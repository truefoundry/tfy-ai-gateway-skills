"""Ask TFY through servicefoundry-server, the path the product UI uses.

sfy builds the agent (instructions, MCP servers, skills, session context) on session create and
proxies every other session call to TrueForge under `/api/svc/v1/ai-features/<tenant>/sessions`.
The TrueForge SDK speaks `/api/v1/sessions`, so a transport rewrites the prefix and the harness
drives Ask TFY unchanged.

The skills commit is chosen per session with `x-ask-tfy-skills-ref`, which sfy only accepts where
`ASK_TFY_ALLOW_SKILLS_REF_OVERRIDE` is on (devtest). sfy stamps the ref it used in session metadata,
and every session is checked against it: a run must never score a commit it did not test.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import httpx
from tfy_eval.agent import AbortRun
from trueforge_sdk import TrueForge

SKILLS_REF_HEADER = "x-ask-tfy-skills-ref"
SKILLS_REF_METADATA_KEY = "skillsRef"
MODEL_METADATA_KEY = "modelIdentifier"
SDK_SESSIONS_PATH = "/api/v1/sessions"

# sfy builds the agent itself and ignores the request body, but the SDK requires one.
AGENT = {"name": "ask-tfy"}

# Keep-alives hold a dead turn's stream open past any read timeout, so cap a stream's lifetime.
# The slowest 1% of whole trials take under 5 minutes.
STREAM_DEADLINE_S = 600.0


class PinMismatch(AbortRun):
    """A session is not on the skills commit or model the run is measuring; stop the whole run."""


class SfyTransport(httpx.HTTPTransport):
    def __init__(self, tenant: str, **kwargs: Any):
        super().__init__(**kwargs)
        self.sessions_path = f"/api/svc/v1/ai-features/{quote(tenant, safe='')}/sessions"

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.url = request.url.copy_with(raw_path=sfy_raw_path(request.url.raw_path, self.sessions_path))
        response = super().handle_request(request)
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            response.stream = DeadlineStream(response.stream, request, time.monotonic() + STREAM_DEADLINE_S)
        return response


class DeadlineStream(httpx.SyncByteStream):
    """Raises a read timeout on the first chunk after `deadline`, so the harness re-attaches or retries."""

    def __init__(self, stream: httpx.SyncByteStream, request: httpx.Request, deadline: float):
        self._stream = stream
        self._request = request
        self._deadline = deadline

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._stream:
            if time.monotonic() > self._deadline:
                raise httpx.ReadTimeout(f"stream open over {STREAM_DEADLINE_S:.0f}s", request=self._request)
            yield chunk

    def close(self) -> None:
        self._stream.close()


def sfy_raw_path(raw_path: bytes, sessions_path: str) -> bytes:
    path, sep, query = raw_path.decode("ascii").partition("?")
    if path != SDK_SESSIONS_PATH and not path.startswith(SDK_SESSIONS_PATH + "/"):
        # sfy proxies sessions only; anything else would reach a different sfy route.
        raise RuntimeError(f"Ask TFY only serves sessions, not {path}")
    return (sessions_path + path[len(SDK_SESSIONS_PATH):] + sep + query).encode("ascii")


def check_pinned(metadata: dict[str, str] | None, skills_sha: str, model: str | None = None) -> None:
    stamped = (metadata or {}).get(SKILLS_REF_METADATA_KEY)
    if stamped != skills_sha:
        raise PinMismatch(
            f"session runs skills {stamped!r}, not {skills_sha}; sfy must honour x-ask-tfy-skills-ref "
            "(ASK_TFY_ALLOW_SKILLS_REF_OVERRIDE)"
        )
    stamped_model = (metadata or {}).get(MODEL_METADATA_KEY)
    if model is not None and stamped_model != model:
        # sfy takes the model from tenant settings per session, so a settings change mid-run
        # would quietly measure two models in one experiment.
        raise PinMismatch(f"session runs model {stamped_model!r}, not {model!r} like the rest of this run")


class _PinnedSessions:
    def __init__(self, sessions: Any, skills_sha: str, model: str | None):
        self._sessions = sessions
        self._skills_sha = skills_sha
        self._model = model

    def create(self, **kwargs: Any) -> Any:
        created = self._sessions.create(**kwargs)
        check_pinned(created.data.metadata, self._skills_sha, self._model)
        return created

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sessions, name)


class PinnedAskTfy:
    """A TrueForge SDK client whose sessions are Ask TFY sessions on one skills commit."""

    def __init__(
        self, host: str, tenant: str, token: str, skills_sha: str, timeout: float, model: str | None = None
    ):
        self._client = TrueForge(
            base_url=host.rstrip("/"),
            token=token,
            headers={SKILLS_REF_HEADER: skills_sha},
            timeout=timeout,
            httpx_client=httpx.Client(transport=SfyTransport(tenant), timeout=timeout),
        )
        self.sessions = _PinnedSessions(self._client.sessions, skills_sha, model)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def probe(client: PinnedAskTfy) -> dict[str, str]:
    """Create one session, without a turn, and return what sfy stamped on it."""
    return dict(client.sessions.create(agent=AGENT).data.metadata or {})

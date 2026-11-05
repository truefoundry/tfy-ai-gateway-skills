"""Redaction of session dumps before they leave our infrastructure, and the scan that checks it worked.

`redact` runs in `export.py fetch`; `scan` runs in `export.py check` and before every upload.
A scan finding reviewed as harmless goes into redaction-allowlist.txt as the sha256 of its value.
"""

import hashlib
import math
import re
from collections import Counter
from pathlib import Path

REDACTION_VERSION = "5"

SECRET_KEYS = {
    "auth_data", "api_key", "apikey", "password", "secret", "token", "access_token",
    "refresh_token", "client_secret", "private_key", "aws_secret_access_key",
    "authorization", "x-api-key", "x-tfy-api-key",
}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    # TrueFoundry tokens (tfy_pat_…); the lookahead spares lowercase identifiers such as tfy_sticky_….
    re.compile(r"\btfy_[a-z]{2,5}_(?=[A-Za-z0-9_\-]*[A-Z0-9])[A-Za-z0-9_\-]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._\-~+/=]{16,}"),
]
# Secret references (tfy-secret://, tfy-k8s-secret://, tfy-ephemeral-secret://) name a secret
# without revealing it; keep them readable.
SECRET_REF = re.compile(r"^tfy-[a-z0-9-]*secret://")
# Placeholders ($VAR, ${VAR}, <token>) are docs, not credentials.
CONN_STRING = re.compile(r"((?<![\w-])(?!tfy-[a-z0-9-]*secret:)[a-z][a-z0-9+.\-]*://[^:/\s@\"'`\\]+:)(?![$<])[^@\s\"'`\\]+@")
KEY_VALUE = re.compile(
    # Prefixed keys count too (x-tfy-api-key, openai_api_key), but not secret references.
    # Quotes may be escaped: tool results are JSON serialised into a string (\"api_key\":\"…\").
    # Kept, being docs or references rather than secrets: placeholders (<KEY>, $VAR, os.environ…,
    # your-key), secret references (tfy-*secret://), field names (spanAttributeKey), env var names.
    r"""(?<![A-Za-z0-9])(\\*["']?(?i:api[_-]?key|(?<!tfy-)(?<!k8s-)(?<!ephemeral-)secret|password|auth[_-]?token|access[_-]?token|client[_-]?secret)\\*["']?\s*[:=]\s*\\*["']?)"""
    r"""(?!\d+\b|//|tfy-[a-z0-9-]*secret:|<|\$|\{|os\.|process\.env\b|\w+\(|(?i:your|my-)|[a-z]+(?:[A-Z][a-z]+)+\b|[A-Z][A-Z0-9_]+\b)([^"'\s,}\\]{6,})"""
)
EMAIL = re.compile(r"(?<![${])\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")


def redact_text(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    text = CONN_STRING.sub(r"\1[REDACTED]@", text)
    text = KEY_VALUE.sub(r"\1[REDACTED]", text)
    return EMAIL.sub(lambda m: "email:" + hashlib.sha256(m.group().lower().encode()).hexdigest()[:10], text)


def redact(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if k.lower() in SECRET_KEYS and isinstance(v, str) and not SECRET_REF.match(v) else redact(v)
            for k, v in value.items()
        }
    return value


# ---------------------------------------------------------------- scan

# A value assigned to a secret-sounding key, with or without (escaped) quotes.
KEYED_TOKEN = re.compile(
    r"""(?i)(api[_-]?key|secret|password|passwd|token|private[_-]?key|credential)s?\\*["']?\s*[:=]\s*\\*["']?([A-Za-z0-9+/_\-.=]{16,})"""
    r"""|(bearer)\s+([A-Za-z0-9+/_\-.=]{16,})"""
)
LONG_TOKEN = re.compile(r"(?<![A-Za-z0-9_\-])[A-Za-z0-9_\-]{32,}(?![A-Za-z0-9_\-])")
# Hashes, TrueFoundry IDs, secret FQNs, and our own redaction marks.
ALLOWED = re.compile(r"^(email:)?[0-9a-f]{10,64}$|^[0-9a-z]{24,26}$|^tfy-secret|REDACTED")
IMAGE_DATA = re.compile(r"^(data:[\w/+.-]+;base64,|iVBOR|/9j/|R0lGOD|UklGR)")
# A JWT header alone (no payload or signature) is a docs example, not a credential; full JWTs are redacted.
JWT_HEADER = re.compile(r"^eyJ[A-Za-z0-9_\-]+$")
# Random-looking but public: thinking signatures, AWS ARNs (role and resource names),
# OAuth client IDs (public by the OAuth spec; their secrets are matched separately).
PUBLIC_CONTEXT = re.compile(r"signature|arn:aws[\w-]*:[^\s\"']*$|client[_-]?id\\*[\"']?\s*[:=]\s*\\*[\"']?$", re.IGNORECASE)
ALLOWLIST_FILE = Path(__file__).with_name("redaction-allowlist.txt")
REVIEWED = {
    line.split()[0]
    for line in (ALLOWLIST_FILE.read_text().splitlines() if ALLOWLIST_FILE.exists() else [])
    if line.strip() and not line.startswith("#")
}


def entropy(s: str) -> float:
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values())


def credential_like(token: str, min_entropy: float) -> bool:
    """Random-looking: mixed case and digits. Identifiers, file names, slugs and words are not."""
    if ALLOWED.search(token) or "." in token.strip(".=") or token.startswith("toolu_") or JWT_HEADER.match(token):
        return False
    if hashlib.sha256(token.encode()).hexdigest() in REVIEWED:
        return False
    parts = re.split(r"[-_]", token)
    if len(parts) >= 3 and all(len(p) <= 12 or p.isdigit() for p in parts):
        return False
    digits = sum(ch.isdigit() for ch in token)
    upper = sum(ch.isupper() for ch in token)
    lower = sum(ch.islower() for ch in token)
    return digits >= 3 and upper >= 2 and lower >= 2 and entropy(token) > min_entropy


def mask(s: str) -> str:
    return s[:4] + "…" + s[-2:] if len(s) > 8 else "…"


def _walk(value, path: str):
    if isinstance(value, dict):
        for k, v in value.items():
            if k.lower() in SECRET_KEYS and isinstance(v, str) and v != "[REDACTED]" and not SECRET_REF.match(v):
                yield path + "." + k, "secret key not redacted", v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _walk(v, f"{path}[{i}]")
    elif isinstance(value, str):
        if IMAGE_DATA.match(value):
            return
        for pattern in SECRET_PATTERNS:
            for m in pattern.finditer(value):
                yield path, "known secret shape", m.group()
        if CONN_STRING.search(value) and "[REDACTED]@" not in value:
            yield path, "connection string with password", CONN_STRING.search(value).group()
        for m in EMAIL.finditer(value):
            yield path, "raw email", m.group()
        for m in KEYED_TOKEN.finditer(value):
            key, token = (m.group(1), m.group(2)) if m.group(2) else (m.group(3), m.group(4))
            if credential_like(token, 3.5):
                yield path, f"value of '{key.lower()}'", token
        for m in LONG_TOKEN.finditer(value):
            if PUBLIC_CONTEXT.search(value[max(0, m.start() - 120):m.start()]):
                continue
            if credential_like(m.group(), 4.3):
                yield path, "high-entropy token", m.group()


def scan(sessions: list[dict]) -> list[tuple[str, str, str, str]]:
    """(session_id, path, kind, value) for everything that still looks like a secret or an email."""
    return [
        (session["session_id"], *finding)
        for i, session in enumerate(sessions)
        for finding in _walk(session, f"sessions[{i}]")
    ]

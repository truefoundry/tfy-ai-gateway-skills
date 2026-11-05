"""A committed snapshot of the tfy-platform-mcp tool names, so CI can check them offline.

    python scripts/tool_schemas.py    # live tools/list -> tool-schemas/tfy-platform-mcp.json

Needs ASK_TFY_HOST, ASK_TFY_TENANT and TFY_API_KEY (evals/runner/.env). Run it when the server's
tools change and commit the result; check_skills.py fails when a skill names a tool it lacks.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "tool-schemas" / "tfy-platform-mcp.json"


def fetch() -> list[dict]:
    url = f"{os.environ['ASK_TFY_HOST'].rstrip('/')}/api/svc/{os.environ['ASK_TFY_TENANT']}/mcp"
    headers = {
        "Authorization": f"Bearer {os.environ['TFY_API_KEY']}",
        "Accept": "application/json, text/event-stream",
    }
    tools: list[dict] = []
    cursor = None
    with httpx.Client(timeout=60) as client:
        while True:
            body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"cursor": cursor} if cursor else {}}
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            text = response.text
            if "data:" in text[:20] or text.startswith("event:"):
                text = [line[5:] for line in text.splitlines() if line.startswith("data:")][-1]
            payload = json.loads(text)
            if "error" in payload:
                raise SystemExit(f"tools/list failed: {payload['error']}")
            tools += payload["result"]["tools"]
            cursor = payload["result"].get("nextCursor")
            if not cursor:
                return sorted(tools, key=lambda tool: tool["name"])


def tool_names() -> set[str]:
    return set(json.loads(SNAPSHOT.read_text()))


def main() -> None:
    SNAPSHOT.parent.mkdir(exist_ok=True)
    tools = [tool["name"] for tool in fetch()]
    SNAPSHOT.write_text(json.dumps(tools, indent=1) + "\n")
    print(f"{len(tools)} tools -> {SNAPSHOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

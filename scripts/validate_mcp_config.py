#!/usr/bin/env python3
"""Validate `.mcp.json` and keep it consistent with root `mcp.json`.

WHY
---
`.mcp.json` is the file Claude Code actually connects through, so a break in it
breaks the plugin for every installed user. The OpenAI package and release gates
also inspect this file as part of broader checks; this script owns the dedicated
connection-configuration validation.

WHAT IT CHECKS
--------------
`.mcp.json` is Claude Code's native format — a bare map of server name to config,
NOT wrapped in an `mcpServers` key (that wrapper is Cursor's shape, in root
`mcp.json`). The two files describe the same server for two different clients,
so the strongest available check is that they agree: same server names, same
URLs, and equivalent transports. Corrupting either one on its own then fails.

`mcp.json`'s own Agent Plugins conformance is checked by
`scripts/validate_agent_plugins.py`; this script only reads it for comparison.

No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent

CLAUDE_NATIVE = REPO_ROOT / ".mcp.json"
AP_CONFIG = REPO_ROOT / "mcp.json"

# The endpoint the whole bundle exists to wrap. Hard-coded on purpose: a change
# here should be a visible, argued diff, not a typo that ships.
CANONICAL_URL = "https://mcp.riverside.com/mcp"

REMOTE_TYPES = {"http", "sse", "streamable-http"}

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        fail(f"{path.name}: file not found")
        return None
    except json.JSONDecodeError as e:
        fail(f"{path.name}: invalid JSON ({e})")
        return None
    if not isinstance(data, dict):
        fail(f"{path.name}: expected a JSON object at the top level, got {type(data).__name__}")
        return None
    return data


def check_url(raw: object, where: str) -> None:
    if not isinstance(raw, str) or not raw:
        fail(f"{where}: `url` must be a non-empty string, got {raw!r}")
        return
    parts = urlsplit(raw)
    if parts.scheme != "https" or not parts.hostname:
        fail(f"{where}: `url` must be an absolute https URL, got {raw!r}")


def canonical_transport(value: object) -> object:
    # Claude Code accepts `streamable-http` as an alias for its native `http`.
    if isinstance(value, str) and value in {"http", "streamable-http"}:
        return "streamable-http"
    return value


def main() -> int:
    native = load(CLAUDE_NATIVE)
    if native is None:
        return report()

    if "mcpServers" in native:
        fail(
            ".mcp.json: has a top-level `mcpServers` key. That is Cursor's wrapped shape "
            "(root mcp.json). Claude Code's native format is a bare map of server name to "
            "config — the wrapper would leave Claude Code with a server literally named "
            "`mcpServers` and no Riverside connection."
        )
        return report()

    if not native:
        fail(".mcp.json: declares no servers")
        return report()

    for name, server in native.items():
        where = f".mcp.json.{name}"
        if not isinstance(server, dict):
            fail(f"{where}: expected an object, got {type(server).__name__}")
            continue
        server_type = server.get("type")
        if server_type is None:
            fail(f"{where}: missing `type`")
        elif server_type in REMOTE_TYPES:
            check_url(server.get("url"), where)
        elif server_type == "stdio":
            if not server.get("command"):
                fail(f"{where}: stdio server has no `command`")
        else:
            fail(f"{where}: unknown transport `{server_type}`")

    if not any(
        isinstance(s, dict) and s.get("url") == CANONICAL_URL for s in native.values()
    ):
        fail(
            f".mcp.json: no server points at {CANONICAL_URL}. That is the endpoint this "
            "bundle wraps; if it moved, change CANONICAL_URL here in the same PR."
        )

    # Cross-check against the Agent Plugins config, which Cursor loads.
    ap = load(AP_CONFIG)
    if ap is not None:
        ap_servers = ap.get("mcpServers")
        if not isinstance(ap_servers, dict):
            fail("mcp.json: `mcpServers` must be an object (Cursor's wrapped shape)")
        else:
            if set(ap_servers) != set(native):
                fail(
                    f"mcp.json declares servers {sorted(ap_servers)} but .mcp.json declares "
                    f"{sorted(native)} — Cursor and Claude Code would not get the same plugin."
                )
            for name in sorted(set(ap_servers) & set(native)):
                ap_url = ap_servers[name].get("url") if isinstance(ap_servers[name], dict) else None
                native_url = native[name].get("url") if isinstance(native[name], dict) else None
                if ap_url != native_url:
                    fail(
                        f"server `{name}`: mcp.json url {ap_url!r} != .mcp.json url "
                        f"{native_url!r} — the two clients would connect to different endpoints."
                    )
                ap_type = ap_servers[name].get("type") if isinstance(ap_servers[name], dict) else None
                native_type = native[name].get("type") if isinstance(native[name], dict) else None
                if canonical_transport(ap_type) != canonical_transport(native_type):
                    fail(
                        f"server `{name}`: mcp.json type {ap_type!r} != .mcp.json type "
                        f"{native_type!r} — the two clients would use different transports."
                    )

    if not errors:
        print(f"MCP config validation passed: {len(native)} server(s), both files agree.")
    return report()


def report() -> int:
    if errors:
        print("MCP config validation FAILED:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

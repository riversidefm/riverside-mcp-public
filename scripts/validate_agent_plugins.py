#!/usr/bin/env python3
"""Validate the Agent Plugins v1.0 files against the official schemas.

Checks root `plugin.json` and root `mcp.json` against the schemas vendored in
`schemas/agent-plugins/1.0.0/`, taken verbatim from
github.com/agentplugins/agent-plugins-spec, plus the semantic requirements the
spec states in prose that JSON Schema cannot express.

WHY THE SCHEMAS ARE VENDORED
----------------------------
The spec itself forbids fetching them at load time (§5.2: "Clients MUST NOT
retrieve a schema while loading a plugin"), and a CI job that reaches the
network to decide whether the build passes is a build that breaks when GitHub
does. Refreshing them is a deliberate, reviewed step — same tradeoff, and same
reasoning, as `expected-tools.txt`.

  Source:  https://github.com/agentplugins/agent-plugins-spec
           schemas/1.0.0/{plugin,mcp}.schema.json
  Fetched: 2026-08-09
  sha256:  plugin  0a4aad95ce337878ad38802ebf0daa3fde76abe3f65400c86bcbb1ec0b3ab883
           mcp     6539175bfcdf43085855183e86da40ea94b166547a72b47ae9a0a390516d3acb

WHY A HAND-ROLLED VALIDATOR
---------------------------
`jsonschema` is not in the stdlib, and this repo's validation deliberately has
no third-party dependencies, so a contributor can run every gate with a bare
`python3`. The evaluator below covers the keyword subset these two pinned
schemas actually use.

The danger with a subset evaluator is that it silently under-validates when the
schema later grows a keyword it does not implement. So it does not skip unknown
keywords — `assert_supported()` walks the vendored schemas first and FAILS THE
BUILD if either uses a keyword this file does not handle. Under-validation
therefore cannot happen quietly: refreshing the schemas either keeps working or
stops the build with the exact keyword to implement.

No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas" / "agent-plugins" / "1.0.0"

PLUGIN_SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
SCHEMA_METADATA = {
    "plugin.schema.json": (
        PLUGIN_SCHEMA_ID,
        "0a4aad95ce337878ad38802ebf0daa3fde76abe3f65400c86bcbb1ec0b3ab883",
    ),
    "mcp.schema.json": (
        MCP_SCHEMA_ID,
        "6539175bfcdf43085855183e86da40ea94b166547a72b47ae9a0a390516d3acb",
    ),
}

# Keywords the evaluator implements.
SUPPORTED = {
    "type", "properties", "required", "additionalProperties", "const", "enum",
    "minLength", "maxLength", "pattern", "items", "oneOf", "$ref", "$defs",
    "propertyNames", "not",
}
# Keywords that carry no constraint and are safe to ignore.
ANNOTATIONS = {"$schema", "$id", "title", "description"}

TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "number": (int, float), "integer": int, "null": type(None),
}

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def unsupported_type_message(expected: object, where: str) -> str:
    return (
        f"{where}: vendored schema uses unsupported `type` value {expected!r}; "
        "extend TYPES in scripts/validate_agent_plugins.py"
    )


def assert_supported(schema: object, origin: str, path: str = "") -> None:
    """Refuse to run against a schema using keywords we do not implement."""
    if isinstance(schema, list):
        for i, item in enumerate(schema):
            assert_supported(item, origin, f"{path}[{i}]")
        return
    if not isinstance(schema, dict):
        return
    for key, value in schema.items():
        if key in ANNOTATIONS:
            continue
        if key not in SUPPORTED:
            fail(
                f"{origin}: vendored schema uses JSON Schema keyword `{key}` at "
                f"{path or '<root>'}, which scripts/validate_agent_plugins.py does not "
                "implement. Implement it (and add it to SUPPORTED) rather than letting "
                "this file under-validate."
            )
            continue
        if key == "type" and (not isinstance(value, str) or value not in TYPES):
            fail(unsupported_type_message(value, f"{origin} at {path or '<root>'}"))
            continue
        if key in {"properties", "$defs"} and isinstance(value, dict):
            for name, sub in value.items():
                assert_supported(sub, origin, f"{path}/{key}/{name}")
        elif key in {"additionalProperties", "items", "propertyNames", "not"}:
            assert_supported(value, origin, f"{path}/{key}")
        elif key == "oneOf":
            assert_supported(value, origin, f"{path}/oneOf")


def resolve(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"only local refs are supported, got {ref!r}")
    node: object = root
    for part in ref[2:].split("/"):
        node = node[part]  # type: ignore[index]
    if not isinstance(node, dict):
        raise ValueError(f"{ref} does not resolve to a schema object")
    return node


def validate(instance: object, schema: dict, root: dict, where: str) -> list[str]:
    """Return a list of violation messages; empty means valid."""
    out: list[str] = []

    if "$ref" in schema:
        return validate(instance, resolve(schema["$ref"], root), root, where)

    if "type" in schema:
        expected = schema["type"]
        if not isinstance(expected, str) or expected not in TYPES:
            return [unsupported_type_message(expected, where)]
        py = TYPES[expected]
        # JSON booleans are Python bools, which are ints — keep them distinct.
        ok = isinstance(instance, py) and not (
            expected in {"number", "integer"} and isinstance(instance, bool)
        )
        if not ok:
            return [f"{where}: expected {expected}, got {type(instance).__name__}"]

    if "const" in schema and instance != schema["const"]:
        out.append(f"{where}: must be {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        out.append(f"{where}: must be one of {schema['enum']!r}, got {instance!r}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            out.append(f"{where}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            out.append(f"{where}: longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            out.append(f"{where}: {instance!r} does not match /{schema['pattern']}/")

    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            out.extend(validate(item, schema["items"], root, f"{where}[{i}]"))

    if isinstance(instance, dict):
        for name in schema.get("required", []):
            if name not in instance:
                out.append(f"{where}: missing required field `{name}`")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                out.extend(validate(value, props[key], root, f"{where}.{key}"))
                continue
            extra = schema.get("additionalProperties", True)
            if extra is False:
                out.append(
                    f"{where}: unexpected field `{key}` — the Agent Plugins schema is "
                    "closed (additionalProperties: false)"
                )
            elif isinstance(extra, dict):
                out.extend(validate(value, extra, root, f"{where}.{key}"))
        if "propertyNames" in schema:
            for key in instance:
                out.extend(validate(key, schema["propertyNames"], root, f"{where}: key {key!r}"))

    if "not" in schema and not validate(instance, schema["not"], root, where):
        out.append(f"{where}: matches a forbidden schema")

    if "oneOf" in schema:
        matched = [b for b in schema["oneOf"] if not validate(instance, b, root, where)]
        if len(matched) != 1:
            # Report against the branch selected by `type`, which gives a usable
            # message instead of "no branch matched".
            declared = instance.get("type") if isinstance(instance, dict) else None
            for branch in schema["oneOf"]:
                target = resolve(branch["$ref"], root) if "$ref" in branch else branch
                if target.get("properties", {}).get("type", {}).get("const") == declared:
                    out.extend(validate(instance, target, root, where))
                    break
            else:
                out.append(
                    f"{where}: matches {len(matched)} of {len(schema['oneOf'])} allowed "
                    f"server variants (type={declared!r})"
                )

    return out


def load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        fail(f"{path.relative_to(REPO_ROOT)}: file not found")
        return None
    except json.JSONDecodeError as e:
        fail(f"{path.relative_to(REPO_ROOT)}: invalid JSON ({e})")
        return None
    if not isinstance(data, dict):
        fail(f"{path.relative_to(REPO_ROOT)}: expected a JSON object at the top level")
        return None
    return data


def load_vendored_schema(name: str) -> dict | None:
    path = SCHEMA_DIR / name
    label = f"schemas/agent-plugins/1.0.0/{name}"
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        fail(f"{label}: file not found")
        return None
    except OSError as exc:
        fail(f"{label}: could not be read ({exc})")
        return None

    expected_id, expected_digest = SCHEMA_METADATA[name]
    actual_digest = hashlib.sha256(raw).hexdigest()
    if actual_digest != expected_digest:
        fail(f"{label}: sha256 {actual_digest} does not match recorded {expected_digest}")

    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label}: invalid JSON ({exc})")
        return None
    if not isinstance(data, dict):
        fail(f"{label}: expected a JSON object at the top level")
        return None
    if data.get("$id") != expected_id:
        fail(f"{label}: unexpected $id {data.get('$id')!r}; expected {expected_id!r}")
    return data


def check_remote_url(raw: object, where: str) -> None:
    """Spec §7.2.1 constraints on a remote MCP `url`, which the schema (minLength
    only) does not express."""
    if not isinstance(raw, str):
        return
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        fail(f"{where}: `url` must be an absolute http(s) URL, got {raw!r}")
        return
    if not parts.hostname:
        fail(f"{where}: `url` has no host ({raw!r})")
        return
    if parts.fragment:
        fail(f"{where}: `url` must not contain a fragment ({raw!r})")
    if parts.username or parts.password:
        fail(f"{where}: `url` must not contain user information ({raw!r})")
    loopback = parts.hostname == "localhost" or parts.hostname.startswith("127.")
    if parts.scheme == "http" and not loopback:
        fail(f"{where}: non-loopback `url` must use HTTPS ({raw!r})")


def check_stdio_cwd(raw: object, where: str) -> None:
    if not isinstance(raw, str):
        return

    plugin_root = REPO_ROOT.resolve()
    if raw.startswith("./"):
        root, suffix = plugin_root, raw[2:]
    elif raw == "${PLUGIN_ROOT}" or raw.startswith("${PLUGIN_ROOT}/"):
        root, suffix = plugin_root, raw.removeprefix("${PLUGIN_ROOT}").removeprefix("/")
    elif raw == "${PLUGIN_DATA}" or raw.startswith("${PLUGIN_DATA}/"):
        # The client chooses PLUGIN_DATA at install time, so its real symlink
        # graph does not exist at package-validation time. A fixed synthetic
        # root rejects lexical traversal here; the client must repeat resolved
        # containment against the actual data directory before launching.
        root = Path("/__agent_plugins_plugin_data__")
        suffix = raw.removeprefix("${PLUGIN_DATA}").removeprefix("/")
    else:
        return

    root = root.resolve()
    resolved = (root / suffix).resolve()
    if not resolved.is_relative_to(root):
        fail(f"{where}: `cwd` {raw!r} resolves outside its declared root (escapes containment)")


def main() -> int:
    plugin_schema = load_vendored_schema("plugin.schema.json")
    mcp_schema = load_vendored_schema("mcp.schema.json")
    if plugin_schema is None or mcp_schema is None:
        return report()

    for schema, name in ((plugin_schema, "plugin.schema.json"), (mcp_schema, "mcp.schema.json")):
        assert_supported(schema, f"schemas/agent-plugins/1.0.0/{name}")
    if errors:
        return report()

    # §4.1.2 / §5.1: the manifest is the one hard MUST.
    plugin = load(REPO_ROOT / "plugin.json")
    if plugin is None:
        fail(
            "plugin.json is required at the plugin root by Agent Plugins §4.1.2. Without "
            "it a conforming client rejects the plugin outright."
        )
    else:
        for msg in validate(plugin, plugin_schema, plugin_schema, "plugin.json"):
            fail(msg)
        # Targeted message for the documented footgun: these four fields are
        # legitimate in .cursor-plugin/plugin.json and fatal here.
        for banned in ("displayName", "logo", "skills", "mcpServers"):
            if banned in plugin:
                fail(
                    f"plugin.json: `{banned}` must not appear in the Agent Plugins manifest. "
                    "Components are discovered from fixed locations (§6.1), not declared. "
                    "It belongs in .cursor-plugin/plugin.json, which is a different file."
                )

    mcp = load(REPO_ROOT / "mcp.json")
    if mcp is not None:
        for msg in validate(mcp, mcp_schema, mcp_schema, "mcp.json"):
            fail(msg)
        servers = mcp.get("mcpServers")
        if isinstance(servers, dict):
            for name, server in servers.items():
                if not isinstance(server, dict):
                    continue
                where = f"mcp.json.mcpServers.{name}"
                if server.get("type") in {"streamable-http", "sse"}:
                    check_remote_url(server.get("url"), where)
                elif server.get("type") == "stdio":
                    check_stdio_cwd(server.get("cwd"), where)

    # §7.2.2 rule 2: mcp.json targeting a different AP version than plugin.json
    # makes a client disable MCP for the whole plugin.
    if plugin is not None and mcp is not None:
        if plugin.get("$schema") == PLUGIN_SCHEMA_ID and mcp.get("$schema") != MCP_SCHEMA_ID:
            fail(
                "mcp.json and plugin.json target different Agent Plugins versions — a "
                "conforming client disables MCP for the whole plugin (§7.2.2)."
            )

    if not errors:
        print("Agent Plugins validation passed: plugin.json and mcp.json conform to v1.0.0.")
    return report()


def report() -> int:
    if errors:
        print("Agent Plugins validation FAILED:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

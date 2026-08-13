#!/usr/bin/env python3
"""Validation gate for the OpenAI (ChatGPT / Codex) packaging.

WHY
---
`claude plugin validate --strict` reads only the Claude manifest, and
`validate_cursor_package.py` only the Cursor one. Until 0.6.0 the repo shipped
no OpenAI lane at all: `.codex-plugin/plugin.json` and the `agents/openai.yaml`
files did not exist on any branch, so a ChatGPT/Codex packaging regression had
nothing to fail against. This script is that gate.

WHAT IT CHECKS
--------------
1. `.codex-plugin/plugin.json` parses, has the required fields, and declares the
   same `name` and `version` as `.claude-plugin/plugin.json`.
2. Its `skills` path field is relative, `./`-prefixed, exists, and stays inside
   the repo.
3. `interface` carries the fields OpenAI requires — including a `supportURL`,
   which both directories ask for — every listing field is inside its character
   cap, `defaultPrompt` obeys the documented "at most 3, each <= 128 characters"
   limit, and every referenced asset exists (screenshots must be PNG).
4. No ChatGPT app binding is committed: no `apps` field in the manifest and no
   `.app.json` file. See NO APP BINDING below.
5. `mcpServers` — see MCP SHAPE below.
6. The plugin-level and per-skill `agents/openai.yaml` files parse and declare an
   interface, the three tool-using skills declare the Riverside MCP dependency
   with `transport: streamable_http`, and no file names an endpoint other than
   the canonical production one.

MCP SHAPE
---------
The OpenAI plugin spec accepts `mcpServers` as either a path string or an inline
object. Riverside uses the inline object deliberately: this repo's `.mcp.json` is
the Claude *plugin* shape — a bare `{"<server>": {...}}` map — whereas every
plugin in OpenAI's own registry (github, figma, cloudflare, codex-security)
wraps `.mcp.json` in a top-level `"mcpServers"` key. Pointing OpenAI at our
unwrapped file would hand it a shape no registry plugin uses. The cost of
inlining is a third copy of the endpoint, so check 5 asserts the inline entry
agrees with `.mcp.json` and `mcp.json` on both server name and URL — the same
anti-drift argument `validate_mcp_config.py` makes for the existing two copies.
If `mcpServers` is ever switched back to a path, this script requires the target
to be wrapped, because that is the trap being guarded.

NO APP BINDING
--------------
An app id is workspace-scoped: it is only usable by the account or workspace that
registered it. Committing one binds this package to a single workspace, and the
value becomes world-readable as soon as the repository is public.

The directory path does not consume it either. A Skills-only upload removes
`.app.json`, and an MCP-backed submission uses "With MCP" and submits the MCP
server directly, so the binding is never the mechanism by which a listed plugin
reaches the server. It is only useful for a locally sideloaded Developer Mode
app, which is not what this repository ships.

So check 4 is an absence check, in both halves: the manifest must declare no
`apps` field, and no `.app.json` may exist in the tree. Either one alone would
leave the other free to reappear.

No third-party dependencies — stdlib only, so it runs in seconds.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent

CODEX_MANIFEST = Path(".codex-plugin/plugin.json")
CLAUDE_MANIFEST = Path(".claude-plugin/plugin.json")
APP_MANIFEST = Path(".app.json")
CLAUDE_NATIVE_MCP = Path(".mcp.json")
AP_MCP = Path("mcp.json")
PLUGIN_AGENT_YAML = Path("agents/openai.yaml")

CANONICAL_URL = "https://mcp.riverside.com/mcp"
CANONICAL_TRANSPORT = "streamable_http"

# `setup` is connection guidance and deliberately declares no MCP dependency:
# it has to stay usable when the MCP is exactly what is failing to connect.
TOOL_SKILLS = ("content-discovery", "social-publishing", "video-editing")

REQUIRED_INTERFACE_FIELDS = (
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    # Both directories ask for a reachable support destination, and OpenAI's
    # submission form requires an HTTPS one — an email address does not satisfy it.
    "supportURL",
)
ASSET_FIELDS = ("composerIcon", "logo", "logoDark")
URL_FIELDS = ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL")

MAX_DEFAULT_PROMPTS = 3
MAX_DEFAULT_PROMPT_CHARS = 128

# Listing-field character caps. `shortDescription` is the listing subtitle, and
# OpenAI's final submission step rejects one over 30 with
# `submission_subtitle_too_long` — a failure that surfaces only at submission
# time, long after CI has gone green, so it is worth asserting here.
MAX_INTERFACE_CHARS = {
    "displayName": 30,
    "shortDescription": 30,
    "longDescription": 1000,
    "developerName": 40,
}

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def repo_root() -> Path:
    """`REPO_ROOT` with symlinks resolved.

    Every containment comparison must resolve both sides. `Path.resolve()`
    follows symlinks, so comparing a resolved candidate against an unresolved
    root reports a false escape — or raises — whenever the checkout path crosses
    a symlink, which on macOS both `/tmp` and `/var` do.
    """
    return REPO_ROOT.resolve()


# --------------------------------------------------------------------------
# A deliberately small YAML reader.
#
# The repo is stdlib-only, so there is no PyYAML. Rather than accept arbitrary
# YAML, this parses exactly the shape these files use — nested maps of scalars
# plus a sequence of maps — and errors on anything else. That is a feature: it
# keeps `agents/openai.yaml` in one canonical, reviewable shape.
# --------------------------------------------------------------------------


class YamlError(Exception):
    pass


def _parse_scalar(raw: str, line_no: int) -> str:
    raw = raw.strip()
    if raw[:1] in {"'", '"'}:
        quote = raw[0]
        closing = raw.find(quote, 1)
        if closing == -1:
            raise YamlError(f"line {line_no}: unterminated {quote} quote")
        trailing = raw[closing + 1 :].strip()
        if trailing and not trailing.startswith("#"):
            raise YamlError(f"line {line_no}: unexpected text after the closing quote")
        return raw[1:closing]
    head, sep, _ = raw.partition(" #")
    return (head if sep else raw).strip()


def _tokenize(text: str) -> list[tuple[int, int, str]]:
    tokens: list[tuple[int, int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Measure all leading whitespace, not just spaces: a tab-indented line
        # would otherwise measure as indent 0 and parse as a column-0 sibling.
        leading = line[: len(line) - len(line.lstrip())]
        if "\t" in leading:
            raise YamlError(f"line {line_no}: tabs are not valid YAML indentation")
        tokens.append((line_no, len(leading), stripped))
    return tokens


def _parse_map(tokens: list[tuple[int, int, str]], pos: int, indent: int) -> tuple[dict, int]:
    result: dict = {}
    while pos < len(tokens) and tokens[pos][1] == indent and not tokens[pos][2].startswith("- "):
        line_no, _, text = tokens[pos]
        key, sep, rest = text.partition(":")
        if not sep:
            raise YamlError(f"line {line_no}: expected `key: value`, got {text!r}")
        key = key.strip()
        if not key:
            raise YamlError(f"line {line_no}: empty key")
        if key in result:
            raise YamlError(f"line {line_no}: duplicate key {key!r}")
        pos += 1
        rest = rest.strip()
        if rest:
            result[key] = _parse_scalar(rest, line_no)
            continue
        if pos < len(tokens) and tokens[pos][1] > indent:
            child_indent = tokens[pos][1]
            if tokens[pos][2].startswith("- "):
                result[key], pos = _parse_sequence(tokens, pos, child_indent)
            else:
                result[key], pos = _parse_map(tokens, pos, child_indent)
        else:
            result[key] = None
    return result, pos


def _parse_sequence(tokens: list[tuple[int, int, str]], pos: int, indent: int) -> tuple[list, int]:
    items: list = []
    while pos < len(tokens) and tokens[pos][1] == indent and tokens[pos][2].startswith("- "):
        line_no, _, text = tokens[pos]
        inner = text[2:].strip()
        if ":" not in inner:
            raise YamlError(f"line {line_no}: only sequences of `key: value` maps are supported")
        pos += 1
        item_indent = indent + 2
        item_tokens = [(line_no, item_indent, inner)]
        while pos < len(tokens) and tokens[pos][1] > indent:
            token = tokens[pos]
            if token[1] != item_indent:
                raise YamlError(
                    f"line {token[0]}: unexpected indentation inside a sequence item"
                )
            item_tokens.append(token)
            pos += 1
        item, consumed = _parse_map(item_tokens, 0, item_indent)
        if consumed != len(item_tokens):
            raise YamlError(
                f"line {item_tokens[consumed][0]}: unexpected content inside a sequence item"
            )
        items.append(item)
    return items, pos


def parse_yaml(text: str) -> dict:
    tokens = _tokenize(text)
    if not tokens:
        return {}
    if tokens[0][1] != 0:
        raise YamlError(f"line {tokens[0][0]}: document must start at column 0")
    data, pos = _parse_map(tokens, 0, 0)
    if pos != len(tokens):
        raise YamlError(f"line {tokens[pos][0]}: unexpected indentation")
    return data


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def load_json(rel: Path) -> dict | None:
    path = REPO_ROOT / rel
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        fail(f"{rel}: file not found")
        return None
    except json.JSONDecodeError as exc:
        fail(f"{rel}: invalid JSON ({exc})")
        return None
    except (OSError, UnicodeError) as exc:
        fail(f"{rel}: could not be read ({exc})")
        return None
    if not isinstance(data, dict):
        fail(f"{rel}: expected a JSON object at the top level, got {type(data).__name__}")
        return None
    return data


def load_yaml(rel: Path) -> dict | None:
    path = REPO_ROOT / rel
    try:
        text = path.read_text()
    except FileNotFoundError:
        fail(f"{rel}: file not found")
        return None
    except (OSError, UnicodeError) as exc:
        fail(f"{rel}: could not be read ({exc})")
        return None
    try:
        data = parse_yaml(text)
    except YamlError as exc:
        fail(f"{rel}: {exc}")
        return None
    if not isinstance(data, dict):
        fail(f"{rel}: expected a mapping at the top level")
        return None
    return data


def require_string(data: dict, field: str, where: str) -> str | None:
    value = data.get(field)
    if field not in data:
        fail(f"{where}: missing required field `{field}`")
        return None
    if not isinstance(value, str) or not value.strip():
        fail(f"{where}: `{field}` must be a non-empty string, got {value!r}")
        return None
    return value


def resolve_inside_repo(raw: object, field: str, where: str) -> Path | None:
    """Resolve a manifest path field and ensure it stays inside the repo."""
    if not isinstance(raw, str) or not raw:
        fail(f"{where}: `{field}` must be a non-empty string, got {raw!r}")
        return None
    if raw.startswith("/"):
        fail(f"{where}: `{field}` must be relative, got absolute path {raw!r}")
        return None
    if not raw.startswith("./"):
        fail(f"{where}: `{field}` ({raw!r}) must begin with `./` per the OpenAI plugin spec")
        return None
    root = repo_root()
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        fail(f"{where}: `{field}` ({raw!r}) escapes the repo root")
        return None
    if not candidate.exists():
        fail(f"{where}: `{field}` ({raw!r}) does not exist")
        return None
    return candidate


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def check_interface(manifest: dict) -> None:
    where = str(CODEX_MANIFEST)
    interface = manifest.get("interface")
    if interface is None:
        fail(f"{where}: missing required field `interface`")
        return
    if not isinstance(interface, dict):
        fail(f"{where}: `interface` must be an object, got {type(interface).__name__}")
        return

    for field in REQUIRED_INTERFACE_FIELDS:
        if field == "capabilities":
            capabilities = interface.get("capabilities")
            if not isinstance(capabilities, list) or not capabilities:
                fail(f"{where}: `interface.capabilities` must be a non-empty array")
            elif not all(isinstance(c, str) and c.strip() for c in capabilities):
                fail(f"{where}: `interface.capabilities` entries must be non-empty strings")
            continue
        value = require_string(interface, field, f"{where} interface")
        cap = MAX_INTERFACE_CHARS.get(field)
        if value is not None and cap is not None and len(value) > cap:
            detail = (
                " (a longer subtitle fails OpenAI's submission step with "
                "`submission_subtitle_too_long`)"
                if field == "shortDescription"
                else ""
            )
            fail(
                f"{where}: `interface.{field}` is {len(value)} characters; "
                f"the cap is {cap}{detail}"
            )

    for field in URL_FIELDS:
        if field not in interface:
            continue
        value = interface.get(field)
        parsed = None
        hostname = None
        if isinstance(value, str):
            try:
                parsed = urlsplit(value)
                hostname = parsed.hostname
                _ = parsed.port
            except ValueError:
                parsed = None
                hostname = None
        if parsed is None or parsed.scheme != "https" or not hostname:
            fail(
                f"{where}: `interface.{field}` must be an https:// URL, got {value!r}. "
                "The directories link these fields directly; an email address or a bare "
                "hostname is not a usable destination."
            )

    prompts = interface.get("defaultPrompt")
    if prompts is not None:
        if not isinstance(prompts, list):
            fail(f"{where}: `interface.defaultPrompt` must be an array, got {type(prompts).__name__}")
        else:
            if len(prompts) > MAX_DEFAULT_PROMPTS:
                fail(
                    f"{where}: `interface.defaultPrompt` has {len(prompts)} entries; "
                    f"OpenAI allows at most {MAX_DEFAULT_PROMPTS}"
                )
            for i, prompt in enumerate(prompts):
                if not isinstance(prompt, str) or not prompt.strip():
                    fail(f"{where}: `interface.defaultPrompt[{i}]` must be a non-empty string")
                elif len(prompt) > MAX_DEFAULT_PROMPT_CHARS:
                    fail(
                        f"{where}: `interface.defaultPrompt[{i}]` is {len(prompt)} characters; "
                        f"OpenAI caps each at {MAX_DEFAULT_PROMPT_CHARS}"
                    )

    for field in ASSET_FIELDS:
        if field in interface:
            resolve_inside_repo(interface[field], f"interface.{field}", where)

    screenshots = interface.get("screenshots")
    if screenshots is not None:
        if not isinstance(screenshots, list):
            fail(f"{where}: `interface.screenshots` must be an array")
        else:
            for i, shot in enumerate(screenshots):
                if resolve_inside_repo(shot, f"interface.screenshots[{i}]", where) is None:
                    continue
                if not str(shot).lower().endswith(".png"):
                    fail(f"{where}: `interface.screenshots[{i}]` ({shot!r}) must be a PNG")


def check_no_app_binding(manifest: dict) -> None:
    """See NO APP BINDING in the module docstring."""
    where = str(CODEX_MANIFEST)
    if "apps" in manifest:
        fail(
            f"{where}: `apps` must not be declared. A ChatGPT app id is workspace-scoped and "
            "becomes world-readable in a public repository, and the directory path does not "
            "consume it — a Skills-only upload removes it, and an MCP-backed submission submits "
            "the MCP server directly. Remove the field."
        )
    for app_manifest in sorted(REPO_ROOT.rglob(APP_MANIFEST.name)):
        relative = app_manifest.relative_to(REPO_ROOT)
        if ".git" in relative.parts:
            continue
        fail(
            f"{relative}: must not be committed. It binds this package to one ChatGPT "
            "workspace and publishes that binding. Keep the id out of the repository and "
            "register the app in the workspace that needs it."
        )


def check_mcp_servers(manifest: dict) -> None:
    """See MCP SHAPE in the module docstring."""
    where = str(CODEX_MANIFEST)
    raw = manifest.get("mcpServers")
    if raw is None:
        fail(f"{where}: missing required field `mcpServers`")
        return

    inline = isinstance(raw, dict)
    if isinstance(raw, str):
        target = resolve_inside_repo(raw, "mcpServers", where)
        if target is None:
            return
        rel = target.relative_to(repo_root())
        pointed = load_json(rel)
        if pointed is None:
            return
        if "mcpServers" not in pointed:
            fail(
                f"{where}: `mcpServers` points at {raw!r}, which has no top-level `mcpServers` key. "
                "OpenAI expects the wrapped shape; this repo's .mcp.json is the unwrapped Claude "
                "plugin shape. Use the inline object form, or point at a wrapped file."
            )
            return
        servers = pointed["mcpServers"]
    elif isinstance(raw, dict):
        servers = raw
    else:
        fail(f"{where}: `mcpServers` must be a path string or an object, got {type(raw).__name__}")
        return

    if not isinstance(servers, dict) or not servers:
        fail(f"{where}: `mcpServers` resolved to no servers")
        return

    for name, entry in sorted(servers.items()):
        if not isinstance(entry, dict):
            fail(f"{where}: `mcpServers.{name}` must be an object, got {type(entry).__name__}")
            continue
        if inline and entry.get("type") != "http":
            fail(
                f"{where}: `mcpServers.{name}.type` must be 'http' for an inline remote server, "
                f"got {entry.get('type')!r}"
            )
        url = entry.get("url")
        if url != CANONICAL_URL:
            fail(
                f"{where}: `mcpServers.{name}.url` must be {CANONICAL_URL!r}, got {url!r}"
            )

    # Anti-drift: the inline copy must agree with the two existing configs.
    native = load_json(CLAUDE_NATIVE_MCP)
    ap = load_json(AP_MCP)
    if native is None or ap is None:
        return
    ap_servers = ap.get("mcpServers")
    if not isinstance(ap_servers, dict):
        fail(f"{AP_MCP}: expected a top-level `mcpServers` object")
        return
    expected = set(native)
    names_match = set(servers) == expected and set(ap_servers) == expected
    if not names_match:
        fail(
            f"{where}: `mcpServers` names {sorted(servers)} disagree with "
            f"{CLAUDE_NATIVE_MCP} {sorted(native)} and {AP_MCP} {sorted(ap_servers)} — "
            "all three describe the same server and must move together"
        )
        return

    for name in sorted(expected):
        configs = (servers, native, ap_servers)
        urls = [
            config[name].get("url") if isinstance(config[name], dict) else None
            for config in configs
        ]
        if not (urls[0] == urls[1] == urls[2]):
            fail(
                f"{where}: `mcpServers.{name}.url` {urls[0]!r} disagrees with "
                f"{CLAUDE_NATIVE_MCP} {urls[1]!r} and {AP_MCP} {urls[2]!r} — "
                "all three URLs must move together"
            )


def check_agent_yaml(rel: Path, require_dependency: bool, mcp_names: set[str]) -> None:
    data = load_yaml(rel)
    if data is None:
        return

    interface = data.get("interface")
    if not isinstance(interface, dict):
        fail(f"{rel}: missing an `interface` mapping")
    else:
        for field in ("display_name", "short_description"):
            value = interface.get(field)
            if not isinstance(value, str) or not value.strip():
                fail(f"{rel}: `interface.{field}` must be a non-empty string, got {value!r}")

    dependencies = data.get("dependencies")
    if dependencies is None:
        if require_dependency:
            fail(
                f"{rel}: missing `dependencies.tools` — this skill calls Riverside MCP tools, so "
                "it must declare the dependency so ChatGPT makes the server available to it"
            )
        return

    if not isinstance(dependencies, dict):
        fail(f"{rel}: `dependencies` must be a mapping")
        return
    tools = dependencies.get("tools")
    if not isinstance(tools, list) or not tools:
        fail(f"{rel}: `dependencies.tools` must be a non-empty sequence")
        return

    mcp_entries = 0
    for i, tool in enumerate(tools):
        if not isinstance(tool, dict):
            fail(f"{rel}: `dependencies.tools[{i}]` must be a mapping")
            continue
        if tool.get("type") != "mcp":
            fail(f"{rel}: `dependencies.tools[{i}].type` must be 'mcp', got {tool.get('type')!r}")
            continue
        mcp_entries += 1
        value = tool.get("value")
        if not isinstance(value, str) or not value.strip():
            fail(f"{rel}: `dependencies.tools[{i}].value` must be a non-empty string")
        elif mcp_names and value not in mcp_names:
            fail(
                f"{rel}: `dependencies.tools[{i}].value` is {value!r}, which is not a configured "
                f"MCP server name ({', '.join(sorted(mcp_names))})"
            )
        transport = tool.get("transport")
        if transport != CANONICAL_TRANSPORT:
            fail(
                f"{rel}: `dependencies.tools[{i}].transport` must be {CANONICAL_TRANSPORT!r}, "
                f"got {transport!r}"
            )
        url = tool.get("url")
        if url != CANONICAL_URL:
            fail(f"{rel}: `dependencies.tools[{i}].url` must be {CANONICAL_URL!r}, got {url!r}")
        description = tool.get("description")
        if not isinstance(description, str) or not description.strip():
            fail(f"{rel}: `dependencies.tools[{i}].description` must be a non-empty string")

    if require_dependency and mcp_entries == 0:
        fail(f"{rel}: `dependencies.tools` declares no `type: mcp` entry")


def check_skills(manifest: dict, mcp_names: set[str]) -> None:
    where = str(CODEX_MANIFEST)
    raw = manifest.get("skills")
    if raw is None:
        fail(f"{where}: missing required field `skills`")
        return
    skills_dir = resolve_inside_repo(raw, "skills", where)
    if skills_dir is None:
        return
    if raw != "./skills/":
        fail(f"{where}: `skills` should be './skills/', got {raw!r}")

    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    if not skill_files:
        fail(f"{where}: `skills` ({raw!r}) contains no */SKILL.md files")
        return

    present = {p.parent.name for p in skill_files}
    missing = [name for name in TOOL_SKILLS if name not in present]
    if missing:
        fail(
            f"skills/: expected the tool-using skills {', '.join(TOOL_SKILLS)}; "
            f"missing {', '.join(missing)}"
        )

    root = repo_root()
    for skill_md in skill_files:
        name = skill_md.parent.name
        yaml_rel = skill_md.parent.relative_to(root) / "agents" / "openai.yaml"
        exists = (root / yaml_rel).exists()
        if name in TOOL_SKILLS:
            if not exists:
                fail(
                    f"{yaml_rel}: file not found. Every tool-using skill needs OpenAI agent "
                    "metadata declaring the Riverside MCP dependency."
                )
                continue
            check_agent_yaml(yaml_rel, require_dependency=True, mcp_names=mcp_names)
        elif exists:
            # Optional for non-tool skills, but it must still be well-formed.
            check_agent_yaml(yaml_rel, require_dependency=False, mcp_names=mcp_names)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    manifest = load_json(CODEX_MANIFEST)
    claude_manifest = load_json(CLAUDE_MANIFEST)
    if manifest is None or claude_manifest is None:
        return report()

    name = require_string(manifest, "name", str(CODEX_MANIFEST))
    version = require_string(manifest, "version", str(CODEX_MANIFEST))
    require_string(manifest, "description", str(CODEX_MANIFEST))

    claude_name = claude_manifest.get("name")
    if name is not None and claude_name != name:
        fail(
            f"{CODEX_MANIFEST} name ({name!r}) does not match {CLAUDE_MANIFEST} name "
            f"({claude_name!r}) — the name is the component namespace and must be identical"
        )

    claude_version = claude_manifest.get("version")
    if version != claude_version:
        fail(
            f"{CODEX_MANIFEST} version ({version!r}) does not match {CLAUDE_MANIFEST} version "
            f"({claude_version!r}) — every host manifest ships from this repo together"
        )

    native = load_json(CLAUDE_NATIVE_MCP)
    mcp_names = set(native) if isinstance(native, dict) else set()

    check_interface(manifest)
    check_no_app_binding(manifest)
    check_mcp_servers(manifest)
    check_skills(manifest, mcp_names)

    plugin_yaml_exists = (REPO_ROOT / PLUGIN_AGENT_YAML).exists()
    if not plugin_yaml_exists:
        fail(f"{PLUGIN_AGENT_YAML}: file not found (plugin-level OpenAI agent metadata)")
    else:
        check_agent_yaml(PLUGIN_AGENT_YAML, require_dependency=False, mcp_names=mcp_names)

    return report()


def report() -> int:
    if errors:
        print("OpenAI package validation FAILED:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("OpenAI package validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

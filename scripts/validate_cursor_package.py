#!/usr/bin/env python3
"""Lightweight validation gate for the Cursor packaging.

`claude plugin validate --strict` (run alongside this in CI) only checks the
Claude plugin manifest. This script checks the Cursor-specific package
(`.cursor-plugin/plugin.json`) so a Cursor packaging regression can't merge
silently:

  - `.cursor-plugin/plugin.json` is valid JSON with the required fields.
  - Its `version` matches `.claude-plugin/plugin.json`'s `version` (the two
    packages are expected to move together — see CHANGELOG.md).
  - The `skills` and `mcpServers` paths it references are relative, resolve
    to files/dirs that exist, and stay inside the repo (no `..` escape, no
    absolute paths).
  - Every `skills/*/SKILL.md` has `name` and `description` in its frontmatter
    (Cursor's review checklist requires this).

No third-party dependencies — stdlib only, so it runs in seconds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def load_json(path: Path) -> dict | None:
    """Parse a JSON file, requiring a top-level object. Returns None (having
    already called fail()) on any error, so callers can distinguish a real
    failure from a legitimately empty `{}`."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        fail(f"{path.relative_to(REPO_ROOT)}: file not found")
        return None
    except json.JSONDecodeError as e:
        fail(f"{path.relative_to(REPO_ROOT)}: invalid JSON ({e})")
        return None
    if not isinstance(data, dict):
        fail(f"{path.relative_to(REPO_ROOT)}: expected a JSON object at the top level, got {type(data).__name__}")
        return None
    return data


def resolve_relative(raw: object, field: str) -> Path | None:
    """Resolve a manifest path field and ensure it stays inside the repo."""
    if not isinstance(raw, str) or not raw:
        fail(f".cursor-plugin/plugin.json: `{field}` must be a non-empty string, got {raw!r}")
        return None
    if raw.startswith("/"):
        fail(f".cursor-plugin/plugin.json: `{field}` must be relative, got absolute path {raw!r}")
        return None
    candidate = (REPO_ROOT / raw).resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError:
        fail(f".cursor-plugin/plugin.json: `{field}` ({raw!r}) escapes the repo root")
        return None
    if not candidate.exists():
        fail(f".cursor-plugin/plugin.json: `{field}` ({raw!r}) does not exist")
        return None
    return candidate


# A YAML block scalar (`description: >`) carries its value in the indented lines
# beneath the key rather than on the key's own line.
BLOCK_SCALAR_INDICATORS = {"|", ">", "|-", ">-", "|+", ">+"}


def scalar_value(raw: str) -> str | None:
    """The effective value of an inline YAML scalar, or None if it is malformed.

    Unwraps a quoted scalar, so `name: "a # b"` keeps its `#`, and drops a
    trailing `# …` comment from an unquoted one, so `name: # TODO` is empty.
    A quoted scalar is malformed — not empty — when its closing quote is
    missing (`name: "draft`) or when anything other than a comment follows it
    (`name: "draft" extra`); YAML rejects both, so this must too.
    """
    if raw[:1] in {"'", '"'}:
        quote = raw[0]
        closing = raw.find(quote, 1)
        if closing == -1:
            return None
        trailing = raw[closing + 1 :].strip()
        if trailing and not trailing.startswith("#"):
            return None
        return raw[1:closing]
    if raw.startswith("#"):
        return ""
    head, sep, _ = raw.partition(" #")
    return head.rstrip() if sep else raw


def check_frontmatter_field(skill_md: Path, frontmatter_lines: list[str], field: str) -> None:
    """Require `field` as a top-level frontmatter key carrying a non-empty value.

    Only unindented keys count: an indented `name:` is nested under some other
    key and is not the field Cursor reads. A key with no value (`name:`,
    `name: ''`, `name: # TODO`) is reported rather than accepted.
    """
    prefix = f"{field}:"
    for i, line in enumerate(frontmatter_lines):
        if not line.startswith(prefix):
            continue
        value = scalar_value(line[len(prefix) :].strip())
        if value is None:
            fail(
                f"{skill_md.relative_to(REPO_ROOT)}: frontmatter `{field}` has a malformed "
                "quoted value (unterminated quote, or trailing text after the closing quote)"
            )
            return
        if value in BLOCK_SCALAR_INDICATORS:
            has_value = False
            for continuation in frontmatter_lines[i + 1 :]:
                if continuation and not continuation[0].isspace():
                    break  # dedented back to a sibling key — the block ended
                if continuation.strip():
                    has_value = True
                    break
        else:
            has_value = bool(value.strip())
        if not has_value:
            fail(f"{skill_md.relative_to(REPO_ROOT)}: frontmatter `{field}` field has no value")
        return
    fail(f"{skill_md.relative_to(REPO_ROOT)}: frontmatter missing required top-level `{field}` field")


def check_skill_frontmatter(skill_md: Path) -> None:
    text = skill_md.read_text()
    if not text.startswith("---\n"):
        fail(f"{skill_md.relative_to(REPO_ROOT)}: missing frontmatter (must start with `---`)")
        return
    lines = text.splitlines()
    # The closing delimiter must be a line that is exactly `---` — a line like
    # `---foo` is not a delimiter, and treating it as one lets malformed
    # frontmatter pass here and fail later during packaging.
    end = next((i for i, line in enumerate(lines[1:], start=1) if line.rstrip() == "---"), None)
    if end is None:
        fail(f"{skill_md.relative_to(REPO_ROOT)}: frontmatter is not closed with `---`")
        return
    frontmatter_lines = lines[1:end]
    for field in ("name", "description"):
        check_frontmatter_field(skill_md, frontmatter_lines, field)


def main() -> int:
    cursor_manifest_path = REPO_ROOT / ".cursor-plugin" / "plugin.json"
    claude_manifest_path = REPO_ROOT / ".claude-plugin" / "plugin.json"

    cursor_manifest = load_json(cursor_manifest_path)
    claude_manifest = load_json(claude_manifest_path)
    if cursor_manifest is None or claude_manifest is None:
        return report()

    for field in ("name", "description", "version", "license"):
        if field not in cursor_manifest:
            fail(f".cursor-plugin/plugin.json: missing required field `{field}`")
        elif not isinstance(cursor_manifest[field], str) or not cursor_manifest[field].strip():
            fail(
                f".cursor-plugin/plugin.json: `{field}` must be a non-empty string, "
                f"got {cursor_manifest[field]!r}"
            )

    cursor_version = cursor_manifest.get("version")
    claude_version = claude_manifest.get("version")
    if cursor_version != claude_version:
        fail(
            ".cursor-plugin/plugin.json version "
            f"({cursor_version!r}) does not match .claude-plugin/plugin.json version "
            f"({claude_version!r}) — bump both together"
        )

    skills_raw = cursor_manifest.get("skills")
    if skills_raw:
        skills_dir = resolve_relative(skills_raw, "skills")
        if skills_dir is not None:
            skill_files = sorted(skills_dir.glob("*/SKILL.md"))
            if not skill_files:
                fail(f".cursor-plugin/plugin.json: `skills` ({skills_raw!r}) contains no */SKILL.md files")
            for skill_md in skill_files:
                check_skill_frontmatter(skill_md)
    else:
        fail(".cursor-plugin/plugin.json: missing required field `skills`")

    mcp_raw = cursor_manifest.get("mcpServers")
    if mcp_raw:
        mcp_path = resolve_relative(mcp_raw, "mcpServers")
        if mcp_path is not None:
            mcp_data = load_json(mcp_path)
            if mcp_data is not None and not isinstance(mcp_data, dict):
                fail(f"{mcp_raw}: expected a JSON object, got {type(mcp_data).__name__}")
            elif mcp_data is not None and "mcpServers" not in mcp_data:
                fail(f"{mcp_raw}: expected a top-level `mcpServers` key (Cursor's wrapped shape)")
    else:
        fail(".cursor-plugin/plugin.json: missing required field `mcpServers`")

    logo_raw = cursor_manifest.get("logo")
    if logo_raw:
        resolve_relative(logo_raw, "logo")

    return report()


def report() -> int:
    if errors:
        print("Cursor package validation FAILED:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("Cursor package validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

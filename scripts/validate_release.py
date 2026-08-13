#!/usr/bin/env python3
"""Assert the release metadata moves when the shipped bundle moves.

WHY
---
`CHANGELOG.md:14-16` states the rule: installed users only pick up a release
when `version` is bumped, so bump it on every release including docs-only ones.
Nothing enforced it, and the existing parity check compares the manifests only
to each other — a comparison that two equally stale manifests satisfy perfectly.
This gate compares the version against the base ref instead, so a change to a
shipped file cannot merge without a bump.

WHAT IT CHECKS
--------------
1. Every host manifest declares the same `version` (`.claude-plugin/plugin.json`,
   `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `plugin.json`).
2. `CHANGELOG.md` has a `## [<version>]` heading for that version.
3. With `--base <ref>`: if any shipped file changed against that ref, the
   version must differ from the version at that ref.

Check 3 is the one with teeth, and it runs whenever a comparison ref is available:
the merge target for a pull request or the pre-push commit for a push. Checks 1
and 2 always run.

WHAT COUNTS AS SHIPPED
----------------------
Skills, README, assets, the manifests, and the MCP configs — the files an
installed user receives. Not `scripts/`, `.github/`, `docs/`, `schemas/`, or
`expected-tools.txt`: those are how the repo checks itself, and a CI fix should
not force a release. `CHANGELOG.md` is excluded too, so a typo fix in it does
not demand a version it would then have to document.

No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
SemVer = Tuple[int, int, int, Optional[Tuple[str, ...]]]

MANIFESTS = [
    Path(".claude-plugin/plugin.json"),
    Path(".codex-plugin/plugin.json"),
    Path(".cursor-plugin/plugin.json"),
    Path("plugin.json"),
]

# `agents/` is the plugin-level OpenAI metadata; per-skill `agents/openai.yaml`
# already falls under `skills/`.
SHIPPED_PREFIXES = ("skills/", "assets/", "agents/")
SHIPPED_FILES = {
    "README.md", "LICENSE", "mcp.json", ".mcp.json", ".app.json",
    ".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
    ".cursor-plugin/plugin.json", "plugin.json",
}

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def is_shipped(path: str) -> bool:
    return path in SHIPPED_FILES or path.startswith(SHIPPED_PREFIXES)


def parse_semver(raw: object, where: str) -> SemVer | None:
    if not isinstance(raw, str) or (match := SEMVER.fullmatch(raw)) is None:
        fail(f"{where}: `version` must be valid SemVer 2.0.0, got {raw!r}")
        return None
    major, minor, patch, prerelease, _build = match.groups()
    identifiers = tuple(prerelease.split(".")) if prerelease is not None else None
    return int(major), int(minor), int(patch), identifiers


def compare_semver(left: SemVer, right: SemVer) -> int:
    left_core, right_core = left[:3], right[:3]
    if left_core != right_core:
        return (left_core > right_core) - (left_core < right_core)

    left_pre, right_pre = left[3], right[3]
    if left_pre is None or right_pre is None:
        return (left_pre is None) - (right_pre is None)

    for left_id, right_id in zip(left_pre, right_pre):
        if left_id == right_id:
            continue
        left_numeric, right_numeric = left_id.isdigit(), right_id.isdigit()
        if left_numeric and right_numeric:
            return (int(left_id) > int(right_id)) - (int(left_id) < int(right_id))
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return (left_id > right_id) - (left_id < right_id)
    return (len(left_pre) > len(right_pre)) - (len(left_pre) < len(right_pre))


def git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True
        )
    except (OSError, UnicodeError) as exc:
        fail(f"git {' '.join(args)} could not run or decode its output ({exc})")
        return None
    return result.stdout if result.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        help=(
            "git ref to compare against (a PR base or pre-push commit). "
            "Omit to run checks 1-2 only."
        ),
    )
    args = parser.parse_args()

    versions: dict[str, str] = {}
    parsed_versions: dict[str, SemVer] = {}
    for rel in MANIFESTS:
        path = REPO_ROOT / rel
        try:
            raw = path.read_text()
        except FileNotFoundError:
            fail(f"{rel}: file not found")
            continue
        except (OSError, UnicodeError) as exc:
            fail(f"{rel}: could not be read ({exc})")
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            fail(f"{rel}: invalid JSON ({e})")
            continue
        if not isinstance(data, dict):
            fail(f"{rel}: expected a JSON object, got {type(data).__name__}")
            continue
        version = data.get("version")
        parsed = parse_semver(version, str(rel))
        if parsed is None:
            continue
        versions[str(rel)] = version
        parsed_versions[str(rel)] = parsed

    if len(set(versions.values())) > 1:
        listed = ", ".join(f"{k} = {v}" for k, v in sorted(versions.items()))
        fail(
            f"manifest versions disagree ({listed}) — all {len(MANIFESTS)} ship from "
            "this repo together"
        )
    if not versions:
        return report()

    version = next(iter(versions.values()))
    parsed_version = parsed_versions[next(iter(versions))]

    try:
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text()
    except (OSError, UnicodeError) as exc:
        fail(f"CHANGELOG.md: could not be read ({exc})")
        return report()
    if not re.search(rf"^## \[{re.escape(version)}\]", changelog, re.MULTILINE):
        fail(
            f"CHANGELOG.md has no `## [{version}]` entry. Every released version needs one — "
            "an unexplained version bump tells an installed user nothing about what changed."
        )

    if args.base:
        if git("rev-parse", "--verify", f"{args.base}^{{commit}}") is None:
            fail(
                f"base ref {args.base!r} is not available. Fetch it (actions/checkout with "
                "fetch-depth: 0) — silently skipping this check is how the gate stops gating."
            )
            return report()

        diff = git("diff", "--name-only", "-z", f"{args.base}...HEAD")
        if diff is None:
            fail(f"could not diff against {args.base}")
            return report()

        changed = sorted(p for p in diff.split("\0") if p and is_shipped(p))
        if changed:
            base_manifest = git("show", f"{args.base}:.claude-plugin/plugin.json")
            base_version: object = None
            parsed_base_version = None
            if base_manifest is None:
                fail(
                    f"could not read .claude-plugin/plugin.json at base {args.base}; "
                    "the version bump cannot be verified"
                )
            else:
                try:
                    base_data = json.loads(base_manifest)
                except json.JSONDecodeError as exc:
                    fail(
                        f".claude-plugin/plugin.json at base {args.base}: invalid JSON ({exc})"
                    )
                else:
                    if not isinstance(base_data, dict):
                        fail(
                            f".claude-plugin/plugin.json at base {args.base}: expected a JSON "
                            f"object, got {type(base_data).__name__}"
                        )
                    else:
                        base_version = base_data.get("version")
                        parsed_base_version = parse_semver(
                            base_version,
                            f".claude-plugin/plugin.json at base {args.base}",
                        )

            if (
                parsed_base_version is not None
                and compare_semver(parsed_version, parsed_base_version) <= 0
            ):
                listed = "\n      ".join(changed)
                fail(
                    f"shipped files changed but `version` {version} is not greater than "
                    f"{base_version} at {args.base}. Installed users would never receive "
                    "this change.\n"
                    f"    Bump all three manifests and add a CHANGELOG entry.\n"
                    f"    Changed:\n      {listed}"
                )
            elif parsed_base_version is not None:
                print(f"Version bumped {base_version} -> {version} for {len(changed)} shipped file(s).")
        else:
            print(f"No shipped files changed against {args.base}; no bump required.")

    if not errors:
        print(
            f"Release validation passed: version {version} consistent across "
            f"{len(MANIFESTS)} manifests + CHANGELOG."
        )
    return report()


def report() -> int:
    if errors:
        print("Release validation FAILED:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

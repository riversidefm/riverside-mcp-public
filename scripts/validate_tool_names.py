#!/usr/bin/env python3
"""Assert every tool name in the shipped docs exists on the live MCP surface.

WHY
---
`claude plugin validate --strict` reads exactly one file
(`.claude-plugin/plugin.json`); `validate_cursor_package.py` reads manifests and
skill *frontmatter*, while `validate_skill_references.py` checks the safety of
the local link graph. None compares callable names in shipped Markdown with the
reviewed live-surface snapshot. This script closes that gap in both directions:
a namespace can be renamed under the bundle, and a whole backend can be added
to or removed from the federated surface.

WHAT IT CHECKS
--------------
Every tool-name-shaped token in `skills/**/*.md` and `README.md` is either

  1. a name in `expected-tools.txt` (the reviewed snapshot of the live surface),
  2. a prefix glob — bare `editing_*` or nested `editing_remove_*` — whose
     prefix covers at least one such name,
  3. an explicitly allowlisted non-tool identifier in NOT_A_TOOL below, or
  4. an explicitly allowlisted non-tool glob in NOT_A_TOOL_GLOBS below.

Anything else fails the build.

WHY STRICT-BY-DEFAULT
---------------------
Rule 3 means a new snake_case *value* in a skill needs a one-line allowlist
entry. That friction is deliberate. The looser alternative — only flag tokens
that look confusable with a known tool — misses the real cases: `modify_crop`
is a batch operation and not a tool, and nothing about its shape says so. A
gate that needs a heuristic to decide what to check is a gate that will miss
the next incident. Making every unknown identifier a build failure with a
required written reason is the only version that cannot silently under-check.

GLOB SHAPE
----------
A glob is an identifier whose last character before the `*` is `_`: `editing_*`,
`editing_remove_*`, `platform-mcp-mcp_*`. The prefix is everything up to and
including that underscore, and it has to cover at least one name in
`expected-tools.txt`.

That trailing underscore is the entire parsing boundary, and it is load-bearing
in both directions.

Requiring it is what makes a BARE namespace glob visible at all. Before 0.5.1
the scanner looked for a glob only in the two characters that FOLLOWED a token,
and TOKEN has to end in an alphanumeric — so `editing_remove_*` was seen (token
`editing_remove`, trailing `_*`) while `editing_*` and `platform-mcp-mcp_*`
matched no token whatsoever and were never scanned. A skill could name every
tool in a namespace that does not exist and nothing would flag it. Verifying a
bare namespace glob is precisely what this file exists to do.

Requiring it is also what keeps markdown emphasis out of the glob parser.
`*editing_batch*` and `**editing_batch**` are an italicised and a bolded tool
name, not globs — neither ends in `_`, so both fall through to the plain-token
scan and are checked as names. A partial-segment glob (`editing_remo*`) is
deliberately not a glob either: it is scanned as the plain token
`editing_remo` and fails as an unknown name, which is the safe direction.

Globs are matched first and their spans recorded, so the plain-token scan skips
anything inside one. A bad glob is reported once, as a glob.

TOKEN SHAPE
-----------
Candidates are lowercase only. Every name on the live surface is lowercase, so
SCREAMING_CASE tokens (`FAILED_PRECONDITION`, `YOUTUBE_SHORTS`) and mixed-case
ones (`New_York`) are enum values and parameters, not tools. That assumption is
asserted against `expected-tools.txt` at startup rather than trusted: if a
refresh ever introduces a tool name with an uppercase letter, this script fails
loudly instead of quietly scanning less than it claims to.

SCOPE
-----
`CHANGELOG.md` is deliberately NOT scanned. It is a historical record, and a
released entry has to keep naming the tools that release actually shipped even
after the surface moves under it. Rewriting history to satisfy a linter would be
worse than the problem. Nothing in the changelog is instruction to a model, so
a stale name there cannot cause a failed tool call — which is the only thing
this gate exists to prevent.

No third-party dependencies — stdlib only, matching validate_cursor_package.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "expected-tools.txt"

SCANNED = ["skills/**/*.md", "README.md"]

# Lowercase identifier containing at least one internal underscore. Must end in
# an alphanumeric so a trailing `_` (as in the glob `editing_remove_*`) is not
# swallowed into the token — globs are matched separately, by GLOB, and their
# spans are skipped by the token scan.
TOKEN = re.compile(r"[a-z][a-z0-9.\-]*_[a-z0-9._\-]*[a-z0-9]")

# A prefix glob: a tool-shaped identifier ending in `_*`. See GLOB SHAPE above
# for why the trailing underscore is required rather than optional.
#
# The lookbehind anchors the match to the start of an identifier, so a
# hypothetical `x_editing_*` is one glob with prefix `x_editing_` and fails,
# rather than yielding an inner `editing_*` that would wrongly pass.
GLOB = re.compile(r"(?<![a-z0-9._\-])[a-z][a-z0-9.\-]*(?:_[a-z0-9.\-]+)*_\*")

# Identifiers that match the tool-name shape but are not tools. Every entry
# needs a reason: the reason is what a reviewer checks when the list grows.
NOT_A_TOOL: dict[str, str] = {
    # Operations *inside* editing_batch, not tools in their own right. They are
    # referenced in prose but are not on the external tool surface; the skill is
    # correct to name them, as long as it frames them as batch ops.
    "change_layout": "editing_batch operation",
    "modify_crop": "editing_batch operation",
    # video-editing/SKILL.md deliberately names the retired doubled-prefix
    # spelling to say it is NOT callable. The callable tool is `editing_batch`
    # (editing-mcp-v2 ENG-640 renamed the registration from `editing_batch` to
    # `batch`, so the gateway's `editing_` namespace no longer doubles it), and
    # that name is in expected-tools.txt like any other tool.
    "editing_editing_batch": "named as a non-callable name, on purpose",
    # Parameter values quoted in the skills.
    "smart_mutes": "editing_restore_audio_cleanup cleanup= value",
    "editorial_strategy": "editing_get_editing_guide mode value",
    "boundary_range": "transcript selection kind",
    "time_range": "transcript selection kind",
    "word_range": "transcript selection kind",
    "bottom_right": "overlay position value",
    "top_left": "overlay position value",
    # Literal example identifiers in worked examples.
    "tok_123": "example id literal",
    "yt_456": "example id literal",
}

# Globs that have the shape but name no callable namespace. Keyed by the exact
# expression as written in the docs, and every entry needs a reason — same rule
# as NOT_A_TOOL, for the same reason: a list is only reviewable if each line
# says why it is on it.
#
# Do NOT put a real namespace here. `editing_*` and `platform-mcp-mcp_*` are the
# references this gate exists to verify; allowlisting either would reopen the
# hole described under GLOB SHAPE.
NOT_A_TOOL_GLOBS: dict[str, str] = {
    # content-discovery/SKILL.md describes the pagination envelope shared by
    # platform_list_edits, platform_list_studios and the rest. `list` is a verb
    # there, not a federated namespace: the live listing tools are
    # `platform_list_*`, and no tool name on any surface begins with `list_`.
    "list_*": "generic family description, not a callable namespace",
}

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def load_expected() -> set[str]:
    if not MANIFEST.exists():
        fail(f"{MANIFEST.name}: file not found — the tool-name gate cannot run without it")
        return set()
    names = {
        line.strip()
        for line in MANIFEST.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if not names:
        fail(f"{MANIFEST.name}: contains no tool names")
        return set()
    # The scanner only looks at lowercase tokens. Assert that is still a
    # complete view of the surface rather than assuming it.
    uppercase = sorted(n for n in names if n != n.lower())
    if uppercase:
        fail(
            f"{MANIFEST.name}: {uppercase} contain uppercase characters. This scanner "
            "only considers lowercase tokens to be tool references, so those names "
            "would never be checked. Widen TOKEN and this assertion together."
        )
    return names


def suggestion(token: str, expected: set[str]) -> str:
    """`platform-mcp-mcp_list_studios` -> 'did you mean platform_list_studios?'

    Matches on the part after the first underscore, which is what survives a
    namespace/prefix change — the exact failure this gate exists to catch. It
    is symmetric on purpose: the prefix has already moved in both directions
    once, and the suggestion has to be useful whichever way it moves next.
    """
    _, _, suffix = token.partition("_")
    hits = sorted(n for n in expected if n.partition("_")[2] == suffix)
    if not hits:
        return ""
    return f" Did you mean {' or '.join(hits)}?"


def glob_suggestion(prefix: str, expected: set[str]) -> str:
    """`platform-mcp-mcp_*` -> 'did you mean platform_*?'

    The same job as suggestion(), for a prefix instead of a whole name: keep
    whatever follows the first underscore and re-home it under a live
    namespace. Candidates are restricted to namespaces that are a prefix of the
    written one or vice versa, because that is what a namespace rename looks
    like in either direction (`platform` -> `platform-mcp-mcp` and back). An
    unrelated namespace gets no guess rather than a list of all five.
    """
    written_ns, _, rest = prefix.partition("_")
    live = {name.split("_", 1)[0] for name in expected}
    near = (
        ns
        for ns in live
        if ns != written_ns
        and (ns.startswith(written_ns) or written_ns.startswith(ns))
    )
    hits = sorted(
        f"{ns}_{rest}"
        for ns in near
        if any(name.startswith(f"{ns}_{rest}") for name in expected)
    )
    if not hits:
        return ""
    return f" Did you mean {' or '.join(hit + '*' for hit in hits)}?"


def scan_file(path: Path, expected: set[str], namespaces: set[str]) -> None:
    text = path.read_text()
    rel = path.relative_to(REPO_ROOT)
    line_starts = [0]
    for line in text.splitlines(keepends=True):
        line_starts.append(line_starts[-1] + len(line))

    def line_of(pos: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid
        return lo + 1

    # Globs first. Their spans are then off-limits to the token scan below, so
    # `editing_missing_*` is one glob diagnostic and not also a bad-token one.
    glob_spans: list[tuple[int, int]] = []
    for match in GLOB.finditer(text):
        glob = match.group(0)
        glob_spans.append(match.span())
        if glob in NOT_A_TOOL_GLOBS:
            continue
        prefix = glob[:-1]
        if any(name.startswith(prefix) for name in expected):
            continue
        fail(
            f"{rel}:{line_of(match.start())}: glob `{glob}` matches no tool in "
            f"{MANIFEST.name}.{glob_suggestion(prefix, expected)} If it names a "
            "real namespace, the manifest is stale — refresh it in its own "
            "reviewed PR. If it is prose and not a callable namespace, add the "
            "exact glob to NOT_A_TOOL_GLOBS in scripts/validate_tool_names.py "
            "with a reason."
        )

    for match in TOKEN.finditer(text):
        if any(match.start() < end and start < match.end() for start, end in glob_spans):
            continue
        token = match.group(0)
        line = line_of(match.start())

        if token in expected or token in NOT_A_TOOL:
            continue

        if any(token.startswith(ns) for ns in namespaces):
            fail(
                f"{rel}:{line}: `{token}` is in a live namespace but is not a live "
                f"tool.{suggestion(token, expected)}"
            )
        else:
            fail(
                f"{rel}:{line}: `{token}` is not in {MANIFEST.name}."
                f"{suggestion(token, expected)} If it is a tool, the manifest is "
                "stale — refresh it in its own reviewed PR. If it is not a tool, "
                "add it to NOT_A_TOOL in scripts/validate_tool_names.py with a reason."
            )


def main() -> int:
    expected = load_expected()
    if errors:
        return report()

    # `platform_get_edit` -> namespace `platform_`. Split on the FIRST
    # underscore, so a hyphenated namespace stays intact.
    #
    # The live namespaces are currently plain, but the gateway may derive a
    # hyphenated namespace when an explicit target name is absent. Keep that
    # shape intact so drift in either direction is reported accurately.
    namespaces = {name.split("_", 1)[0] + "_" for name in expected}

    paths: list[Path] = []
    for pattern in SCANNED:
        paths.extend(sorted(REPO_ROOT.glob(pattern)))
    if not paths:
        fail(f"no files matched {SCANNED} — the gate would pass vacuously")
        return report()

    for path in paths:
        scan_file(path, expected, namespaces)

    if not errors:
        print(
            f"Tool-name validation passed: {len(paths)} files checked against "
            f"{len(expected)} live tool names."
        )
    return report()


def report() -> int:
    if errors:
        print("Tool-name validation FAILED:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            f"\n{MANIFEST.name} is a checked-in snapshot, not a live query — CI has no "
            "OAuth credential for the gateway. See that file's header for how to refresh it.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Validate the local reference graph shipped by every bundled skill.

A skill is loaded in two stages: its ``SKILL.md`` is always in context, while
files under ``references/`` are read only when the model follows a link. This
gate makes that second stage portable across every supported host by requiring:

* every local Markdown link to name a regular, non-symlinked file inside the
  owning skill;
* every ``references/*.md`` file to be linked directly from its ``SKILL.md``;
* reference files to stay one level deep and contain no further local links.

Code examples are not live links, and external URLs or same-file fragments are
outside the local graph. Markdown image destinations are live local resources,
so they receive the same existence, containment, and symlink checks as links.

No third-party dependencies are used, keeping the CI gate host-neutral.
"""

from __future__ import annotations

import re
import stat
import sys
import urllib.parse
from html.entities import html5
from pathlib import Path, PurePosixPath
from typing import NamedTuple, Optional


RESOLUTION_ERRORS = (OSError, RuntimeError, ValueError)
try:
    REPO_ROOT = Path(__file__).resolve().parent.parent
except RESOLUTION_ERRORS as error:
    print(
        f"validate_skill_references.py: validator location cannot be resolved "
        f"({error})",
        file=sys.stderr,
    )
    raise SystemExit(1)

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


# A Markdown label character is either a backslash escape or anything other
# than a closing bracket. Sharing this grammar prevents one link form from
# accepting labels that another form silently ignores.
LABEL_ATOM = r"(?:\\.|[^\\\]])"

# Reference-style usages, ``[text][id]`` and ``![alt][id]``. A blank second
# label is the collapsed form, where the visible label is also the id.
REFERENCE_USAGE = re.compile(
    rf"(!?)\[({LABEL_ATOM}+)\]\[({LABEL_ATOM}*)\]"
)

# Shortcut reference usages, ``[label]`` and ``![label]``. These are only live
# when a matching definition exists, and matches that belong to another
# Markdown form are excluded below.
SHORTCUT_USAGE = re.compile(rf"(!?)\[({LABEL_ATOM}+)\]")

# A link-reference definition, ``[label]: target "optional title"``. A
# definition has no link/image kind by itself; its usages supply that meaning.
LINK_DEFINITION = re.compile(
    rf"^[ ]{{0,3}}\[({LABEL_ATOM}+)\]:[ \t]*"
    rf"(?:<((?:\\.|[^<>\n])*)>|((?!<)(?:\\.|[^ \t\n])+))"
    rf"(?:[ \t]+(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|"
    rf"\((?:\\.|[^)])*\)))?[ \t]*$",
    re.MULTILINE,
)

# Opening or closing fenced-code delimiter, indented at most three spaces.
CODE_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
BACKTICK_RUN = re.compile(r"`+")

MARKDOWN_ESCAPE = re.compile(
    r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])"
)
CHARACTER_REFERENCE = re.compile(
    r"&(?:#[xX][0-9A-Fa-f]{1,6}|#[0-9]{1,7}|[A-Za-z][A-Za-z0-9]{1,31});"
)


class MarkdownDestination(NamedTuple):
    line: int
    destination: str
    is_link: bool
    is_image: bool


class InlineDestination(NamedTuple):
    start: int
    end: int
    destination_start: int
    destination: str
    is_image: bool


class FilesystemEntry(NamedTuple):
    path: Path
    mode: int


def blank_code_spans(line: str) -> str:
    """Blank complete inline-code spans while preserving every offset."""
    runs = [match.span() for match in BACKTICK_RUN.finditer(line)]
    chars = list(line)
    opener = 0
    while opener < len(runs):
        start, end = runs[opener]
        closer = next(
            (
                index
                for index in range(opener + 1, len(runs))
                if runs[index][1] - runs[index][0] == end - start
            ),
            None,
        )
        if closer is None:
            opener += 1
            continue
        for index in range(start, runs[closer][1]):
            chars[index] = " "
        opener = closer + 1
    return "".join(chars)


def blank_code(text: str) -> str:
    """Blank fenced and inline code while preserving line and byte offsets."""
    blanked: list[str] = []
    fence: Optional[str] = None
    for line in text.split("\n"):
        match = CODE_FENCE.match(line)
        if fence is not None:
            if (
                match
                and match.group(1)[0] == fence[0]
                and len(match.group(1)) >= len(fence)
                and not match.group(2).strip()
            ):
                fence = None
            blanked.append(" " * len(line))
        elif match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
            fence = match.group(1)
            blanked.append(" " * len(line))
        else:
            blanked.append(blank_code_spans(line))
    return "\n".join(blanked)


def unescape_markdown(value: str) -> str:
    """Remove CommonMark backslashes before escapable punctuation."""
    return MARKDOWN_ESCAPE.sub(r"\1", value)


def decode_character_references(value: str) -> str:
    """Decode the HTML character references CommonMark permits in URLs."""
    def decode(match: re.Match[str]) -> str:
        reference = match.group(0)
        if not reference.startswith("&#"):
            return html5.get(reference[1:], reference)

        numeric = reference[2:-1]
        base = 10
        if numeric.startswith(("x", "X")):
            numeric = numeric[1:]
            base = 16
        code_point = int(numeric, base)
        if (
            code_point == 0
            or code_point > 0x10FFFF
            or 0xD800 <= code_point <= 0xDFFF
        ):
            return "\N{REPLACEMENT CHARACTER}"
        return chr(code_point)

    return CHARACTER_REFERENCE.sub(decode, value)


def normalized_label(label: str) -> str:
    """Normalize a Markdown reference label for case-insensitive lookup."""
    return " ".join(unescape_markdown(label).split()).casefold()


def is_escaped(text: str, position: int) -> bool:
    """Return whether the character at ``position`` has an odd slash prefix."""
    backslashes = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        backslashes += 1
        position -= 1
    return bool(backslashes % 2)


def closing_bracket(text: str, opener: int) -> Optional[int]:
    """Find the matching unescaped closing bracket for one link label."""
    depth = 0
    position = opener + 1
    while position < len(text):
        character = text[position]
        if character == "\\" and position + 1 < len(text):
            position += 2
            continue
        if character == "[":
            depth += 1
        elif character == "]":
            if depth == 0:
                return position
            depth -= 1
        position += 1
    return None


def inline_close(text: str, position: int) -> Optional[int]:
    """Return the end offset after an optional title and closing ``)``."""
    while position < len(text) and text[position].isspace():
        position += 1
    if position >= len(text):
        return None
    if text[position] == ")":
        return position + 1

    opener = text[position]
    if opener not in ('"', "'", "("):
        return None
    closer = ")" if opener == "(" else opener
    depth = 0
    position += 1
    while position < len(text):
        character = text[position]
        if character == "\\" and position + 1 < len(text):
            position += 2
            continue
        if opener == "(" and character == "(":
            depth += 1
        elif character == closer:
            if depth == 0:
                position += 1
                break
            depth -= 1
        elif character == "\n":
            return None
        position += 1
    else:
        return None

    while position < len(text) and text[position].isspace():
        position += 1
    if position < len(text) and text[position] == ")":
        return position + 1
    return None


def parse_inline_destination(
    text: str, opening_paren: int
) -> Optional[InlineDestination]:
    """Parse one inline destination, including balanced and ``<...>`` forms."""
    position = opening_paren + 1
    while position < len(text) and text[position].isspace():
        position += 1
    if position >= len(text):
        return None

    if text[position] == "<":
        destination_start = position + 1
        position = destination_start
        while position < len(text):
            character = text[position]
            if character == "\\" and position + 1 < len(text):
                position += 2
                continue
            if character == "\n":
                return None
            if character == "<":
                return None
            if character == ">":
                end = inline_close(text, position + 1)
                if end is None:
                    return None
                return InlineDestination(
                    opening_paren,
                    end,
                    destination_start,
                    text[destination_start:position],
                    False,
                )
            position += 1
        return None

    destination_start = position
    depth = 0
    while position < len(text):
        character = text[position]
        if character == "\\" and position + 1 < len(text):
            position += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return InlineDestination(
                    opening_paren,
                    position + 1,
                    destination_start,
                    text[destination_start:position],
                    False,
                )
            depth -= 1
        elif character.isspace():
            if depth:
                return None
            end = inline_close(text, position)
            if end is None:
                return None
            return InlineDestination(
                opening_paren,
                end,
                destination_start,
                text[destination_start:position],
                False,
            )
        position += 1
    return None


def inline_destinations(text: str) -> list[InlineDestination]:
    """Scan inline Markdown links without truncating escaped or nested syntax."""
    matches: list[InlineDestination] = []
    position = 0
    while position < len(text):
        opener = text.find("[", position)
        if opener < 0:
            break
        position = opener + 1
        if is_escaped(text, opener):
            continue

        closer = closing_bracket(text, opener)
        if closer is None or closer + 1 >= len(text) or text[closer + 1] != "(":
            continue
        parsed = parse_inline_destination(text, closer + 1)
        if parsed is None:
            continue

        is_image = (
            opener > 0
            and text[opener - 1] == "!"
            and not is_escaped(text, opener - 1)
        )
        matches.append(
            InlineDestination(
                opener - 1 if is_image else opener,
                parsed.end,
                parsed.destination_start,
                parsed.destination,
                is_image,
            )
        )
        position = parsed.end
    return matches


def markdown_destinations(path: Path) -> list[MarkdownDestination]:
    """Return local-target candidates with source lines and rendered kinds."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        fail(
            f"{path.relative_to(REPO_ROOT)}: cannot be read as UTF-8 ({error})"
        )
        return []
    text = blank_code(raw)
    destinations: list[MarkdownDestination] = []

    inline_matches = inline_destinations(text)
    reference_matches = list(REFERENCE_USAGE.finditer(text))
    definition_matches = list(LINK_DEFINITION.finditer(text))

    for match in inline_matches:
        destination = match.destination
        if not destination:
            continue
        line = text.count("\n", 0, match.destination_start) + 1
        destinations.append(
            MarkdownDestination(
                line, destination, not match.is_image, match.is_image
            )
        )

    usage_kinds: dict[str, set[str]] = {}
    for match in reference_matches:
        label = match.group(3) or match.group(2)
        kind = "image" if match.group(1) else "link"
        usage_kinds.setdefault(normalized_label(label), set()).add(kind)

    defined_labels = {
        normalized_label(match.group(1)) for match in definition_matches
    }
    occupied_spans = [
        (match.start, match.end) for match in inline_matches
    ] + [
        match.span()
        for matches in (reference_matches, definition_matches)
        for match in matches
    ]
    for match in SHORTCUT_USAGE.finditer(text):
        if any(
            match.start() < end and start < match.end()
            for start, end in occupied_spans
        ):
            continue
        label = normalized_label(match.group(2))
        if label not in defined_labels:
            continue
        kind = "image" if match.group(1) else "link"
        usage_kinds.setdefault(label, set()).add(kind)

    for match in definition_matches:
        kinds = usage_kinds.get(normalized_label(match.group(1)))
        if not kinds:
            continue
        destination_group = 2 if match.group(2) is not None else 3
        destination = match.group(destination_group)
        if not destination:
            continue
        line = text.count("\n", 0, match.start(destination_group)) + 1
        destinations.append(
            MarkdownDestination(
                line,
                destination,
                "link" in kinds,
                "image" in kinds,
            )
        )

    return sorted(destinations)


def local_destination(destination: str) -> Optional[str]:
    """Return the decoded local path, or ``None`` for a non-local target."""
    rendered = decode_character_references(unescape_markdown(destination))
    split = urllib.parse.urlsplit(rendered)
    if split.scheme.casefold() == "file":
        raise ValueError("file URI targets are not allowed")
    if split.scheme or split.netloc:
        return None
    if not split.path:
        return None
    return urllib.parse.unquote(split.path)


def directory_entries(path: Path) -> Optional[list[Path]]:
    """List a directory or record a fail-closed diagnostic."""
    try:
        return sorted(path.iterdir())
    except OSError as error:
        fail(
            f"{path.relative_to(REPO_ROOT)}: directory cannot be read ({error})"
        )
        return None


def tree_entries(root: Path) -> list[FilesystemEntry]:
    """Walk a directory without following symlinks or suppressing read errors."""
    found: list[FilesystemEntry] = []
    pending = [root]
    while pending:
        current = pending.pop()
        entries = directory_entries(current)
        if entries is None:
            continue
        for entry in entries:
            try:
                mode = entry.lstat().st_mode
            except OSError as error:
                fail(
                    f"{entry.relative_to(REPO_ROOT)}: path cannot be inspected "
                    f"({error})"
                )
                continue
            found.append(FilesystemEntry(entry, mode))
            if stat.S_ISDIR(mode):
                pending.append(entry)
    return sorted(found, key=lambda entry: entry.path)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def first_symlink(path: Path, root: Path) -> Optional[Path]:
    """Return the first symlink in ``path`` below ``root``, if one exists."""
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(mode):
            return current
    return None


def normalized_local_target(
    source: Path, decoded: str, skill_root: Path
) -> Optional[Path]:
    """Apply POSIX parent segments without allowing escape from ``skill_root``."""
    parts = list(source.parent.relative_to(skill_root).parts)
    for part in PurePosixPath(decoded).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return skill_root.joinpath(*parts)


def resolved_without_diagnostic(path: Path) -> Optional[Path]:
    """Resolve a path already rejected for another reason, if it is valid."""
    try:
        return path.resolve()
    except RESOLUTION_ERRORS:
        return None


def fail_invalid_path(
    source: Path, line: int, destination: str, error: BaseException
) -> None:
    where = f"{source.relative_to(REPO_ROOT)}:{line}"
    fail(
        f"{where}: link {destination!r} is not a valid local path ({error}). "
        "Use a relative path containing valid filesystem characters."
    )


def fail_symlink(
    source: Path, line: int, destination: str, symlink: Path
) -> None:
    where = f"{source.relative_to(REPO_ROOT)}:{line}"
    fail(
        f"{where}: link target {destination!r} uses symlink "
        f"{symlink.relative_to(REPO_ROOT)}. Bundled skill references must "
        "be regular files reached without symlinks."
    )


def check_link(
    source: Path, line: int, destination: str, skill_root: Path
) -> Optional[Path]:
    """Validate one link and return the resolved local target when present."""
    try:
        decoded = local_destination(destination)
    except ValueError as error:
        fail_invalid_path(source, line, destination, error)
        return None
    if decoded is None:
        return None

    where = f"{source.relative_to(REPO_ROOT)}:{line}"
    decoded_path = PurePosixPath(decoded)
    unresolved_target = source.parent / decoded

    if decoded_path.is_absolute():
        fail(
            f"{where}: link {destination!r} is an absolute path. A skill is "
            "installed under a path it cannot predict, so only relative links "
            "can resolve."
        )
        return resolved_without_diagnostic(unresolved_target)

    try:
        lexical_target = normalized_local_target(source, decoded, skill_root)
    except RESOLUTION_ERRORS as error:
        fail_invalid_path(source, line, destination, error)
        return None
    if lexical_target is None:
        fail(
            f"{where}: link {destination!r} uses `..` to point outside its "
            "owning skill. A bundled skill has to be self-contained."
        )
        return resolved_without_diagnostic(unresolved_target)

    try:
        symlink = first_symlink(lexical_target, skill_root)
        if symlink is not None:
            fail_symlink(source, line, destination, symlink)
            return None
        target = lexical_target.resolve()
        if not is_within(target, skill_root):
            fail(
                f"{where}: link {destination!r} resolves outside its owning skill "
                f"({skill_root.name}). A bundled skill has to be self-contained."
            )
        elif not target.exists():
            fail(f"{where}: link target {destination!r} does not exist")
        elif not target.is_file():
            fail(f"{where}: link target {destination!r} is not a regular file")
    except RESOLUTION_ERRORS as error:
        fail_invalid_path(source, line, destination, error)
        return None
    return target


def check_reference_destinations(
    reference: Path, references_root: Path, skill_root: Path
) -> None:
    """Validate images and reject links in a terminal reference file."""
    rel = reference.relative_to(REPO_ROOT)
    for found in markdown_destinations(reference):
        if found.is_image:
            check_link(reference, found.line, found.destination, skill_root)
        if not found.is_link:
            continue

        try:
            decoded = local_destination(found.destination)
        except ValueError as error:
            fail_invalid_path(reference, found.line, found.destination, error)
            continue
        if decoded is None:
            continue
        target: Optional[Path] = None
        try:
            lexical_target = None
            if not PurePosixPath(decoded).is_absolute():
                lexical_target = normalized_local_target(
                    reference, decoded, skill_root
                )
            if lexical_target is not None:
                symlink = first_symlink(lexical_target, skill_root)
                if symlink is not None:
                    fail_symlink(
                        reference, found.line, found.destination, symlink
                    )
                    continue
                target = lexical_target.resolve()
        except RESOLUTION_ERRORS as error:
            fail_invalid_path(reference, found.line, found.destination, error)
            continue
        if target is not None and is_within(target, references_root):
            fail(
                f"{rel}:{found.line}: reference-to-reference link "
                f"{found.destination!r}. "
                "Only SKILL.md may link a reference: a chain buries content one "
                "hop further than the model is told to look."
            )
        else:
            fail(
                f"{rel}:{found.line}: link {found.destination!r} out of a "
                "reference. A "
                "reference is where progressive disclosure ends; it may not "
                "link another local file."
            )


def check_skill_references(skill_md: Path) -> None:
    """Validate local links and direct one-level references for one skill."""
    try:
        symlink = first_symlink(skill_md, REPO_ROOT)
    except RESOLUTION_ERRORS as error:
        fail(
            f"{skill_md}: bundled skill path cannot be inspected ({error})"
        )
        return
    if symlink is not None:
        fail(
            f"{skill_md.parent.relative_to(REPO_ROOT)}: skill directory or "
            f"SKILL.md uses symlink {symlink.relative_to(REPO_ROOT)}. Bundled "
            "skills must be stored directly under skills/."
        )
        return
    try:
        skill_root = skill_md.parent.resolve()
    except RESOLUTION_ERRORS as error:
        fail(
            f"{skill_md.relative_to(REPO_ROOT)}: owning skill directory cannot "
            f"be resolved ({error})"
        )
        return
    linked: set[Path] = set()
    for found in markdown_destinations(skill_md):
        target = check_link(skill_md, found.line, found.destination, skill_root)
        if found.is_link and target is not None:
            linked.add(target)

    references_dir = skill_md.parent / "references"
    try:
        references_mode = references_dir.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as error:
        fail(
            f"{references_dir.relative_to(REPO_ROOT)}: path cannot be inspected "
            f"({error})"
        )
        return
    if stat.S_ISLNK(references_mode):
        fail(
            f"{references_dir.relative_to(REPO_ROOT)}: references directory is a "
            "symlink. Bundled skill references must be stored directly in the "
            "owning skill."
        )
        return
    if not stat.S_ISDIR(references_mode):
        return

    try:
        references_root = references_dir.resolve()
    except RESOLUTION_ERRORS as error:
        fail(
            f"{references_dir.relative_to(REPO_ROOT)}: references directory "
            f"cannot be resolved ({error})"
        )
        return
    for found_entry in tree_entries(references_dir):
        entry = found_entry.path
        mode = found_entry.mode
        rel = entry.relative_to(REPO_ROOT)
        if stat.S_ISLNK(mode):
            fail(
                f"{rel}: reference target is a symlink. Bundled skill references "
                "must be regular files reached without symlinks."
            )
            continue
        if not stat.S_ISREG(mode):
            continue
        if entry.parent != references_dir:
            fail(
                f"{rel}: references may only be one level deep "
                "(`references/*.md`); move it directly into references/."
            )
            continue
        if entry.suffix != ".md":
            continue
        try:
            resolved_entry = entry.resolve()
        except RESOLUTION_ERRORS as error:
            fail(f"{rel}: reference target cannot be resolved ({error})")
            continue
        if resolved_entry not in linked:
            fail(
                f"{rel}: orphan reference — no link in "
                f"{skill_md.relative_to(REPO_ROOT)} points at it, so nothing "
                "would ever load it."
            )
        check_reference_destinations(entry, references_root, skill_root)


def report() -> int:
    if errors:
        print("Skill reference validation FAILED:\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    skills_dir = REPO_ROOT / "skills"
    skill_files: list[Path] = []
    skill_entries = directory_entries(skills_dir)
    if skill_entries is None:
        return report()
    for entry in skill_entries:
        try:
            mode = entry.lstat().st_mode
        except OSError as error:
            fail(
                f"{entry.relative_to(REPO_ROOT)}: path cannot be inspected "
                f"({error})"
            )
            continue
        if stat.S_ISLNK(mode):
            try:
                target_mode = entry.stat().st_mode
            except OSError as error:
                fail(
                    f"{entry.relative_to(REPO_ROOT)}: symlink target cannot be "
                    f"inspected ({error})"
                )
                continue
            if stat.S_ISDIR(target_mode):
                fail(
                    f"{entry.relative_to(REPO_ROOT)}: skill directory is a "
                    "symlink. Bundled skills must be stored directly under "
                    "skills/."
                )
            continue
        if not stat.S_ISDIR(mode):
            continue
        children = directory_entries(entry)
        if children is None:
            continue
        skill_files.extend(child for child in children if child.name == "SKILL.md")
    if not skill_files:
        fail("skills/: no */SKILL.md files found; reference validation cannot run")
        return report()

    for skill_md in skill_files:
        check_skill_references(skill_md)

    if not errors:
        print(
            f"Skill reference validation passed: {len(skill_files)} bundled "
            "skills checked."
        )
    return report()


if __name__ == "__main__":
    sys.exit(main())

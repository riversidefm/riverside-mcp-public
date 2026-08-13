from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_tool_names as validator  # noqa: E402


# A miniature stand-in for expected-tools.txt: two live namespaces, one with a
# nested `editing_remove_` family. Fixtures stay this small on purpose — a
# failure should name the rule that broke, not the shipped snapshot.
LIVE_TOOLS = (
    "editing_remove_fillers\n"
    "editing_remove_pauses\n"
    "editing_set_captions\n"
    "platform_list_studios\n"
)

# Only `platform_` is live here, so a stale deployment-derived namespace has
# exactly one plausible correction to suggest.
PLATFORM_ONLY = "platform_list_studios\nplatform_get_studio\n"


class ToolNameValidatorTests(unittest.TestCase):
    def run_validator(
        self, manifest: str, files: dict[str, str]
    ) -> tuple[int, list[str]]:
        """Run the whole gate over a throwaway repo containing exactly these files."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = root / "expected-tools.txt"
            manifest_path.write_text(manifest)
            for rel, body in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body)

            validator.errors.clear()
            with (
                mock.patch.object(validator, "REPO_ROOT", root),
                mock.patch.object(validator, "MANIFEST", manifest_path),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                status = validator.main()
            return status, list(validator.errors)

    # --- globs -----------------------------------------------------------

    def test_bare_namespace_glob_passes_when_a_live_tool_shares_the_prefix(self) -> None:
        status, errors = self.run_validator(
            LIVE_TOOLS,
            {"README.md": "The `editing_*` family is revision-aware.\n"},
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_nested_prefix_glob_passes_when_a_live_tool_shares_the_prefix(self) -> None:
        status, errors = self.run_validator(
            LIVE_TOOLS,
            {"README.md": "Use `editing_remove_*` to clean up speech.\n"},
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_nested_glob_fails_when_no_live_tool_shares_the_prefix(self) -> None:
        status, errors = self.run_validator(
            LIVE_TOOLS,
            {"README.md": "Use `editing_missing_*` to clean up speech.\n"},
        )

        self.assertEqual(1, status)
        self.assertTrue(
            any("`editing_missing_*`" in error for error in errors), errors
        )
        self.assertTrue(any("matches no tool" in error for error in errors), errors)

    def test_stale_namespace_glob_fails_and_suggests_the_live_namespace(self) -> None:
        status, errors = self.run_validator(
            PLATFORM_ONLY,
            {"README.md": "Call the `platform-mcp-mcp_*` tools to browse.\n"},
        )

        self.assertEqual(1, status)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("`platform-mcp-mcp_*`", errors[0])
        self.assertIn("platform_*", errors[0])

    def test_allowlisted_prose_glob_passes_for_a_documented_reason(self) -> None:
        # No `list_` tool exists on any surface, so this can only pass through
        # the explicit non-tool allowlist.
        status, errors = self.run_validator(
            LIVE_TOOLS,
            {"README.md": "Every `list_*` tool returns a compact envelope.\n"},
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_every_allowlisted_non_tool_glob_carries_a_reason(self) -> None:
        self.assertIn("list_*", validator.NOT_A_TOOL_GLOBS)
        for glob, reason in validator.NOT_A_TOOL_GLOBS.items():
            with self.subTest(glob=glob):
                self.assertIsInstance(reason, str)
                self.assertTrue(reason.strip(), f"{glob} has no reviewable reason")

    def test_unallowlisted_generic_glob_fails(self) -> None:
        status, errors = self.run_validator(
            LIVE_TOOLS,
            {"README.md": "See the `unknown_*` helpers for details.\n"},
        )

        self.assertEqual(1, status)
        self.assertTrue(any("`unknown_*`" in error for error in errors), errors)

    def test_failing_glob_reports_one_diagnostic_not_a_duplicate_token(self) -> None:
        # `editing_missing` is itself a dead token inside the glob. It must be
        # reported once, as a glob — not twice, once per scanner.
        status, errors = self.run_validator(
            LIVE_TOOLS,
            {"README.md": "Use `editing_missing_*` for this.\n"},
        )

        self.assertEqual(1, status)
        self.assertEqual(1, len(errors), errors)

    def test_emphasised_non_tool_identifier_is_a_token_not_a_glob(self) -> None:
        # The trailing-underscore rule is what keeps markdown out of the glob
        # parser. Treat `<name>*` as a glob and the closing marker of *italics*
        # or **bold** becomes the star: the identifier is checked as a dead
        # prefix instead of as a name, so its NOT_A_TOOL entry never applies and
        # a correct document fails. `editing_editing_batch` is the live example —
        # video-editing/SKILL.md names the retired doubled-prefix spelling
        # precisely to say it is NOT callable.
        status, errors = self.run_validator(
            LIVE_TOOLS,
            {
                "README.md": "The tool is not *editing_editing_batch* or "
                "**editing_editing_batch**.\n"
            },
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    # --- plain tokens ----------------------------------------------------

    def test_nested_skill_files_are_scanned(self) -> None:
        status, errors = self.run_validator(
            "platform_known\n",
            {
                "README.md": "No tool references here.\n",
                "skills/group/nested/SKILL.md": (
                    "Call `platform_missing` for this fixture.\n"
                ),
            },
        )

        self.assertEqual(1, status)
        self.assertTrue(any("platform_missing" in error for error in errors), errors)

    def test_reference_markdown_files_are_scanned(self) -> None:
        status, errors = self.run_validator(
            "platform_known\n",
            {
                "README.md": "No tool references here.\n",
                "skills/video-editing/SKILL.md": "No tool references here.\n",
                "skills/video-editing/references/mutations.md": (
                    "Call `platform_missing` for this fixture.\n"
                ),
            },
        )

        self.assertEqual(1, status)
        self.assertTrue(
            any(
                "skills/video-editing/references/mutations.md:1" in error
                and "platform_missing" in error
                for error in errors
            ),
            errors,
        )

    def test_live_tool_names_and_allowlisted_identifiers_pass(self) -> None:
        status, errors = self.run_validator(
            LIVE_TOOLS,
            {
                "README.md": (
                    "Call `editing_set_captions`, then the `modify_crop` batch op.\n"
                )
            },
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_stale_prefixed_plain_token_suggests_the_live_tool(self) -> None:
        status, errors = self.run_validator(
            PLATFORM_ONLY,
            {"README.md": "Call `platform-mcp-mcp_list_studios` to browse.\n"},
        )

        self.assertEqual(1, status)
        self.assertTrue(
            any("Did you mean platform_list_studios?" in error for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()

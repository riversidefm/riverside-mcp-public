from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import traceback
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_skill_references as validator  # noqa: E402


SKILL = "---\nname: fixture\ndescription: Use when testing fixtures.\n---\n"


class SkillReferenceValidatorTests(unittest.TestCase):
    def run_validator_with_output(
        self,
        files: dict[str, str],
        binary_files: Optional[dict[str, bytes]] = None,
        symlinks: Optional[dict[str, tuple[str, bool]]] = None,
    ) -> tuple[int, list[str], str, str]:
        """Run the real gate and expose both diagnostics streams."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            for rel, contents in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents, encoding="utf-8")
            for rel, contents in (binary_files or {}).items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
            for rel, (target, is_directory) in (symlinks or {}).items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(target, target_is_directory=is_directory)

            validator.errors.clear()
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(validator, "REPO_ROOT", root),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                try:
                    status = validator.main()
                except Exception:
                    traceback.print_exc()
                    status = 2
            return (
                status,
                list(validator.errors),
                stdout.getvalue(),
                stderr.getvalue(),
            )

    def run_validator(
        self,
        files: dict[str, str],
        binary_files: Optional[dict[str, bytes]] = None,
        symlinks: Optional[dict[str, tuple[str, bool]]] = None,
    ) -> tuple[int, list[str]]:
        status, errors, _, _ = self.run_validator_with_output(
            files, binary_files, symlinks
        )
        return status, errors

    def assert_failed_with(
        self, files: dict[str, str], *diagnostics: str,
        binary_files: Optional[dict[str, bytes]] = None,
        symlinks: Optional[dict[str, tuple[str, bool]]] = None,
    ) -> list[str]:
        status, errors = self.run_validator(files, binary_files, symlinks)
        self.assertEqual(1, status, errors)
        for diagnostic in diagnostics:
            self.assertTrue(
                any(diagnostic in error for error in errors),
                f"{diagnostic!r} not found in {errors}",
            )
        return errors

    def test_valid_direct_reference_link_passes(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [search](references/search.md).\n"
                ),
                "skills/fixture/references/search.md": "# Search\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_missing_local_target_reports_source_path_and_line(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "Intro.\n"  # 5
                    + "\n"  # 6
                    + "See [search](references/missing.md).\n"  # 7
                )
            },
            "skills/fixture/SKILL.md:7",
            "references/missing.md",
            "does not exist",
        )

        self.assertEqual(1, len(errors), errors)

    def test_absolute_local_path_is_rejected(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [search](/tmp/search.md).\n"
                )
            },
            "absolute",
        )

    def test_parent_directory_escape_is_rejected(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": SKILL + "See [outside](../outside.md).\n",
                "skills/outside.md": "# Outside\n",
            },
            "outside its owning skill",
        )

    def test_url_decoded_parent_directory_escape_is_rejected(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [outside](%2e%2e/outside.md).\n"
                ),
                "skills/outside.md": "# Outside\n",
            },
            "outside its owning skill",
        )

    def test_symlinked_reference_target_is_rejected_even_within_skill(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [search](references/search.md).\n"
                ),
                "skills/fixture/search-source.md": "# Search\n",
            },
            "symlink",
            symlinks={
                "skills/fixture/references/search.md": ("../search-source.md", False)
            },
        )

    def test_symlinked_references_directory_is_rejected_even_within_skill(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [search](references/search.md).\n"
                ),
                "skills/fixture/reference-source/search.md": "# Search\n",
            },
            "references",
            "symlink",
            symlinks={
                "skills/fixture/references": ("reference-source", True)
            },
        )

    def test_symlinked_skill_directory_is_rejected(self) -> None:
        self.assert_failed_with(
            {"skill-source/SKILL.md": SKILL + "No local links.\n"},
            "skills/fixture",
            "symlink",
            symlinks={"skills/fixture": ("../skill-source", True)},
        )

    def test_symlinked_skill_directory_without_skill_file_is_rejected(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": SKILL + "No local links.\n",
                "skill-source/notes.md": "# Notes\n",
            },
            "skills/linked",
            "symlink",
            symlinks={"skills/linked": ("../skill-source", True)},
        )

    def test_uninspectable_skill_symlink_is_reported_without_traceback(self) -> None:
        for name, target in (("dangling", "../missing"), ("loop", "loop")):
            with self.subTest(name=name):
                status, errors, _, stderr = self.run_validator_with_output(
                    {"skills/fixture/SKILL.md": SKILL + "No local links.\n"},
                    symlinks={f"skills/{name}": (target, True)},
                )

                self.assertEqual(1, status, errors)
                self.assertTrue(
                    any(
                        f"skills/{name}" in error
                        and "symlink target cannot be inspected" in error
                        for error in errors
                    ),
                    errors,
                )
                self.assertNotIn("Traceback", stderr)

    def test_unrelated_symlinked_file_under_skills_is_ignored(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": SKILL + "No local links.\n",
                "target.txt": "not a skill\n",
            },
            symlinks={"skills/unrelated-link": ("../target.txt", False)},
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_unlinked_reference_is_rejected_as_an_orphan(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": SKILL + "No links here.\n",
                "skills/fixture/references/orphan.md": "# Orphan\n",
            },
            "orphan",
        )

    def test_nested_reference_file_is_rejected(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [search](references/nested/search.md).\n"
                ),
                "skills/fixture/references/nested/search.md": "# Search\n",
            },
            "one level",
        )

    def test_reference_to_reference_link_is_rejected(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [first](references/first.md) and "
                    + "[second](references/second.md).\n"
                ),
                "skills/fixture/references/first.md": (
                    "Then read [second](second.md).\n"
                ),
                "skills/fixture/references/second.md": "# Second\n",
            },
            "reference-to-reference",
        )

    def test_reference_link_back_to_skill_is_rejected_as_a_local_link(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [first](references/first.md).\n"
                ),
                "skills/fixture/references/first.md": "Back to [skill](../SKILL.md).\n",
            },
            "../SKILL.md",
        )

        self.assertFalse(
            any("reference-to-reference" in error for error in errors), errors
        )

    def test_reference_link_to_other_local_file_is_rejected(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [first](references/first.md).\n"
                ),
                "skills/fixture/references/first.md": "See [notes](../notes.md).\n",
                "skills/fixture/notes.md": "# Notes\n",
            },
            "../notes.md",
        )

    def test_inline_markdown_link_is_validated(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [missing](references/missing.md).\n"
                )
            },
            "references/missing.md",
        )

        self.assertEqual(1, len(errors), errors)

    def test_inline_link_with_escaped_closing_bracket_is_validated(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [missing\\]](references/missing.md).\n"
                )
            },
            "references/missing.md",
        )

        self.assertEqual(1, len(errors), errors)

    def test_shortcut_label_with_escaped_closing_bracket_is_validated(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [missing\\]].\n\n"
                    + "[missing\\]]: references/missing.md\n"
                )
            },
            "references/missing.md",
        )

        self.assertEqual(1, len(errors), errors)

    def test_balanced_parentheses_in_inline_destination_are_preserved(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [guide](guide(v2).md).\n"
                ),
                "skills/fixture/guide(v2).md": "# Guide\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_balanced_destination_cannot_validate_a_truncated_file(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [guide](references/guide(v2).md).\n"
                ),
                "skills/fixture/references/guide(v2": "# Wrong target\n",
            },
            "references/guide(v2).md",
            "does not exist",
        )

        self.assertEqual(1, len(errors), errors)

    def test_angle_bracket_destination_may_contain_spaces(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [guide](<notes/my guide.md>).\n"
                ),
                "skills/fixture/notes/my guide.md": "# Guide\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_unescaped_angle_bracket_inside_destination_is_not_a_link(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "This is not a link: [guide](<missing<name>).\n"
                )
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_escaped_angle_bracket_inside_destination_is_validated(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [guide](<notes/my\\<guide.md>).\n"
                ),
                "skills/fixture/notes/my<guide.md": "# Guide\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_unescaped_angle_bracket_invalidates_reference_definition(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "This is not a link: [guide].\n\n"
                    + "[guide]: <missing<name>\n"
                )
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_escaped_angle_bracket_in_reference_definition_is_validated(
        self,
    ) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [guide].\n\n"
                    + "[guide]: <notes/my\\<guide.md>\n"
                ),
                "skills/fixture/notes/my<guide.md": "# Guide\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_escaped_parentheses_in_inline_destination_are_unescaped(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [guide](guide\\(v2\\).md).\n"
                ),
                "skills/fixture/guide(v2).md": "# Guide\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_escaped_uri_delimiters_keep_their_rendered_url_semantics(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [draft](notes.md\\?mode=full\\#details).\n"
                    + "See [other].\n\n"
                    + "[other]: other.md\\#details\n"
                ),
                "skills/fixture/notes.md": "# Draft\n",
                "skills/fixture/other.md": "# Other\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_link_definition_destination_is_validated_on_definition_line(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [search][guide].\n"  # 5
                    + "\n"  # 6
                    + "[guide]: references/missing.md\n"  # 7
                )
            },
            "skills/fixture/SKILL.md:7",
            "references/missing.md",
        )

    def test_fragments_and_external_urls_are_not_local_targets(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [below](#details), [docs](https://riverside.com/docs), "
                    + "and [mail](mailto:support@riverside.fm).\n"
                )
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_remote_uri_schemes_and_authorities_are_not_local_targets(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "Call [support](tel:+15550100).\n"
                    + "Load [inline data](data:text/plain,hello).\n"
                    + "Fetch [archive](ftp://example.com/guide.md).\n"
                    + "Visit [authority](//example.com/guide.md).\n"
                )
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_file_uri_is_rejected_as_a_local_escape(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "Read [host file](file:///etc/passwd).\n"
                )
            },
            "file:///etc/passwd",
            "file URI",
        )

        self.assertEqual(1, len(errors), errors)

    def test_escaped_file_uri_is_rejected_as_a_local_escape(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "Read [host file](file\\:///etc/passwd).\n"
                ),
                "skills/fixture/file:/etc/passwd": "decoy\n",
            },
            "file\\\\:///etc/passwd",
            "file URI",
        )

        self.assertEqual(1, len(errors), errors)

    def test_encoded_file_uri_is_rejected_as_a_local_escape(self) -> None:
        for encoded_colon in ("&#58;", "&#x3a;"):
            with self.subTest(encoded_colon=encoded_colon):
                errors = self.assert_failed_with(
                    {
                        "skills/fixture/SKILL.md": (
                            SKILL
                            + f"Read [host file](file{encoded_colon}///etc/passwd).\n"
                        ),
                        "skills/fixture/file&": "decoy\n",
                    },
                    "file URI",
                )

                self.assertEqual(1, len(errors), errors)

    def test_only_valid_named_character_references_are_decoded(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [literal](notes&notit;.md).\n"
                    + "See [decoded](notes&amp;draft.md).\n"
                ),
                "skills/fixture/notes&notit;.md": "# Literal\n",
                "skills/fixture/notes&draft.md": "# Decoded\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_numeric_character_reference_uses_the_unicode_code_point(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [control](notes&#128;.md).\n"
                ),
                "skills/fixture/notes\u0080.md": "# Control\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_local_destination_ignores_query_and_fragment(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [guide](guide.md?mode=full#details).\n"
                ),
                "skills/fixture/guide.md": "# Guide\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_link_shaped_text_in_fences_and_inline_code_is_ignored(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "````markdown\n"
                    + "```\n"
                    + "See [guide](references/missing-fenced.md).\n"
                    + "```\n"
                    + "````\n"
                    + "\n"
                    + "~~~\n"
                    + "See [other](references/missing-tilde.md).\n"
                    + "~~~\n"
                    + "\n"
                    + "Write `[label](references/missing-inline.md)` to route.\n"
                )
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_actual_local_image_link_is_validated(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "Intro.\n"  # 5
                    + "\n"  # 6
                    + "![diagram](references/missing.png)\n"  # 7
                )
            },
            "skills/fixture/SKILL.md:7",
            "references/missing.png",
            "does not exist",
        )

        self.assertEqual(1, len(errors), errors)

    def test_inline_image_to_markdown_does_not_own_reference(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "![search](references/search.md)\n"
                ),
                "skills/fixture/references/search.md": "# Search\n",
            },
            "orphan reference",
        )

    def test_reference_style_image_does_not_own_reference(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "![search][diagram]\n"  # 5
                    + "\n"  # 6
                    + "[diagram]: references/search.md\n"  # 7
                ),
                "skills/fixture/references/search.md": "# Search\n",
            },
            "orphan reference",
        )

    def test_reference_style_link_owns_reference(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [search][guide].\n"  # 5
                    + "\n"  # 6
                    + "[guide]: references/search.md\n"  # 7
                ),
                "skills/fixture/references/search.md": "# Search\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_shortcut_link_owns_reference(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [search].\n"  # 5
                    + "\n"  # 6
                    + "[search]: references/search.md\n"  # 7
                ),
                "skills/fixture/references/search.md": "# Search\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_shortcut_link_inside_terminal_reference_is_rejected(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [first](references/first.md) and "
                    + "[second](references/second.md).\n"
                ),
                "skills/fixture/references/first.md": (
                    "Then read [second].\n\n[second]: second.md\n"
                ),
                "skills/fixture/references/second.md": "# Second\n",
            },
            "reference-to-reference",
            "second.md",
        )

    def test_shortcut_image_missing_in_skill_is_rejected(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "![diagram]\n"  # 5
                    + "\n"  # 6
                    + "[diagram]: assets/missing.png\n"  # 7
                )
            },
            "skills/fixture/SKILL.md:7",
            "assets/missing.png",
            "does not exist",
        )

        self.assertEqual(1, len(errors), errors)

    def test_shortcut_image_missing_in_terminal_reference_is_rejected(
        self,
    ) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [first](references/first.md).\n"
                ),
                "skills/fixture/references/first.md": (
                    "# First\n\n![diagram]\n\n[diagram]: missing.png\n"
                ),
            },
            "skills/fixture/references/first.md:5",
            "missing.png",
            "does not exist",
        )

        self.assertEqual(1, len(errors), errors)

    def test_shortcut_image_does_not_own_reference(self) -> None:
        self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "![search]\n\n[search]: references/search.md\n"
                ),
                "skills/fixture/references/search.md": "# Search\n",
            },
            "orphan reference",
        )

    def test_shortcut_image_inside_terminal_reference_is_not_a_chain(
        self,
    ) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [first](references/first.md) and "
                    + "[second](references/second.md).\n"
                ),
                "skills/fixture/references/first.md": (
                    "![second]\n\n[second]: second.md\n"
                ),
                "skills/fixture/references/second.md": "# Second\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_inline_and_unused_labels_do_not_activate_definitions(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "Read [guide](https://riverside.com/docs).\n"
                    + "Unrelated [bracketed prose].\n\n"
                    + "[guide]: references/missing.md\n"
                )
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_reference_style_image_inside_terminal_reference_is_valid(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [first](references/first.md).\n"
                ),
                "skills/fixture/references/first.md": (
                    "# First\n\n![diagram][asset]\n\n[asset]: diagram.png\n"
                ),
                "skills/fixture/references/diagram.png": "image fixture\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_missing_image_inside_terminal_reference_is_rejected(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [first](references/first.md).\n"
                ),
                "skills/fixture/references/first.md": (
                    "# First\n![diagram](missing.png)\n"
                ),
            },
            "skills/fixture/references/first.md:2",
            "missing.png",
            "does not exist",
        )

        self.assertTrue(
            any(
                "skills/fixture/references/first.md:2" in error
                and "does not exist" in error
                for error in errors
            ),
            errors,
        )

    def test_parent_path_inside_skill_is_allowed_for_reference_image(self) -> None:
        status, errors = self.run_validator(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [guide](references/guide.md).\n"
                ),
                "skills/fixture/references/guide.md": (
                    "![diagram](../assets/diagram.png)\n"
                ),
                "skills/fixture/assets/diagram.png": "image fixture\n",
            }
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)

    def test_symlinked_image_inside_terminal_reference_is_rejected(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [first](references/first.md).\n"
                ),
                "skills/fixture/references/first.md": (
                    "# First\n![diagram](diagram.png)\n"
                ),
                "skills/fixture/references/image-source.png": "image fixture\n",
            },
            "symlink",
            symlinks={
                "skills/fixture/references/diagram.png": ("image-source.png", False)
            },
        )

        self.assertTrue(
            any(
                "skills/fixture/references/first.md:2" in error
                and "symlink" in error
                for error in errors
            ),
            errors,
        )

    def test_symlink_loop_inside_terminal_reference_has_no_traceback(
        self,
    ) -> None:
        status, errors, _, stderr = self.run_validator_with_output(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [first](references/first.md).\n"
                ),
                "skills/fixture/references/first.md": (
                    "Then read [loop](loop.md).\n"
                ),
            },
            symlinks={
                "skills/fixture/references/loop.md": ("loop.md", False)
            },
        )

        self.assertEqual(1, status, stderr)
        self.assertTrue(
            any(
                "skills/fixture/references/first.md:1" in error
                and "loop.md" in error
                and "symlink" in error
                for error in errors
            ),
            errors,
        )
        self.assertNotIn("Traceback", stderr)

    def test_escaping_image_inside_terminal_reference_is_rejected(self) -> None:
        errors = self.assert_failed_with(
            {
                "skills/fixture/SKILL.md": (
                    SKILL + "See [first](references/first.md).\n"
                ),
                "skills/fixture/references/first.md": (
                    "# First\n![diagram](../../../outside.png)\n"
                ),
                "outside.png": "image fixture\n",
            },
            "skills/fixture/references/first.md:2",
            "outside its owning skill",
        )

        self.assertTrue(
            any(
                "skills/fixture/references/first.md:2" in error
                and "outside its owning skill" in error
                for error in errors
            ),
            errors,
        )

    def test_invalid_decoded_path_is_reported_and_other_errors_are_aggregated(
        self,
    ) -> None:
        status, errors, _, stderr = self.run_validator_with_output(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [invalid](references/%00.md).\n"  # 5
                    + "See [missing](references/missing.md).\n"  # 6
                    + "See [absolute](/tmp/missing.md).\n"  # 7
                )
            }
        )

        self.assertEqual(1, status, stderr)
        self.assertEqual(3, len(errors), errors)
        for line, destination in (
            (5, "references/%00.md"),
            (6, "references/missing.md"),
            (7, "/tmp/missing.md"),
        ):
            self.assertTrue(
                any(
                    f"skills/fixture/SKILL.md:{line}" in diagnostic
                    and destination in diagnostic
                    for diagnostic in stderr.splitlines()
                ),
                stderr,
            )
        self.assertNotIn("Traceback", stderr)

    def test_invalid_utf8_is_reported_without_traceback(self) -> None:
        status, errors, _, stderr = self.run_validator_with_output(
            {},
            binary_files={"skills/fixture/SKILL.md": b"\xff"},
        )

        self.assertEqual(1, status, stderr)
        self.assertTrue(
            any(
                "skills/fixture/SKILL.md" in error
                and "UTF-8" in error
                for error in errors
            ),
            errors,
        )
        self.assertNotIn("Traceback", stderr)

    def test_unreadable_markdown_is_reported_without_traceback(self) -> None:
        with mock.patch.object(
            Path, "read_text", side_effect=OSError("permission denied")
        ):
            status, errors, _, stderr = self.run_validator_with_output(
                {"skills/fixture/SKILL.md": SKILL + "No local links.\n"}
            )

        self.assertEqual(1, status, stderr)
        self.assertTrue(
            any(
                "skills/fixture/SKILL.md" in error
                and "cannot be read" in error
                for error in errors
            ),
            errors,
        )
        self.assertNotIn("Traceback", stderr)

    def test_unreadable_skill_directory_is_reported_without_traceback(self) -> None:
        original_iterdir = Path.iterdir

        def fail_hidden(path: Path):
            if path.name == "hidden":
                raise PermissionError("permission denied")
            return original_iterdir(path)

        with mock.patch.object(Path, "iterdir", autospec=True, side_effect=fail_hidden):
            status, errors, _, stderr = self.run_validator_with_output(
                {
                    "skills/fixture/SKILL.md": SKILL + "No local links.\n",
                    "skills/hidden/SKILL.md": SKILL + "No local links.\n",
                }
            )

        self.assertEqual(1, status, stderr)
        self.assertTrue(
            any(
                "skills/hidden" in error and "cannot be read" in error
                for error in errors
            ),
            errors,
        )
        self.assertNotIn("Traceback", stderr)

    def test_unreadable_references_directory_is_reported_without_traceback(
        self,
    ) -> None:
        original_iterdir = Path.iterdir

        def fail_references(path: Path):
            if path.name == "references":
                raise PermissionError("permission denied")
            return original_iterdir(path)

        with mock.patch.object(
            Path, "iterdir", autospec=True, side_effect=fail_references
        ):
            status, errors, _, stderr = self.run_validator_with_output(
                {
                    "skills/fixture/SKILL.md": SKILL + "No local links.\n",
                    "skills/fixture/references/hidden.md": "# Hidden\n",
                }
            )

        self.assertEqual(1, status, stderr)
        self.assertTrue(
            any(
                "skills/fixture/references" in error
                and "cannot be read" in error
                for error in errors
            ),
            errors,
        )
        self.assertNotIn("Traceback", stderr)

    def test_uninspectable_reference_entry_is_reported_without_traceback(
        self,
    ) -> None:
        original_lstat = Path.lstat

        def fail_hidden(path: Path):
            if path.name == "hidden.md":
                raise PermissionError("permission denied")
            return original_lstat(path)

        with mock.patch.object(
            Path, "lstat", autospec=True, side_effect=fail_hidden
        ):
            status, errors, _, stderr = self.run_validator_with_output(
                {
                    "skills/fixture/SKILL.md": SKILL + "No local links.\n",
                    "skills/fixture/references/hidden.md": "# Hidden\n",
                }
            )

        self.assertEqual(1, status, stderr)
        self.assertTrue(
            any(
                "skills/fixture/references/hidden.md" in error
                and "cannot be inspected" in error
                for error in errors
            ),
            errors,
        )
        self.assertNotIn("Traceback", stderr)

    def test_symlink_loop_is_reported_and_other_errors_are_aggregated(
        self,
    ) -> None:
        status, errors, _, stderr = self.run_validator_with_output(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "![loop](assets/loop.png)\n"  # 5
                    + "![missing](assets/missing.png)\n"  # 6
                )
            },
            symlinks={"skills/fixture/assets/loop.png": ("loop.png", False)},
        )

        self.assertEqual(1, status, stderr)
        self.assertEqual(2, len(errors), errors)
        for line, destination, reason in (
            (5, "assets/loop.png", "symlink"),
            (6, "assets/missing.png", "does not exist"),
        ):
            self.assertTrue(
                any(
                    f"skills/fixture/SKILL.md:{line}" in diagnostic
                    and destination in diagnostic
                    and reason in diagnostic
                    for diagnostic in stderr.splitlines()
                ),
                stderr,
            )
        self.assertNotIn("Traceback", stderr)

    def test_rejected_escape_through_symlink_loop_does_not_abort_aggregation(
        self,
    ) -> None:
        status, errors, _, stderr = self.run_validator_with_output(
            {
                "skills/fixture/SKILL.md": (
                    SKILL
                    + "See [outside](../outside.md).\n"  # 5
                    + "![missing](assets/missing.png)\n"  # 6
                )
            },
            symlinks={"skills/outside.md": ("outside.md", False)},
        )

        self.assertEqual(1, status, stderr)
        self.assertEqual(3, len(errors), errors)
        self.assertTrue(
            any(
                "skills/outside.md" in error
                and "symlink target cannot be inspected" in error
                for error in errors
            ),
            errors,
        )
        self.assertTrue(
            any(
                "skills/fixture/SKILL.md:5" in error
                and "../outside.md" in error
                and "outside its owning skill" in error
                for error in errors
            ),
            errors,
        )
        self.assertTrue(
            any(
                "skills/fixture/SKILL.md:6" in error
                and "assets/missing.png" in error
                and "does not exist" in error
                for error in errors
            ),
            errors,
        )
        self.assertNotIn("Traceback", stderr)

    def test_skill_without_references_directory_is_valid(self) -> None:
        status, errors = self.run_validator(
            {"skills/fixture/SKILL.md": SKILL + "No local links.\n"}
        )

        self.assertEqual(0, status, errors)
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()

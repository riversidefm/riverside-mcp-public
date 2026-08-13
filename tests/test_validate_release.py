from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_release as validator  # noqa: E402


class ReleaseValidatorTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def init_repo(self, root: Path) -> None:
        self.git(root, "init", "-q")
        self.git(root, "config", "user.email", "validator@example.com")
        self.git(root, "config", "user.name", "Validator Test")

    def write_manifests(self, root: Path, version: str) -> None:
        for rel in validator.MANIFESTS:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"version": version}))

    def write_changelog(self, root: Path, *versions: str) -> None:
        root.joinpath("CHANGELOG.md").write_text(
            "# Changelog\n\n" + "\n".join(f"## [{version}]" for version in versions) + "\n"
        )

    def commit(self, root: Path, message: str) -> str:
        self.git(root, "add", "--all")
        self.git(root, "commit", "-q", "-m", message)
        return self.git(root, "rev-parse", "HEAD")

    def run_validator(self, root: Path, base: str | None = None) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = ["validate_release.py"]
        if base is not None:
            argv.extend(["--base", base])
        validator.errors.clear()
        with (
            mock.patch.object(validator, "REPO_ROOT", root),
            mock.patch.object(sys, "argv", argv),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = validator.main()
        return status, stdout.getvalue(), stderr.getvalue()

    def test_changed_bundle_requires_strict_semver_increase(self) -> None:
        cases = (
            ("0.9.0", "0.10.0", 0),
            ("0.5.0", "0.5.0", 1),
            ("0.5.0", "0.4.0", 1),
            ("0.5.0", "banana", 1),
        )
        for base_version, head_version, expected_status in cases:
            with self.subTest(base=base_version, head=head_version):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    self.init_repo(root)
                    self.write_manifests(root, base_version)
                    self.write_changelog(root, base_version, head_version)
                    base = self.commit(root, "base")
                    self.write_manifests(root, head_version)
                    if base_version == head_version:
                        changed = root / "skills" / "fixture" / "SKILL.md"
                        changed.parent.mkdir(parents=True)
                        changed.write_text("fixture\n")
                    self.commit(root, "head")

                    status, _, _ = self.run_validator(root, base)

                self.assertEqual(expected_status, status, validator.errors)

    def test_reference_only_change_requires_version_increase(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.init_repo(root)
            self.write_manifests(root, "0.5.0")
            self.write_changelog(root, "0.5.0")
            reference = root / "skills/fixture/references/search.md"
            reference.parent.mkdir(parents=True)
            reference.write_text("# Search\n\nOriginal guidance.\n")
            base = self.commit(root, "base")

            reference.write_text("# Search\n\nUpdated guidance.\n")
            self.commit(root, "head")

            status, _, stderr = self.run_validator(root, base)

        self.assertEqual(1, status)
        self.assertIn("shipped files changed", stderr)
        self.assertIn("skills/fixture/references/search.md", stderr)

    def test_semver_prerelease_and_build_precedence(self) -> None:
        increasing = (
            ("0.5.0-alpha", "0.5.0-alpha.1"),
            ("0.5.0-alpha.2", "0.5.0-alpha.10"),
            ("0.5.0-beta", "0.5.0-rc.1"),
            ("0.5.0-rc.1", "0.5.0"),
        )
        for lower, higher in increasing:
            with self.subTest(lower=lower, higher=higher):
                validator.errors.clear()
                parsed_lower = validator.parse_semver(lower, "lower")
                parsed_higher = validator.parse_semver(higher, "higher")
                self.assertIsNotNone(parsed_lower, validator.errors)
                self.assertIsNotNone(parsed_higher, validator.errors)
                self.assertLess(validator.compare_semver(parsed_lower, parsed_higher), 0)

        first_build = validator.parse_semver("0.5.0+build.1", "first")
        second_build = validator.parse_semver("0.5.0+build.2", "second")
        self.assertIsNotNone(first_build, validator.errors)
        self.assertIsNotNone(second_build, validator.errors)
        self.assertEqual(0, validator.compare_semver(first_build, second_build))

        for invalid in ("01.0.0", "0.5.0-01", "0.5.0-alpha..1"):
            with self.subTest(invalid=invalid):
                validator.errors.clear()
                self.assertIsNone(validator.parse_semver(invalid, "fixture"))

    def test_unreadable_or_invalid_base_version_fails_closed(self) -> None:
        cases: dict[str, str | bytes | None] = {
            "missing": None,
            "invalid JSON": "{",
            "invalid UTF-8": b"\xff",
            "non-object JSON": "[]",
            "missing version": "{}",
            "non-string version": '{"version": 4}',
            "invalid SemVer": '{"version": "banana"}',
        }
        for label, base_manifest in cases.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    self.init_repo(root)
                    self.write_manifests(root, "0.4.0")
                    claude_manifest = root / ".claude-plugin" / "plugin.json"
                    if base_manifest is None:
                        claude_manifest.unlink()
                    elif isinstance(base_manifest, bytes):
                        claude_manifest.write_bytes(base_manifest)
                    else:
                        claude_manifest.write_text(base_manifest)
                    self.write_changelog(root, "0.4.0", "0.5.0")
                    base = self.commit(root, "base")
                    self.write_manifests(root, "0.5.0")
                    self.commit(root, "head")

                    try:
                        status, stdout, stderr = self.run_validator(root, base)
                    except (AttributeError, OSError, UnicodeError, json.JSONDecodeError) as exc:
                        self.fail(f"{label} base version raised {type(exc).__name__}: {exc}")

                self.assertEqual(1, status)
                self.assertNotIn("Version bumped", stdout)
                self.assertIn("base", stderr.lower())

    def test_invalid_current_manifest_is_reported_without_traceback(self) -> None:
        cases = {
            "non-object JSON": b"[]",
            "invalid UTF-8": b"\xff",
            "unreadable path": None,
        }
        for label, contents in cases.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    self.write_manifests(root, "0.5.0")
                    self.write_changelog(root, "0.5.0")
                    manifest = root / ".claude-plugin" / "plugin.json"
                    manifest.unlink()
                    if contents is None:
                        manifest.mkdir()
                    else:
                        manifest.write_bytes(contents)

                    try:
                        status, _, stderr = self.run_validator(root)
                    except (AttributeError, OSError, UnicodeError) as exc:
                        self.fail(f"{label} current manifest raised {type(exc).__name__}: {exc}")

                self.assertEqual(1, status)
                self.assertIn(".claude-plugin/plugin.json", stderr)

    def test_missing_git_executable_is_reported_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.write_manifests(root, "0.5.0")
            self.write_changelog(root, "0.5.0")
            try:
                with mock.patch.dict(os.environ, {"PATH": ""}):
                    status, _, stderr = self.run_validator(root, "HEAD")
            except OSError as exc:
                self.fail(f"missing git executable raised {type(exc).__name__}: {exc}")

        self.assertEqual(1, status)
        self.assertIn("git", stderr.lower())

    def test_shipped_path_with_newline_is_not_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.init_repo(root)
            self.write_manifests(root, "0.5.0")
            self.write_changelog(root, "0.5.0")
            base = self.commit(root, "base")

            path = root / "skills/line\nbreak/SKILL.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")
            self.commit(root, "head")

            status, _, stderr = self.run_validator(root, base)

        self.assertEqual(1, status)
        self.assertIn("shipped files changed", stderr)

    def test_deleting_legacy_app_binding_requires_version_bump(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.init_repo(root)
            self.write_manifests(root, "0.5.0")
            self.write_changelog(root, "0.5.0")
            (root / ".app.json").write_text('{"apps": {}}\n')
            base = self.commit(root, "base")

            (root / ".app.json").unlink()
            self.commit(root, "remove workspace binding")

            status, _, stderr = self.run_validator(root, base)

        self.assertEqual(1, status)
        self.assertIn("shipped files changed", stderr)

    def test_missing_or_unreadable_changelog_is_reported_without_traceback(self) -> None:
        for label, contents in (("missing", None), ("invalid UTF-8", b"\xff")):
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    self.write_manifests(root, "0.5.0")
                    if contents is not None:
                        (root / "CHANGELOG.md").write_bytes(contents)

                    try:
                        status, _, stderr = self.run_validator(root)
                    except (OSError, UnicodeError) as exc:
                        self.fail(f"{label} changelog raised {type(exc).__name__}: {exc}")

                self.assertEqual(1, status)
                self.assertIn("CHANGELOG.md", stderr)


if __name__ == "__main__":
    unittest.main()

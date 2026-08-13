from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_agent_plugins as validator  # noqa: E402


REAL_SCHEMA_DIR = validator.SCHEMA_DIR


class AgentPluginsValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        validator.errors.clear()

    def write_plugin(self, root: Path) -> None:
        (root / "plugin.json").write_text(
            json.dumps(
                {
                    "$schema": validator.PLUGIN_SCHEMA_ID,
                    "name": "fixture",
                }
            )
        )

    def run_config(self, root: Path, mcp: object) -> int:
        self.write_plugin(root)
        (root / "mcp.json").write_text(json.dumps(mcp))
        validator.errors.clear()
        with (
            mock.patch.object(validator, "REPO_ROOT", root),
            mock.patch.object(validator, "SCHEMA_DIR", REAL_SCHEMA_DIR),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            return validator.main()

    def test_stdio_cwd_cannot_escape_its_declared_root(self) -> None:
        valid = ("./subdir", "${PLUGIN_ROOT}/subdir", "${PLUGIN_DATA}/subdir")
        invalid = ("./../tmp", "${PLUGIN_ROOT}/../../tmp", "${PLUGIN_DATA}/../tmp")

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "plugin"
            root.mkdir()
            for cwd in valid:
                with self.subTest(cwd=cwd):
                    status = self.run_config(
                        root,
                        {
                            "$schema": validator.MCP_SCHEMA_ID,
                            "mcpServers": {
                                "fixture": {"type": "stdio", "command": "python3", "cwd": cwd}
                            },
                        },
                    )
                    self.assertEqual(0, status, validator.errors)

            for cwd in invalid:
                with self.subTest(cwd=cwd):
                    status = self.run_config(
                        root,
                        {
                            "$schema": validator.MCP_SCHEMA_ID,
                            "mcpServers": {
                                "fixture": {"type": "stdio", "command": "python3", "cwd": cwd}
                            },
                        },
                    )
                    self.assertEqual(1, status)
                    self.assertTrue(any("escapes" in error for error in validator.errors))

    def test_stdio_cwd_rejects_existing_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            root = base / "plugin"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "linked-outside").symlink_to(outside, target_is_directory=True)

            status = self.run_config(
                root,
                {
                    "$schema": validator.MCP_SCHEMA_ID,
                    "mcpServers": {
                        "fixture": {
                            "type": "stdio",
                            "command": "python3",
                            "cwd": "./linked-outside",
                        }
                    },
                },
            )

        self.assertEqual(1, status)
        self.assertTrue(any("escapes" in error for error in validator.errors))

    def test_vendored_schema_requires_recorded_digest_and_file_specific_id(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            schema_dir = Path(raw) / "schemas"
            shutil.copytree(REAL_SCHEMA_DIR, schema_dir)
            plugin_path = schema_dir / "plugin.schema.json"
            plugin_schema = json.loads(plugin_path.read_text())
            plugin_schema["$id"] = validator.MCP_SCHEMA_ID
            plugin_path.write_text(json.dumps(plugin_schema))

            with (
                mock.patch.object(validator, "SCHEMA_DIR", schema_dir),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                status = validator.main()

        self.assertEqual(1, status)
        self.assertTrue(any("sha256" in error for error in validator.errors))
        self.assertTrue(any("unexpected $id" in error for error in validator.errors))

    def test_unsupported_schema_type_values_fail_cleanly(self) -> None:
        for expected in (["string", "null"], "uuid"):
            with self.subTest(expected=expected):
                validator.errors.clear()
                validator.assert_supported({"type": expected}, "fixture.schema.json")
                self.assertTrue(any("unsupported `type` value" in e for e in validator.errors))

                try:
                    messages = validator.validate("value", {"type": expected}, {}, "fixture")
                except (KeyError, TypeError) as exc:
                    self.fail(f"unsupported schema type raised {type(exc).__name__}: {exc}")
                self.assertTrue(any("unsupported `type` value" in message for message in messages))

    def test_non_mapping_mcp_servers_reports_schema_error_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for servers in ([{"type": "stdio"}], "fixture", 7):
                with self.subTest(servers=servers):
                    status = self.run_config(
                        root,
                        {
                            "$schema": validator.MCP_SCHEMA_ID,
                            "mcpServers": servers,
                        },
                    )
                    self.assertEqual(1, status)
                    self.assertTrue(
                        any("mcp.json.mcpServers: expected object" in e for e in validator.errors)
                    )


if __name__ == "__main__":
    unittest.main()

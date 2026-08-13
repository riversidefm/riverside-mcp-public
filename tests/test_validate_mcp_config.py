from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_mcp_config as validator  # noqa: E402


class McpConfigValidatorTests(unittest.TestCase):
    def run_configs(self, native_type: str, agent_plugins_type: str) -> int:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            native = root / ".mcp.json"
            agent_plugins = root / "mcp.json"
            native.write_text(
                json.dumps(
                    {
                        "riverside": {
                            "type": native_type,
                            "url": validator.CANONICAL_URL,
                        }
                    }
                )
            )
            agent_plugins.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "riverside": {
                                "type": agent_plugins_type,
                                "url": validator.CANONICAL_URL,
                            }
                        }
                    }
                )
            )
            validator.errors.clear()
            with (
                mock.patch.object(validator, "REPO_ROOT", root),
                mock.patch.object(validator, "CLAUDE_NATIVE", native),
                mock.patch.object(validator, "AP_CONFIG", agent_plugins),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                return validator.main()

    def test_http_alias_matches_agent_plugins_streamable_http(self) -> None:
        self.assertEqual(0, self.run_configs("http", "streamable-http"), validator.errors)

    def test_different_transport_protocols_do_not_match(self) -> None:
        status = self.run_configs("sse", "streamable-http")
        self.assertEqual(1, status)
        self.assertTrue(any("different transports" in error for error in validator.errors))


if __name__ == "__main__":
    unittest.main()

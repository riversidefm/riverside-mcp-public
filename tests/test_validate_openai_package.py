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

import validate_openai_package as validator  # noqa: E402


CANONICAL = "https://mcp.riverside.com/mcp"
SUPPORT_URL = "https://support.riverside.com/hc/en-us"

TOOL_SKILLS = ("content-discovery", "social-publishing", "video-editing")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def skill_yaml(display: str, *, with_dependency: bool = True, **overrides: str) -> str:
    body = (
        "interface:\n"
        f'  display_name: "{display}"\n'
        f'  short_description: "{display} for Riverside"\n'
    )
    if with_dependency:
        fields = {
            "type": "mcp",
            "value": "riverside",
            "description": "Riverside MCP server",
            "transport": "streamable_http",
            "url": CANONICAL,
        }
        fields.update(overrides)
        body += "\ndependencies:\n  tools:\n"
        first = True
        for key, value in fields.items():
            prefix = "    - " if first else "      "
            body += f'{prefix}{key}: "{value}"\n'
            first = False
    return body


def codex_manifest(version: str = "0.6.1", **overrides: object) -> dict:
    manifest: dict = {
        "name": "riverside",
        "version": version,
        "description": "Riverside podcast and recording platform.",
        "skills": "./skills/",
        "mcpServers": {"riverside": {"type": "http", "url": CANONICAL}},
        "interface": {
            "displayName": "Riverside",
            "shortDescription": "Search, edit & publish video",
            "longDescription": "Search, edit, and publish Riverside content.",
            "developerName": "Riverside",
            "category": "Creativity",
            "capabilities": ["Interactive", "Read", "Write"],
            "supportURL": SUPPORT_URL,
            "defaultPrompt": ["Find a Riverside recording"],
            "logo": "./assets/logo.png",
            "screenshots": [],
        },
    }
    manifest.update(overrides)
    return manifest


def build_package(root: Path, *, claude_version: str = "0.6.1",
                  setup_yaml: bool = True, **manifest_overrides: object) -> None:
    write_json(root / ".claude-plugin" / "plugin.json",
               {"name": "riverside", "version": claude_version})
    write_json(root / ".codex-plugin" / "plugin.json", codex_manifest(**manifest_overrides))
    write_json(root / ".mcp.json", {"riverside": {"type": "http", "url": CANONICAL}})
    write_json(root / "mcp.json",
               {"mcpServers": {"riverside": {"type": "streamable-http", "url": CANONICAL}}})

    (root / "assets").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    agents = root / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / "openai.yaml").write_text(skill_yaml("Riverside", with_dependency=False))

    for name in TOOL_SKILLS:
        skill_dir = root / "skills" / name
        (skill_dir / "agents").mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")
        (skill_dir / "agents" / "openai.yaml").write_text(skill_yaml(name))

    setup_dir = root / "skills" / "setup"
    setup_dir.mkdir(parents=True, exist_ok=True)
    (setup_dir / "SKILL.md").write_text("---\nname: setup\ndescription: x\n---\n")
    if setup_yaml:
        (setup_dir / "agents").mkdir(parents=True, exist_ok=True)
        (setup_dir / "agents" / "openai.yaml").write_text(
            skill_yaml("Setup", with_dependency=False)
        )


def run(root: Path, argv: tuple[str, ...] = ()) -> int:
    validator.errors.clear()
    with (
        mock.patch.object(validator, "REPO_ROOT", root),
        mock.patch.object(sys, "argv", ["validate_openai_package.py", *argv]),
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return validator.main()


class OpenAiPackageValidatorTests(unittest.TestCase):
    @contextlib.contextmanager
    def package(self, **kwargs):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            build_package(root, **kwargs)
            yield root

    def assertFailsWith(self, root: Path, needle: str, argv: tuple[str, ...] = ()) -> None:
        self.assertEqual(1, run(root, argv), f"expected failure; errors={validator.errors}")
        self.assertTrue(
            any(needle in error for error in validator.errors),
            f"no error contained {needle!r}; got {validator.errors}",
        )

    # --- happy path -------------------------------------------------------

    def test_complete_package_passes(self) -> None:
        with self.package() as root:
            self.assertEqual(0, run(root), validator.errors)

    def test_setup_skill_without_dependency_is_allowed(self) -> None:
        """`setup` troubleshoots the connection, so it must not require the MCP."""
        with self.package() as root:
            (root / "skills" / "setup" / "agents" / "openai.yaml").write_text(
                skill_yaml("Setup", with_dependency=False)
            )
            self.assertEqual(0, run(root), validator.errors)

    def test_setup_skill_may_omit_the_yaml_entirely(self) -> None:
        with self.package(setup_yaml=False) as root:
            self.assertEqual(0, run(root), validator.errors)

    # --- no committed app binding ------------------------------------------

    def test_declaring_apps_fails(self) -> None:
        """A workspace-scoped app id must not be published in the manifest."""
        with self.package(apps="./.app.json") as root:
            self.assertFailsWith(root, "`apps` must not be declared")

    def test_committed_app_json_fails_even_without_the_manifest_field(self) -> None:
        """The file is the thing that leaks, so it is checked independently."""
        with self.package() as root:
            write_json(root / ".app.json", {"apps": {"riverside": {"id": "asdk_app_x"}}})
            self.assertFailsWith(root, "must not be committed")

    def test_nested_app_json_fails(self) -> None:
        """A workspace binding is publishable regardless of where it is nested."""
        with self.package() as root:
            write_json(
                root / "fixtures" / ".app.json",
                {"apps": {"riverside": {"id": "asdk_app_x"}}},
            )
            self.assertFailsWith(root, "must not be committed")

    # --- version parity ---------------------------------------------------

    def test_version_mismatch_against_claude_manifest_fails(self) -> None:
        with self.package(claude_version="0.5.1") as root:
            self.assertFailsWith(root, "does not match")

    def test_name_mismatch_against_claude_manifest_fails(self) -> None:
        with self.package() as root:
            write_json(root / ".claude-plugin" / "plugin.json",
                       {"name": "riverside-plugin", "version": "0.6.0"})
            self.assertFailsWith(root, "component namespace")

    # --- the .mcp.json wrapper trap ---------------------------------------

    def test_path_to_unwrapped_claude_mcp_json_fails(self) -> None:
        """Riverside's .mcp.json is the unwrapped Claude plugin shape; OpenAI wants wrapped."""
        with self.package(mcpServers="./.mcp.json") as root:
            self.assertFailsWith(root, "no top-level `mcpServers` key")

    def test_path_to_wrapped_mcp_json_is_accepted(self) -> None:
        with self.package(mcpServers="./mcp.json") as root:
            self.assertEqual(0, run(root), validator.errors)

    def test_inline_server_disagreeing_with_mcp_json_fails(self) -> None:
        with self.package(
            mcpServers={"riverside-v2": {"type": "http", "url": CANONICAL}}
        ) as root:
            self.assertFailsWith(root, "must move together")

    def test_non_canonical_inline_url_fails(self) -> None:
        with self.package(
            mcpServers={"riverside": {"type": "http", "url": "https://not-canonical.example.com/mcp"}}
        ) as root:
            self.assertFailsWith(root, "mcpServers.riverside.url")

    def test_inline_server_missing_type_fails(self) -> None:
        with self.package(mcpServers={"riverside": {"url": CANONICAL}}) as root:
            self.assertFailsWith(root, "mcpServers.riverside.type")

    def test_inline_server_wrong_type_fails(self) -> None:
        with self.package(
            mcpServers={"riverside": {"type": "streamable_http", "url": CANONICAL}}
        ) as root:
            self.assertFailsWith(root, "mcpServers.riverside.type")

    def test_existing_mcp_urls_must_agree_with_the_inline_server(self) -> None:
        with self.package() as root:
            other = "https://not-canonical.example.com/mcp"
            write_json(root / ".mcp.json", {"riverside": {"type": "http", "url": other}})
            write_json(
                root / "mcp.json",
                {"mcpServers": {"riverside": {"type": "streamable-http", "url": other}}},
            )
            self.assertFailsWith(root, "all three URLs must move together")

    # --- per-skill dependency declarations --------------------------------

    def test_tool_skill_missing_agent_yaml_fails(self) -> None:
        with self.package() as root:
            (root / "skills" / "video-editing" / "agents" / "openai.yaml").unlink()
            self.assertFailsWith(root, "file not found")

    def test_tool_skill_without_dependency_fails(self) -> None:
        with self.package() as root:
            (root / "skills" / "video-editing" / "agents" / "openai.yaml").write_text(
                skill_yaml("Video Editing", with_dependency=False)
            )
            self.assertFailsWith(root, "missing `dependencies.tools`")

    def test_wrong_transport_fails(self) -> None:
        with self.package() as root:
            (root / "skills" / "video-editing" / "agents" / "openai.yaml").write_text(
                skill_yaml("Video Editing", transport="sse")
            )
            self.assertFailsWith(root, "transport")

    def test_non_canonical_dependency_url_fails(self) -> None:
        with self.package() as root:
            (root / "skills" / "video-editing" / "agents" / "openai.yaml").write_text(
                skill_yaml("Video Editing", url="http://localhost:3000/mcp")
            )
            self.assertFailsWith(root, "url")

    def test_dependency_value_must_name_a_configured_server(self) -> None:
        with self.package() as root:
            (root / "skills" / "video-editing" / "agents" / "openai.yaml").write_text(
                skill_yaml("Video Editing", value="riverside-editing")
            )
            self.assertFailsWith(root, "not a configured")

    def test_missing_tool_skill_directory_fails(self) -> None:
        with self.package() as root:
            shutil.rmtree(root / "skills" / "social-publishing")
            self.assertFailsWith(root, "missing social-publishing")

    # --- interface shape --------------------------------------------------

    def test_too_many_default_prompts_fails(self) -> None:
        interface = codex_manifest()["interface"]
        interface["defaultPrompt"] = ["a", "b", "c", "d"]
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "at most 3")

    def test_overlong_default_prompt_fails(self) -> None:
        interface = codex_manifest()["interface"]
        interface["defaultPrompt"] = ["x" * 129]
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "caps each at 128")

    def test_missing_interface_field_fails(self) -> None:
        interface = codex_manifest()["interface"]
        del interface["category"]
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "`category`")

    # --- listing-field caps and URLs ---------------------------------------

    def test_overlong_short_description_fails(self) -> None:
        """31 characters fails OpenAI's submission step, so it must fail CI first."""
        interface = codex_manifest()["interface"]
        interface["shortDescription"] = "x" * 31
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "submission_subtitle_too_long")

    def test_short_description_at_the_cap_passes(self) -> None:
        interface = codex_manifest()["interface"]
        interface["shortDescription"] = "x" * 30
        with self.package(interface=interface) as root:
            self.assertEqual(0, run(root), validator.errors)

    def test_overlong_display_name_fails(self) -> None:
        interface = codex_manifest()["interface"]
        interface["displayName"] = "x" * 31
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "`interface.displayName` is 31 characters")

    def test_missing_support_url_fails(self) -> None:
        """Both directories require a reachable support destination."""
        interface = codex_manifest()["interface"]
        del interface["supportURL"]
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "`supportURL`")

    def test_non_https_support_url_fails(self) -> None:
        interface = codex_manifest()["interface"]
        interface["supportURL"] = "support@riverside.fm"
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "must be an https:// URL")

    def test_https_url_without_a_host_fails(self) -> None:
        interface = codex_manifest()["interface"]
        interface["supportURL"] = "https://"
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "must be an https:// URL")

    def test_https_url_with_non_numeric_port_fails(self) -> None:
        interface = codex_manifest()["interface"]
        interface["supportURL"] = "https://support.riverside.com:invalid/path"
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "must be an https:// URL")

    def test_https_url_with_out_of_range_port_fails(self) -> None:
        interface = codex_manifest()["interface"]
        interface["supportURL"] = "https://support.riverside.com:65536/path"
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "must be an https:// URL")

    def test_non_string_optional_url_fails(self) -> None:
        interface = codex_manifest()["interface"]
        interface["websiteURL"] = 7
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "`interface.websiteURL` must be an https:// URL")

    def test_missing_asset_fails(self) -> None:
        interface = codex_manifest()["interface"]
        interface["logo"] = "./assets/nope.png"
        with self.package(interface=interface) as root:
            self.assertFailsWith(root, "does not exist")

    def test_non_png_screenshot_fails(self) -> None:
        interface = codex_manifest()["interface"]
        interface["screenshots"] = ["./assets/logo.png", "./assets/shot.jpg"]
        with self.package(interface=interface) as root:
            (root / "assets" / "shot.jpg").write_bytes(b"jpg")
            self.assertFailsWith(root, "must be a PNG")

    # --- path containment -------------------------------------------------

    def test_path_escaping_the_repo_fails(self) -> None:
        with self.package(skills="./../skills/") as root:
            self.assertFailsWith(root, "escapes the repo root")

    def test_absolute_path_fails(self) -> None:
        with self.package(skills="/etc/") as root:
            self.assertFailsWith(root, "must be relative")

    def test_path_without_dot_slash_prefix_fails(self) -> None:
        with self.package(skills="skills/") as root:
            self.assertFailsWith(root, "must begin with `./`")


class YamlReaderTests(unittest.TestCase):
    def test_parses_nested_maps_and_sequences_of_maps(self) -> None:
        data = validator.parse_yaml(
            'interface:\n'
            '  display_name: "Riverside"\n'
            '\n'
            '# a comment\n'
            'dependencies:\n'
            '  tools:\n'
            '    - type: "mcp"\n'
            '      value: "riverside"\n'
            '    - type: "mcp"\n'
            '      value: "other"\n'
        )
        self.assertEqual({"display_name": "Riverside"}, data["interface"])
        self.assertEqual(
            [{"type": "mcp", "value": "riverside"}, {"type": "mcp", "value": "other"}],
            data["dependencies"]["tools"],
        )

    def test_unquoted_scalar_drops_trailing_comment(self) -> None:
        self.assertEqual({"a": "b"}, validator.parse_yaml("a: b # note\n"))

    def test_quoted_scalar_keeps_hash(self) -> None:
        self.assertEqual({"a": "#00FF00"}, validator.parse_yaml('a: "#00FF00"\n'))

    def test_tabs_are_rejected(self) -> None:
        with self.assertRaises(validator.YamlError):
            validator.parse_yaml("a:\n\tb: c\n")

    def test_unterminated_quote_is_rejected(self) -> None:
        with self.assertRaises(validator.YamlError):
            validator.parse_yaml('a: "unclosed\n')

    def test_duplicate_key_is_rejected(self) -> None:
        with self.assertRaises(validator.YamlError):
            validator.parse_yaml("a: 1\na: 2\n")

    def test_scalar_sequence_is_rejected(self) -> None:
        with self.assertRaises(validator.YamlError):
            validator.parse_yaml("a:\n  - plain\n")

    def test_nested_map_inside_a_sequence_item_is_rejected(self) -> None:
        with self.assertRaises(validator.YamlError):
            validator.parse_yaml("a:\n  - k: v\n    meta:\n      x: 1\n")

    def test_unparsed_token_inside_a_sequence_item_is_rejected(self) -> None:
        with self.assertRaises(validator.YamlError):
            validator.parse_yaml("a:\n  - k: v\n    - nested: nope\n")


if __name__ == "__main__":
    unittest.main()

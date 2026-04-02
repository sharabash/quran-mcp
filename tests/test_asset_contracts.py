from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

from quran_mcp.lib.assets import asset_path, asset_text
from quran_mcp.mcp.resources.app import mushaf as mushaf_resource

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class TestAssetFilesExist:
    def test_skill_md_exists(self):
        assert asset_path("SKILL.md").is_file()

    def test_grounding_rules_md_exists(self):
        assert asset_path("GROUNDING_RULES.md").is_file()

    def test_mushaf_app_html_exists(self):
        assert mushaf_resource.MUSHAF_APP_PATH.is_file()


class TestMushafAppResourceOwnership:
    def test_resource_owns_local_path_lookup(self):
        assert mushaf_resource.MUSHAF_APP_PATH.is_file()
        assert mushaf_resource.MCP_APP_MIME == "text/html;profile=mcp-app"


class TestGroundingRulesContent:
    @pytest.fixture(autouse=True)
    def _load(self):
        asset_text.cache_clear()
        self.text = asset_text("GROUNDING_RULES.md")

    def test_non_empty(self):
        assert len(self.text) > 0

    def test_contains_grounded(self):
        assert "Grounded" in self.text

    def test_contains_partially_grounded(self):
        assert "Partially grounded" in self.text

    def test_contains_ungrounded(self):
        assert "Ungrounded" in self.text


class TestSkillMdContent:
    @pytest.fixture(autouse=True)
    def _load(self):
        asset_text.cache_clear()
        self.text = asset_text("SKILL.md")

    def test_non_empty(self):
        assert len(self.text) > 0

    def test_contains_usage_keywords(self):
        lower = self.text.lower()
        assert "tool" in lower or "search" in lower or "fetch" in lower


class TestFetchSkillGuideTool:
    @pytest.fixture
    def mcp(self):
        skill_guide_mod = _load_module(
            REPO_ROOT / "src" / "quran_mcp" / "mcp" / "tools" / "skill_guide" / "fetch.py",
            "test_skill_guide_fetch_mod",
        )
        server = FastMCP("skill-guide-test")
        skill_guide_mod.register(server)
        return server

    @pytest.mark.asyncio
    async def test_output_matches_actual_file(self, mcp):
        expected = asset_text("SKILL.md")
        async with Client(mcp) as client:
            result = await client.call_tool("fetch_skill_guide", {})
        assert result.content[0].text == expected


class TestFetchGroundingRulesTool:
    @pytest.fixture
    def mcp(self):
        grounding_rules_mod = _load_module(
            REPO_ROOT / "src" / "quran_mcp" / "mcp" / "tools" / "grounding_rules" / "fetch.py",
            "test_grounding_rules_fetch_mod",
        )
        server = FastMCP("grounding-rules-test")
        grounding_rules_mod.register(server)
        return server

    @pytest.mark.asyncio
    async def test_output_matches_actual_file(self, mcp):
        expected = asset_text("GROUNDING_RULES.md")
        async with Client(mcp) as client:
            result = await client.call_tool("fetch_grounding_rules", {})
        assert result.content[0].text == expected


class TestSkillGuideFallback:
    @pytest.mark.asyncio
    async def test_fallback_when_file_missing(self, monkeypatch: pytest.MonkeyPatch):
        mod = _load_module(
            REPO_ROOT / "src" / "quran_mcp" / "mcp" / "tools" / "skill_guide" / "fetch.py",
            "test_skill_guide_fetch_mod_fallback",
        )
        monkeypatch.setattr(mod, "skill_guide_markdown", lambda: "(file not found: SKILL.md)")
        server = FastMCP("fallback-test")
        mod.register(server)

        async with Client(server) as client:
            result = await client.call_tool("fetch_skill_guide", {})
        assert result.content[0].text == "(file not found: SKILL.md)"


class TestGroundingRulesFallback:
    @pytest.mark.asyncio
    async def test_fallback_when_file_missing(self, monkeypatch: pytest.MonkeyPatch):
        mod = _load_module(
            REPO_ROOT / "src" / "quran_mcp" / "mcp" / "tools" / "grounding_rules" / "fetch.py",
            "test_grounding_rules_fetch_mod_fallback",
        )
        monkeypatch.setattr(
            mod,
            "grounding_rules_markdown",
            lambda: "(file not found: GROUNDING_RULES.md)",
        )
        server = FastMCP("grounding-fallback-test")
        mod.register(server)

        async with Client(server) as client:
            result = await client.call_tool("fetch_grounding_rules", {})
        assert result.content[0].text == "(file not found: GROUNDING_RULES.md)"

from __future__ import annotations

from contextvars import copy_context

from quran_mcp.lib.editions import flags


def test_set_override_can_be_reset_to_environment(monkeypatch):
    monkeypatch.delenv("GOODMEM_NATIVE_QURAN", raising=False)

    flags.set_goodmem_native("quran", False)
    assert flags.use_goodmem_native("quran") is False

    flags.reset_goodmem_native_overrides("quran")
    assert flags.use_goodmem_native("quran") is True


def test_context_manager_restores_previous_override(monkeypatch):
    monkeypatch.setenv("GOODMEM_NATIVE_QURAN", "false")

    flags.set_goodmem_native("quran", True)
    assert flags.use_goodmem_native("quran") is True

    with flags.goodmem_native_override("quran", False):
        assert flags.use_goodmem_native("quran") is False

    assert flags.use_goodmem_native("quran") is True
    flags.reset_goodmem_native_overrides("quran")
    assert flags.use_goodmem_native("quran") is False


def test_overrides_do_not_leak_across_copied_contexts(monkeypatch):
    monkeypatch.delenv("GOODMEM_NATIVE_TRANSLATION", raising=False)

    def _override_and_read() -> bool:
        flags.set_goodmem_native("translation", False)
        return flags.use_goodmem_native("translation")

    ctx = copy_context()
    assert ctx.run(_override_and_read) is False
    assert flags.use_goodmem_native("translation") is True


def test_reset_all_clears_multiple_overrides(monkeypatch):
    monkeypatch.setenv("GOODMEM_NATIVE_QURAN", "false")
    monkeypatch.setenv("GOODMEM_NATIVE_TAFSIR", "false")

    flags.set_goodmem_native("quran", True)
    flags.set_goodmem_native("tafsir", True)
    assert flags.get_all_flags()["quran"] is True
    assert flags.get_all_flags()["tafsir"] is True

    flags.reset_goodmem_native_overrides()
    assert flags.use_goodmem_native("quran") is False
    assert flags.use_goodmem_native("tafsir") is False

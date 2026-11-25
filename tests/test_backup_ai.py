"""Backup AI: Gemini reads its share first, then the free backup AI reads the rest."""
import asyncio

import pytest

import parser as p
from config import settings

GOOD = '{"deals": []}'


def make(monkeypatch, backup=True, budget=None):
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "x")
    monkeypatch.setattr(settings, "llm_max_rpm", 6000)
    monkeypatch.setattr(settings, "backup_max_rpm", 6000)
    monkeypatch.setattr(settings, "backup_api_key", "k" if backup else "")
    ex = p.LLMExtractor()
    ex.primary_budget = budget
    calls = []

    async def gem(text):
        calls.append("main")
        return GOOD

    async def bak(text):
        calls.append("backup")
        return GOOD

    ex._gemini = gem
    ex._backup_call = bak
    return ex, calls


def run(coro):
    return asyncio.run(coro)


def test_no_backup_key_means_no_backup(monkeypatch):
    ex, _ = make(monkeypatch, backup=False)
    assert not ex.has_backup


def test_main_first_then_backup(monkeypatch):
    ex, calls = make(monkeypatch, budget=2)
    for _ in range(4):
        run(ex.extract("deal text"))
    assert calls == ["main", "main", "backup", "backup"]
    assert ex.primary_used == 2 and ex.backup_used == 2


def test_main_quota_out_falls_to_backup(monkeypatch):
    ex, calls = make(monkeypatch)

    async def gem(text):
        calls.append("main")
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    ex._gemini = gem
    monkeypatch.setattr(p, "wait_exponential_jitter", lambda **k: (lambda rs: 0))
    run(ex.extract("a"))
    run(ex.extract("b"))
    assert ex.quota_out
    run(ex.extract("c"))
    assert calls[-1] == "backup"
    assert ex.backup_used == 3


def test_both_out_raises_quota(monkeypatch):
    ex, _ = make(monkeypatch, budget=0)
    monkeypatch.setattr(settings, "backup_models", ["only-model"])

    async def bak(text):
        raise RuntimeError("Error code: 429 rate limit")

    ex._backup_call = bak
    for _ in range(2):
        with pytest.raises(p.AIQuotaUsedUp):
            run(ex.extract("x"))
    assert ex.backup_out
    with pytest.raises(p.AIQuotaUsedUp):
        run(ex.extract("y"))


def test_no_backup_keeps_old_behavior(monkeypatch):
    ex, calls = make(monkeypatch, backup=False, budget=1)
    run(ex.extract("a"))
    with pytest.raises(p.AIQuotaUsedUp):
        run(ex.extract("b"))
    assert calls == ["main"]


def test_retired_model_moves_to_next(monkeypatch):
    ex, calls = make(monkeypatch, budget=0)
    monkeypatch.setattr(settings, "backup_models", ["old-model", "new-model"])
    seen = []

    async def bak(text):
        model = settings.backup_models[ex.backup_model_i]
        seen.append(model)
        if model == "old-model":
            raise RuntimeError("Error code: 404 - The model `old-model` does not exist")
        return GOOD

    ex._backup_call = bak
    run(ex.extract("x"))
    assert seen == ["old-model", "new-model"]
    assert ex.backup_used == 1 and not ex.backup_out


def test_all_models_gone_stops_fast(monkeypatch):
    ex, _ = make(monkeypatch, budget=0)
    monkeypatch.setattr(settings, "backup_models", ["a", "b"])
    tries = []

    async def bak(text):
        tries.append(1)
        raise RuntimeError("Error code: 404 - model_not_found")

    ex._backup_call = bak
    with pytest.raises(p.AIQuotaUsedUp):
        run(ex.extract("x"))
    assert ex.backup_out and len(tries) == 2
    with pytest.raises(p.AIQuotaUsedUp):      # later posts don't even try
        run(ex.extract("y"))
    assert len(tries) == 2


def test_bad_key_turns_backup_off(monkeypatch):
    ex, _ = make(monkeypatch, budget=0)

    async def bak(text):
        raise RuntimeError("Error code: 401 - invalid_api_key")

    ex._backup_call = bak
    with pytest.raises(p.AIQuotaUsedUp):
        run(ex.extract("x"))
    assert ex.backup_out


def test_json_wrapped_in_words_is_read():
    assert p._json_part('Here you go:\n```json\n{"deals": []}\n```') == '{"deals": []}'

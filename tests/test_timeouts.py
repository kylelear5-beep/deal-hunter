import asyncio
import time

import verifier


class FrozenVerifier:
    async def supports(self, domain):
        return True

    async def test_codes(self, domain, codes):
        await asyncio.sleep(3600)        # a check that never finishes


async def test_frozen_code_check_is_skipped(db, monkeypatch):
    async def pending(limit):
        return {"shop-a.com": [{"deal_hash": "a", "promo_code": "X"}],
                "shop-b.com": [{"deal_hash": "b", "promo_code": "Y"}]}

    async def attempts(domain):
        return 0
    monkeypatch.setattr(db, "pending_codes_by_domain", pending)
    monkeypatch.setattr(db, "attempts_today", attempts)
    monkeypatch.setattr(verifier, "VERIFIERS", [FrozenVerifier()])
    t = time.monotonic()
    stats = await verifier.verify_pending(db, total_seconds=6, per_code_seconds=0.2)
    assert time.monotonic() - t < 3
    assert stats["timed_out"] == 2 and stats["valid"] == 0


async def test_out_of_time_stops_early(db, monkeypatch):
    async def pending(limit):
        return {"shop-a.com": [{"deal_hash": "a", "promo_code": "X"}]}
    monkeypatch.setattr(db, "pending_codes_by_domain", pending)
    monkeypatch.setattr(verifier, "VERIFIERS", [FrozenVerifier()])
    stats = await verifier.verify_pending(db, total_seconds=1)
    assert stats["timed_out"] == 0          # not even started: no time left


async def test_slow_scan_still_publishes(db, monkeypatch, tmp_path):
    import main
    from config import settings
    called = []

    async def slow_pipeline(*a, **k):
        await asyncio.sleep(3600)

    async def fake_tick(*a, **k):
        called.append("posts")

    async def fake_build(db_, *a, **k):
        called.append("site")
    monkeypatch.setattr(main, "run_pipeline", slow_pipeline)
    monkeypatch.setattr(main, "PIPELINE_LIMIT_SECONDS", 0.3)
    monkeypatch.setattr(main, "scheduler_tick", fake_tick)
    monkeypatch.setattr("sitegen.build_site", fake_build)
    monkeypatch.setattr(settings, "site_dir", str(tmp_path))

    async def no_links(*a, **k):
        return {"tried": 0, "found": 0}
    monkeypatch.setattr("linkresolve.backfill_store_links", no_links)
    await main.run_actions_once(db, extractor=None)
    assert called[:2] == ["posts", "site"]

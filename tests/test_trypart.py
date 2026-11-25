import trypart


async def test_try_part_site_and_unknown(db, tmp_path, monkeypatch, capsys):
    from config import settings
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "missing.db"))
    assert await trypart.try_part("site") is True
    assert "TRY-PART site: WORKS" in capsys.readouterr().out
    assert await trypart.try_part("nope") is False


async def test_try_part_reports_broken(monkeypatch, tmp_path, capsys):
    from config import settings
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "missing.db"))

    async def boom(db, tmp):
        raise ValueError("bad thing")
    monkeypatch.setitem(trypart.RUNNERS, "site", boom)
    assert await trypart.try_part("site") is False
    assert "STILL BROKEN" in capsys.readouterr().out


async def test_try_part_never_touches_real_db(tmp_path, monkeypatch):
    import sqlite3
    from config import settings
    real = tmp_path / "real.db"
    sqlite3.connect(real).close()
    before = real.read_bytes()
    monkeypatch.setattr(settings, "db_path", str(real))
    assert await trypart.try_part("recheck") is True
    assert real.read_bytes() == before

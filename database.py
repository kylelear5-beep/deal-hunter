"""SQLite storage (aiosqlite): deals, alert history, verifier attempts, processed items,
API keys and API usage counters."""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import aiosqlite

from config import settings
from parser import Deal

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS deals (
    deal_hash       TEXT PRIMARY KEY,
    store_name      TEXT NOT NULL,
    store_domain    TEXT NOT NULL,
    promo_code      TEXT,
    discount_value  TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN
                        ('COUPON','CASHBACK_BONUS','FREEBIE','PRICE_ERROR')),
    expiration_date TEXT,
    source_url      TEXT NOT NULL,
    affiliate_url   TEXT NOT NULL DEFAULT '',
    merchant_url    TEXT,
    source          TEXT NOT NULL DEFAULT '',
    is_verified     INTEGER NOT NULL DEFAULT 0,
    verify_status   TEXT NOT NULL DEFAULT 'pending',   -- pending|verified|flagged|unsupported|n/a
    fail_count      INTEGER NOT NULL DEFAULT 0,
    last_checked_at TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deals_domain  ON deals(store_domain);
CREATE INDEX IF NOT EXISTS idx_deals_created ON deals(created_at);
CREATE INDEX IF NOT EXISTS idx_deals_status  ON deals(verify_status);

CREATE TABLE IF NOT EXISTS alert_log (
    deal_hash TEXT NOT NULL,
    channel   TEXT NOT NULL,
    sent_at   TEXT NOT NULL,
    PRIMARY KEY (deal_hash, channel)
);

CREATE TABLE IF NOT EXISTS verify_attempts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_hash    TEXT NOT NULL,
    store_domain TEXT NOT NULL,
    result       TEXT NOT NULL,
    detail       TEXT,
    attempted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_domain ON verify_attempts(store_domain, attempted_at);

CREATE TABLE IF NOT EXISTS processed_items (
    item_hash    TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash   TEXT PRIMARY KEY,
    key_prefix TEXT NOT NULL,
    owner      TEXT NOT NULL,
    tier       TEXT NOT NULL CHECK (tier IN ('free','pro')),
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_hash   TEXT NOT NULL,
    niche       TEXT NOT NULL,
    tier        TEXT NOT NULL,                 -- free | paid
    kind        TEXT NOT NULL,                 -- telegram | discord
    target      TEXT NOT NULL,                 -- chat id / webhook url
    post_type   TEXT NOT NULL DEFAULT 'deal',  -- deal | teaser
    due_at      TEXT NOT NULL,
    sent_at     TEXT,
    attempts    INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'queued', -- queued | sent | failed | skipped
    error       TEXT,
    UNIQUE (deal_hash, niche, tier, kind, target)
);
CREATE INDEX IF NOT EXISTS idx_posts_due ON posts(status, due_at);

CREATE TABLE IF NOT EXISTS clicks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_hash  TEXT NOT NULL,
    channel    TEXT NOT NULL,
    clicked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clicks_time ON clicks(clicked_at);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    finished_at TEXT NOT NULL,
    scraped     INTEGER NOT NULL,
    parsed      INTEGER NOT NULL,
    llm_failed  INTEGER NOT NULL,
    new_deals   INTEGER NOT NULL,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS api_usage (
    key_hash TEXT NOT NULL,
    day      TEXT NOT NULL,
    count    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key_hash, day)
);
"""

PUBLIC_FIELDS = ("deal_hash", "store_name", "store_domain", "promo_code", "discount_value",
                 "category", "expiration_date", "source_url", "affiliate_url", "is_verified",
                 "created_at")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


MIGRATIONS = {  # column -> DDL, applied to databases created by older versions
    "summary": "ALTER TABLE deals ADD COLUMN summary TEXT NOT NULL DEFAULT ''",
    "niches": "ALTER TABLE deals ADD COLUMN niches TEXT NOT NULL DEFAULT ''",
}


class Database:
    def __init__(self, path: Optional[str] = None):
        self.path = path or settings.db_path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> "Database":
        self.conn = await aiosqlite.connect(self.path, timeout=30)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        cur = await self.conn.execute("PRAGMA table_info(deals)")
        have = {r[1] for r in await cur.fetchall()}
        for col, ddl in MIGRATIONS.items():
            if col not in have:
                await self.conn.execute(ddl)
        await self.conn.commit()
        return self

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None

    async def __aenter__(self) -> "Database":
        return await self.connect()

    async def __aexit__(self, *exc) -> None:
        await self.close()

    @staticmethod
    def _row(row: aiosqlite.Row) -> dict[str, Any]:
        d = dict(row)
        d["is_verified"] = bool(d.get("is_verified"))
        if "niches" in d:
            d["niches"] = [n for n in (d["niches"] or "").split(",") if n]
        return d

    # -- deals -----------------------------------------------------------------
    async def insert_deal(self, deal: Deal) -> bool:
        """Insert if new. Returns True only for brand-new deals (dedup by deal_hash)."""
        d = deal.model_dump(mode="json")
        status = "pending" if d["promo_code"] else "n/a"
        cur = await self.conn.execute(
            """INSERT OR IGNORE INTO deals (deal_hash, store_name, store_domain, promo_code,
                   discount_value, category, expiration_date, source_url, affiliate_url,
                   merchant_url, source, is_verified, verify_status, created_at,
                   summary, niches)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["deal_hash"], d["store_name"], d["store_domain"], d["promo_code"],
             d["discount_value"], d["category"], d["expiration_date"], d["source_url"],
             d["affiliate_url"], d["merchant_url"], d["source"], int(d["is_verified"]),
             status, d["created_at"], d.get("summary") or "",
             ",".join(d.get("niches") or [])))
        await self.conn.commit()
        return cur.rowcount == 1

    async def get_deal(self, deal_hash: str) -> Optional[dict]:
        cur = await self.conn.execute("SELECT * FROM deals WHERE deal_hash=?", (deal_hash,))
        row = await cur.fetchone()
        return self._row(row) if row else None

    @staticmethod
    def _active_clause() -> str:
        return ("(expiration_date IS NULL OR expiration_date >= ?) "
                "AND verify_status != 'flagged'")

    async def query_deals(self, domain: Optional[str] = None, category: Optional[str] = None,
                          verified_only: bool = True, limit: int = 50, offset: int = 0,
                          allowed_sources: Optional[list[str]] = None
                          ) -> tuple[list[dict], int]:
        where = [self._active_clause()]
        params: list[Any] = [date.today().isoformat()]
        if domain:
            # exact, request is a subdomain of the store, or store is a subdomain of request
            where.append("(store_domain = ? OR ? LIKE '%.' || store_domain "
                         "OR store_domain LIKE '%.' || ?)")
            params += [domain, domain, domain]
        if category:
            where.append("category = ?")
            params.append(category)
        if verified_only:
            where.append("is_verified = 1")
        if allowed_sources is not None:
            if not allowed_sources:
                return [], 0
            where.append(f"source IN ({','.join('?' * len(allowed_sources))})")
            params += allowed_sources
        sql_where = " AND ".join(where)
        cur = await self.conn.execute(f"SELECT COUNT(*) FROM deals WHERE {sql_where}", params)
        total = (await cur.fetchone())[0]
        cur = await self.conn.execute(
            f"SELECT * FROM deals WHERE {sql_where} "
            f"ORDER BY is_verified DESC, created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset])
        return [self._row(r) for r in await cur.fetchall()], total

    async def recent_deals(self, hours: int = 24, cap: int = 500,
                           allowed_sources: Optional[list[str]] = None) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(
            timespec="seconds")
        where = [self._active_clause(), "created_at >= ?"]
        params: list[Any] = [date.today().isoformat(), since]
        if allowed_sources is not None:
            if not allowed_sources:
                return []
            where.append(f"source IN ({','.join('?' * len(allowed_sources))})")
            params += allowed_sources
        cur = await self.conn.execute(
            f"SELECT * FROM deals WHERE {' AND '.join(where)} "
            f"ORDER BY created_at DESC LIMIT ?", params + [cap])
        return [self._row(r) for r in await cur.fetchall()]

    async def purge_expired(self) -> int:
        cur = await self.conn.execute(
            "DELETE FROM deals WHERE expiration_date IS NOT NULL AND expiration_date < ?",
            (date.today().isoformat(),))
        await self.conn.commit()
        return cur.rowcount

    # -- verifier --------------------------------------------------------------
    async def pending_codes_by_domain(self, per_domain: int = 20) -> dict[str, list[dict]]:
        cur = await self.conn.execute(
            f"""SELECT * FROM deals WHERE promo_code IS NOT NULL
                  AND verify_status IN ('pending','retry')
                  AND (expiration_date IS NULL OR expiration_date >= ?)
                ORDER BY created_at DESC""", (date.today().isoformat(),))
        grouped: dict[str, list[dict]] = {}
        for row in await cur.fetchall():
            bucket = grouped.setdefault(row["store_domain"], [])
            if len(bucket) < per_domain:
                bucket.append(self._row(row))
        return grouped

    async def attempts_today(self, store_domain: str) -> int:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                                                   microsecond=0).isoformat(timespec="seconds")
        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM verify_attempts WHERE store_domain=? AND attempted_at>=?",
            (store_domain, start))
        return (await cur.fetchone())[0]

    async def log_attempt(self, deal_hash: str, store_domain: str, result: str,
                          detail: str = "") -> None:
        await self.conn.execute(
            "INSERT INTO verify_attempts (deal_hash, store_domain, result, detail, "
            "attempted_at) VALUES (?,?,?,?,?)",
            (deal_hash, store_domain, result, detail[:500], utcnow_iso()))
        await self.conn.commit()

    async def mark_verified(self, deal_hash: str) -> None:
        await self.conn.execute(
            "UPDATE deals SET is_verified=1, verify_status='verified', fail_count=0, "
            "last_checked_at=? WHERE deal_hash=?", (utcnow_iso(), deal_hash))
        await self.conn.commit()

    async def record_failure(self, deal_hash: str, delete_after: Optional[int] = None) -> str:
        """Count a failed check. Returns 'deleted' or 'retry'.
        Rows marked 'retry' stay visible as unverified until they pass or are deleted."""
        delete_after = delete_after or settings.verify_delete_after_failures
        await self.conn.execute(
            "UPDATE deals SET fail_count=fail_count+1, is_verified=0, last_checked_at=? "
            "WHERE deal_hash=?", (utcnow_iso(), deal_hash))
        cur = await self.conn.execute("SELECT fail_count FROM deals WHERE deal_hash=?",
                                      (deal_hash,))
        row = await cur.fetchone()
        if row and row[0] >= delete_after:
            await self.conn.execute("DELETE FROM deals WHERE deal_hash=?", (deal_hash,))
            outcome = "deleted"
        else:
            await self.conn.execute("UPDATE deals SET verify_status='retry' WHERE deal_hash=?",
                                    (deal_hash,))
            outcome = "retry"
        await self.conn.commit()
        return outcome

    async def mark_status(self, deal_hashes: Iterable[str], status: str) -> None:
        await self.conn.executemany(
            "UPDATE deals SET verify_status=?, last_checked_at=? WHERE deal_hash=?",
            [(status, utcnow_iso(), h) for h in deal_hashes])
        await self.conn.commit()

    # -- alerts ----------------------------------------------------------------
    async def was_alerted(self, deal_hash: str, channel: str) -> bool:
        cur = await self.conn.execute(
            "SELECT 1 FROM alert_log WHERE deal_hash=? AND channel=?", (deal_hash, channel))
        return await cur.fetchone() is not None

    async def record_alert(self, deal_hash: str, channel: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO alert_log (deal_hash, channel, sent_at) VALUES (?,?,?)",
            (deal_hash, channel, utcnow_iso()))
        await self.conn.commit()

    # -- processed raw items (saves LLM money) ---------------------------------
    async def filter_unprocessed(self, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        seen: set[str] = set()
        for i in range(0, len(hashes), 500):
            chunk = hashes[i:i + 500]
            cur = await self.conn.execute(
                f"SELECT item_hash FROM processed_items WHERE item_hash IN "
                f"({','.join('?' * len(chunk))})", chunk)
            seen.update(r[0] for r in await cur.fetchall())
        return set(hashes) - seen

    async def mark_processed(self, hashes: Iterable[str]) -> None:
        now = utcnow_iso()
        await self.conn.executemany(
            "INSERT OR IGNORE INTO processed_items (item_hash, processed_at) VALUES (?,?)",
            [(h, now) for h in hashes])
        await self.conn.commit()

    # -- API keys & usage --------------------------------------------------------
    async def create_api_key(self, owner: str, tier: str = "free") -> str:
        if tier not in ("free", "pro"):
            raise ValueError("tier must be 'free' or 'pro'")
        key = "dh_" + secrets.token_urlsafe(32)
        await self.conn.execute(
            "INSERT INTO api_keys (key_hash, key_prefix, owner, tier, active, created_at) "
            "VALUES (?,?,?,?,1,?)", (hash_key(key), key[:10], owner, tier, utcnow_iso()))
        await self.conn.commit()
        return key

    async def lookup_api_key(self, api_key: str) -> Optional[dict]:
        cur = await self.conn.execute(
            "SELECT key_hash, key_prefix, owner, tier, active FROM api_keys WHERE key_hash=?",
            (hash_key(api_key),))
        row = await cur.fetchone()
        return dict(row) if row and row["active"] else None

    async def list_api_keys(self) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT key_prefix, owner, tier, active, created_at FROM api_keys "
            "ORDER BY created_at")
        return [dict(r) for r in await cur.fetchall()]

    async def revoke_api_key(self, key_prefix: str) -> int:
        cur = await self.conn.execute("UPDATE api_keys SET active=0 WHERE key_prefix=?",
                                      (key_prefix,))
        await self.conn.commit()
        return cur.rowcount

    async def increment_usage(self, key_hash: str) -> int:
        """Add one request to today's counter and return the new total."""
        day = datetime.now(timezone.utc).date().isoformat()
        await self.conn.execute(
            "INSERT INTO api_usage (key_hash, day, count) VALUES (?,?,1) "
            "ON CONFLICT(key_hash, day) DO UPDATE SET count=count+1", (key_hash, day))
        await self.conn.commit()
        cur = await self.conn.execute(
            "SELECT count FROM api_usage WHERE key_hash=? AND day=?", (key_hash, day))
        return (await cur.fetchone())[0]

    # -- channel posts (v3) -------------------------------------------------------
    async def enqueue_post(self, deal_hash: str, niche: str, tier: str, kind: str,
                           target: str, due_at: str, post_type: str = "deal") -> bool:
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO posts (deal_hash, niche, tier, kind, target, post_type, "
            "due_at) VALUES (?,?,?,?,?,?,?)",
            (deal_hash, niche, tier, kind, target, post_type, due_at))
        await self.conn.commit()
        return cur.rowcount == 1

    async def due_posts(self, now_iso: str, limit: int = 50) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT p.id AS post_id, p.niche, p.tier, p.kind, p.target, p.post_type, "
            "p.attempts, d.* FROM posts p JOIN deals d ON d.deal_hash = p.deal_hash "
            "WHERE p.status='queued' AND p.due_at <= ? ORDER BY p.due_at LIMIT ?",
            (now_iso, limit))
        return [self._row(r) for r in await cur.fetchall()]

    async def orphan_posts_cleanup(self) -> int:
        """Posts whose deal was deleted (dead code / expired) are skipped."""
        cur = await self.conn.execute(
            "UPDATE posts SET status='skipped', error='deal removed' WHERE status='queued' "
            "AND deal_hash NOT IN (SELECT deal_hash FROM deals)")
        await self.conn.commit()
        return cur.rowcount

    async def finish_post(self, post_id: int, ok: bool, error: str = "",
                          retry_at: Optional[str] = None, max_attempts: int = 5) -> None:
        if ok:
            await self.conn.execute(
                "UPDATE posts SET status='sent', sent_at=?, attempts=attempts+1, error=NULL "
                "WHERE id=?", (utcnow_iso(), post_id))
        else:
            await self.conn.execute(
                "UPDATE posts SET attempts=attempts+1, error=?, "
                "status=CASE WHEN attempts+1 >= ? THEN 'failed' ELSE 'queued' END, "
                "due_at=COALESCE(?, due_at) WHERE id=?",
                (error[:300], max_attempts, retry_at, post_id))
        await self.conn.commit()

    async def skip_post(self, post_id: int, reason: str) -> None:
        await self.conn.execute("UPDATE posts SET status='skipped', error=? WHERE id=?",
                                (reason, post_id))
        await self.conn.commit()

    async def post_stats(self, since_iso: str) -> dict[str, int]:
        cur = await self.conn.execute(
            "SELECT status, COUNT(*) FROM posts WHERE due_at >= ? GROUP BY status",
            (since_iso,))
        return {r[0]: r[1] for r in await cur.fetchall()}

    # -- niche queries (website, digests) ------------------------------------------
    async def niche_deals(self, niche: Optional[str] = None, hours: int = 24 * 7,
                          limit: int = 200) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(
            timespec="seconds")
        where = [self._active_clause(), "created_at >= ?", "niches != ''"]
        params: list[Any] = [date.today().isoformat(), since]
        if niche:
            where.append("(',' || niches || ',') LIKE ?")
            params.append(f"%,{niche},%")
        cur = await self.conn.execute(
            f"SELECT * FROM deals WHERE {' AND '.join(where)} "
            f"ORDER BY created_at DESC LIMIT ?", params + [limit])
        return [self._row(r) for r in await cur.fetchall()]

    async def count_new_deals(self, since_iso: str) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) FROM deals WHERE created_at >= ?",
                                      (since_iso,))
        return (await cur.fetchone())[0]

    async def niche_counts(self, since_iso: str) -> dict[str, int]:
        cur = await self.conn.execute(
            "SELECT niches FROM deals WHERE created_at >= ? AND niches != ''", (since_iso,))
        counts: dict[str, int] = {}
        for (niches,) in await cur.fetchall():
            for n in niches.split(","):
                counts[n] = counts.get(n, 0) + 1
        return counts

    # -- click tracking ---------------------------------------------------------------
    async def find_deal_by_prefix(self, prefix: str) -> Optional[dict]:
        if len(prefix) < 8 or not prefix.isalnum():
            return None
        cur = await self.conn.execute(
            "SELECT * FROM deals WHERE deal_hash LIKE ? LIMIT 1", (prefix.lower() + "%",))
        row = await cur.fetchone()
        return self._row(row) if row else None

    async def record_click(self, deal_hash: str, channel: str) -> None:
        await self.conn.execute(
            "INSERT INTO clicks (deal_hash, channel, clicked_at) VALUES (?,?,?)",
            (deal_hash, channel[:40], utcnow_iso()))
        await self.conn.commit()

    async def click_stats(self, since_iso: str) -> dict[str, Any]:
        cur = await self.conn.execute(
            "SELECT channel, COUNT(*) FROM clicks WHERE clicked_at >= ? GROUP BY channel "
            "ORDER BY 2 DESC", (since_iso,))
        by_channel = {r[0]: r[1] for r in await cur.fetchall()}
        cur = await self.conn.execute(
            "SELECT d.store_name, d.discount_value, COUNT(*) AS n FROM clicks c "
            "JOIN deals d ON d.deal_hash = c.deal_hash WHERE c.clicked_at >= ? "
            "GROUP BY c.deal_hash ORDER BY n DESC LIMIT 5", (since_iso,))
        top = [dict(r) for r in await cur.fetchall()]
        return {"total": sum(by_channel.values()), "by_channel": by_channel, "top": top}

    # -- key/value + run history (scheduler, watchdog) --------------------------------
    async def kv_get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        cur = await self.conn.execute("SELECT value FROM kv WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default

    async def kv_set(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT INTO kv (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        await self.conn.commit()

    async def record_run(self, scraped: int, parsed: int, llm_failed: int, new_deals: int,
                         error: Optional[str] = None) -> None:
        await self.conn.execute(
            "INSERT INTO runs (finished_at, scraped, parsed, llm_failed, new_deals, error) "
            "VALUES (?,?,?,?,?,?)",
            (utcnow_iso(), scraped, parsed, llm_failed, new_deals, error))
        await self.conn.execute(
            "DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY id DESC LIMIT 500)")
        await self.conn.commit()

    async def recent_runs(self, n: int = 5) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (n,))
        return [dict(r) for r in await cur.fetchall()]

    # -- backups ---------------------------------------------------------------------
    async def backup_to(self, dest_path: str) -> None:
        dst = await aiosqlite.connect(dest_path)
        try:
            await self.conn.backup(dst)
        finally:
            await dst.close()

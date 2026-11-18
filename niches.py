"""Niche definitions (niche.yaml) + matching deals to niches + channel lookup from .env."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from config import BASE_DIR

TIERS = ("free", "paid")


@dataclass
class Niche:
    id: str
    name: str
    emoji: str = "🏷️"
    stores: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    @property
    def _pattern(self) -> re.Pattern | None:
        if not self.keywords:
            return None
        words = sorted((re.escape(k.lower()) for k in self.keywords), key=len, reverse=True)
        return re.compile(r"(?<![a-z0-9])(" + "|".join(words) + r")(?![a-z0-9])", re.I)

    def matches(self, store_domain: str, text: str) -> bool:
        domain = (store_domain or "").lower()
        if any(domain == s or domain.endswith("." + s) for s in self.stores):
            return True
        pat = self._pattern
        return bool(pat and pat.search(text or ""))

    # -- channel config from .env --------------------------------------------
    def _env(self, suffix: str) -> str:
        return (os.getenv(f"{self.id.upper()}_{suffix}") or "").strip()

    def telegram_chat(self, tier: str) -> str:
        return self._env(f"{tier.upper()}_TELEGRAM")

    def discord_webhook(self, tier: str) -> str:
        return self._env(f"{tier.upper()}_DISCORD")

    @property
    def premium_url(self) -> str:
        return self._env("PREMIUM_URL")

    def channels(self, tier: str) -> list[tuple[str, str]]:
        """[(kind, target)] configured for this tier, e.g. [('telegram','@farmdeals')]."""
        out = []
        if self.telegram_chat(tier):
            out.append(("telegram", self.telegram_chat(tier)))
        if self.discord_webhook(tier):
            out.append(("discord", self.discord_webhook(tier)))
        return out


@lru_cache(maxsize=4)
def _load(path: str) -> tuple[Niche, ...]:
    p = Path(path)
    if not p.exists():
        return ()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = []
    for n in data.get("niches", []):
        out.append(Niche(id=str(n["id"]).lower(), name=n.get("name", n["id"]),
                         emoji=n.get("emoji", "🏷️"),
                         stores=[s.lower() for s in n.get("stores", [])],
                         keywords=[k.lower() for k in n.get("keywords", [])]))
    return tuple(out)


def load_niches(path: Path | None = None) -> list[Niche]:
    return list(_load(str(path or BASE_DIR / "niche.yaml")))


def get_niche(niche_id: str) -> Niche | None:
    return next((n for n in load_niches() if n.id == niche_id), None)


def match_niches(deal: dict, niches: list[Niche] | None = None) -> list[str]:
    niches = niches if niches is not None else load_niches()
    text = " ".join(str(deal.get(k) or "") for k in
                    ("summary", "discount_value", "store_name"))
    return [n.id for n in niches if n.matches(deal.get("store_domain", ""), text)]

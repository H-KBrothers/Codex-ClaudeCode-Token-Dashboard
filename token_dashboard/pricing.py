"""Pricing table + plan-aware cost formatting."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from .db import connect


def load_pricing(path: Union[str, Path]) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _tier_from_name(model: str) -> Optional[str]:
    m = (model or "").lower()
    if "haiku" in m:
        return "claude_haiku"
    if "sonnet" in m:
        return "claude_sonnet"
    if "opus" in m:
        return "claude_opus"
    if "fable" in m or "mythos" in m:
        return "claude_fable"
    if "mini" in m or "nano" in m:
        return "mini"
    if "gpt-5.5" in m:
        return "frontier"
    if "gpt-5" in m or "codex" in m or m.startswith("o"):
        return "large"
    return None


def _rates_for(model: str, pricing: dict) -> tuple[Optional[dict], bool]:
    rates = pricing["models"].get(model)
    estimated = False
    if rates is None:
        tier = _tier_from_name(model or "")
        if tier and tier in pricing["tier_fallback"]:
            rates = pricing["tier_fallback"][tier]
            estimated = True
        else:
            return None, True
    return rates, estimated


def cost_for(model: str, usage: dict, pricing: dict) -> dict:
    """Return {usd, estimated, breakdown}. usd=None when no tier match."""
    rates, estimated = _rates_for(model, pricing)
    if rates is None:
        return {"usd": None, "estimated": True, "breakdown": {}}
    bd = {
        "input":           usage["input_tokens"]            * rates["input"]           / 1_000_000,
        "output":          usage["output_tokens"]           * rates["output"]          / 1_000_000,
        "cache_read":      usage["cache_read_tokens"]       * rates["cache_read"]      / 1_000_000,
        "cache_create_5m": usage["cache_create_5m_tokens"]  * rates["cache_create_5m"] / 1_000_000,
        "cache_create_1h": usage["cache_create_1h_tokens"]  * rates["cache_create_1h"] / 1_000_000,
    }
    return {"usd": round(sum(bd.values()), 6), "estimated": estimated, "breakdown": bd}


def get_plan(db_path: Union[str, Path], default: str = "codex-free") -> str:
    with connect(db_path) as c:
        row = c.execute("SELECT v FROM plan WHERE k='plan'").fetchone()
    return row["v"] if row else default


def set_plan(db_path: Union[str, Path], plan: str) -> None:
    with connect(db_path) as c:
        c.execute("INSERT OR REPLACE INTO plan (k, v) VALUES ('plan', ?)", (plan,))
        c.commit()


def format_for_user(api_cost_usd: float, plan: str, pricing: dict) -> dict:
    p = pricing["plans"].get(plan, pricing["plans"]["api"])
    if plan == "api":
        return {"display_usd": api_cost_usd, "subtitle": None, "subscription_usd": None}
    if p["monthly"] == 0:
        return {
            "display_usd": api_cost_usd,
            "subtitle": f"{p['label']} selected; dollar amount is API-equivalent only",
            "subscription_usd": 0,
        }
    return {
        "display_usd":      api_cost_usd,
        "subtitle":         f"You pay ${p['monthly']}/mo on {p['label']}",
        "subscription_usd": p["monthly"],
    }

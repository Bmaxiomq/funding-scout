#!/usr/bin/env python3
"""Funding-rate scout — GitHub Actions serverless edition.

Public-repo safe. No hardcoded paths, no secrets, no host references.
Writes timestamped + latest snapshots. Sends Telegram on extreme funding.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HL_URL = "https://api.hyperliquid.xyz/info"
OUT_DIR = Path("data/funding")
JSONL = OUT_DIR / "funding_rates.jsonl"
LATEST = OUT_DIR / "funding_latest.json"
WATCH = ("BTC", "ETH", "SOL", "HYPE", "XRP", "DOGE", "BNB")
PERIODS_PER_YEAR = 3 * 365
TOP_N = 15
ABS_ANN_ALERT_PCT = 40.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def send_telegram(message: str) -> bool:
    """Send Telegram alert. Returns True if sent, False if skipped/failed."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"

    if dry_run:
        print("::notice::DRY_RUN=true, skipping Telegram")
        return False
    if not token or not chat_id:
        print("::warning::TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.load(resp)
        return result.get("ok", False)
    except Exception as e:
        print(f"::error::Telegram send failed: {e}")
        return False


def fetch_hl() -> list[dict]:
    body = json.dumps({"type": "metaAndAssetCtxs"}).encode()
    req = urllib.request.Request(
        HL_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "spectrequant-funding-scout/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        meta = json.load(resp)
    universe = meta[0].get("universe", [])
    ctxs = meta[1] if len(meta) > 1 else []
    rows: list[dict] = []
    for i, asset in enumerate(universe):
        if i >= len(ctxs):
            break
        ctx = ctxs[i]
        funding = float(ctx.get("funding") or 0.0)
        mark = float(ctx.get("markPx") or 0.0)
        oi = float(ctx.get("openInterest") or 0.0)
        coin = asset.get("name")
        rows.append(
            {
                "venue": "hyperliquid",
                "coin": coin,
                "funding_8h": funding,
                "funding_8h_pct": round(funding * 100, 6),
                "ann_pct": round(funding * PERIODS_PER_YEAR * 100, 2),
                "mark": mark,
                "open_interest": oi,
            }
        )
    rows.sort(key=lambda r: abs(r["ann_pct"]), reverse=True)
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"::group::Funding Rate Scout — {utc_now()}")

    t0 = time.time()
    try:
        rows = fetch_hl()
    except Exception as e:
        rec = {
            "ts": utc_now(),
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
        }
        print(f"::error::{rec}")
        with JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        sys.exit(1)

    by_coin = {r["coin"]: r for r in rows}
    watch = [by_coin[c] for c in WATCH if c in by_coin]
    top = rows[:TOP_N]
    outliers = [r for r in rows if abs(r["ann_pct"]) >= ABS_ANN_ALERT_PCT]

    print("-- majors --")
    for r in watch:
        print(
            f"{r['coin']:6} 8h={r['funding_8h_pct']:+.4f}%  ann={r['ann_pct']:+.1f}%  "
            f"mark={r['mark']}  oi={r['open_interest']:.0f}"
        )
    print(f"-- top {TOP_N} |ann| --")
    for r in top:
        print(
            f"{r['coin']:8} 8h={r['funding_8h_pct']:+.4f}%  ann={r['ann_pct']:+.1f}%  "
            f"mark={r['mark']}  oi={r['open_interest']:.0f}"
        )

    snapshot = {
        "ts": utc_now(),
        "status": "ok",
        "venue": "hyperliquid",
        "n_assets": len(rows),
        "duration_s": round(time.time() - t0, 2),
        "majors": watch,
        "top_abs_ann": top,
        "outlier_count": len(outliers),
        "outliers": outliers[:10],
    }

    ts_file = OUT_DIR / f"scout_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}.json"
    ts_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    with JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot) + "\n")

    LATEST.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    print(f"::notice::Wrote {ts_file}, {JSONL}, {LATEST}")
    print("::endgroup::")

    if outliers:
        lines = [
            "🚨 *Extreme Funding Alert*",
            f"_{utc_now()} UTC_",
            "",
            f"*{len(outliers)} assets* with |ann| ≥ {ABS_ANN_ALERT_PCT}%:",
            "",
        ]
        for r in outliers[:5]:
            emoji = "🟢" if r["ann_pct"] > 0 else "🔴"
            lines.append(
                f"{emoji} `{r['coin']:8}` {r['ann_pct']:+.1f}% ann "
                f"({r['funding_8h_pct']:+.4f}% 8h)"
            )
        if len(outliers) > 5:
            lines.append(f"_...and {len(outliers) - 5} more_")

        message = "\n".join(lines)
        sent = send_telegram(message)
        if sent:
            print(f"::notice::Telegram alert sent for {len(outliers)} outliers")
        else:
            print("::warning::Telegram alert not sent")


if __name__ == "__main__":
    main()

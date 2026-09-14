# Funding Rate Scout

Serverless GitHub Actions workflow that polls Hyperliquid funding rates every 4 hours, detects outliers (|ann| ≥ 40%), and commits timestamped snapshots to this repository.

## What it does

- **Data source**: Hyperliquid `metaAndAssetCtxs` (public, no API key required)
- **Schedule**: Every 4 hours at minute 7 (avoids GitHub top-of-hour congestion)
- **Outputs**:
  - `data/funding/scout_YYYY-MM-DD_HHMMSS.json` — immutable timestamped snapshot
  - `data/funding/funding_latest.json` — latest snapshot for quick dashboard reference
  - `data/funding/funding_rates.jsonl` — append-only ledger (excluded from git, kept as artifact)
- **Alerts**: Telegram message when any asset has |annualized funding| ≥ 40%

## Setup

1. Fork or clone this repo
2. Add repository secrets (Settings → Secrets and Variables → Actions):
   - `TELEGRAM_BOT_TOKEN` — from BotFather
   - `TELEGRAM_CHAT_ID` — your chat ID
3. Enable Actions (if forked)
4. Trigger manually: Actions → Funding Rate Scout → Run workflow → `dry_run=true` to test

## Local run

```bash
pip install requests
python scripts/funding_rate_scout_gha.py
```

## Data format

Each snapshot contains:
- `ts`: ISO-8601 UTC timestamp
- `status`: `ok` or `error`
- `venue`: `hyperliquid`
- `n_assets`: number of assets scanned
- `majors`: watchlist (BTC, ETH, SOL, HYPE, XRP, DOGE, BNB)
- `top_abs_ann`: top 15 assets by |annualized funding|
- `outlier_count`: number of assets with |ann| ≥ 40%
- `outliers`: details of extreme funding assets

## Cost

- GitHub Actions: ~15 min/run × 6 runs/day = ~2,700 min/month (exceeds free tier 2,000 min)
- Recommendation: reduce cron to `*/6` (every 6h) for ~1,800 min/month, or purchase additional minutes
- Artifact storage: ~50 KB/run × 180 runs = ~9 MB (well within 500 MB free tier)

## License

MIT

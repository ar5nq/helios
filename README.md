# Helios

A genetic-algorithm strategy breeder + backtester that outputs **signals for a human to act on**,
instead of auto-trading through MetaTrader 5.

## Architecture

```
engine/
  genome.py      -- strategy DNA: bias, signal indicator, filter, exec/RR, mutation, crossover
  data_feed.py    -- pulls OHLC price history (yfinance: FX majors, gold, indices -- no API key)
  backtest.py     -- scores a genome on TRAIN (in-sample) vs TEST (out-of-sample) data
  campaign.py     -- runs N generations of breeding, vaults survivors that clear the fitness gate

signals/
  signal_engine.py -- emits a signal from a vaulted genome; tracks taken/skipped + win/loss/breakeven
                       per signal, and computes a genome's LIVE win rate from real outcomes
                       (this is your decay-detection loop, replacing MT5 auto-execution)

news/
  calendar_feed.py -- pulls ForexFactory's public weekly calendar JSON, flags high-impact events
                       (Financial-Juice-style alerting, built on the same public data)

data/
  vault.json       -- promoted strategies (the "strategy vault")
  signal_log.json  -- every signal ever emitted + its outcome
```

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Usage

Breed a campaign of strategies for a symbol/timeframe:
```bash
python run.py breed --symbol EURUSD --timeframe H1 --generations 5 --population 40
```
This populates `data/vault.json` with any genome whose out-of-sample fitness clears the gate.

Emit a signal from a vaulted genome (you decide when its rule fires -- this MVP does not yet
run genomes live against streaming data; see Roadmap):
```bash
python run.py signal --genome B8CE8E --symbol EURUSD --timeframe H1 --direction BUY \
  --entry 1.1050 --stop 1.1010 --target 1.1130
```

Check today's high-impact news:
```bash
python run.py news
```

## Why no MT5

The genome/backtest/campaign logic is identical to what an MT5-export version would need --
the only thing removed is auto-execution. Signals are advisory: you take them or skip them,
and report the real outcome, which is what keeps the live win-rate honest.

## Roadmap (not yet built)
- [ ] Live genome runner: poll `data_feed` on a schedule and auto-call `emit_signal` when a
      vaulted genome's rule condition fires on the newest bar (cron / APScheduler)
  - [ ] Push/SMS/Telegram delivery for new signals and news alerts
- [ ] Dashboard (the UI in your screenshots) as a small Flask/FastAPI + React app reading from
      `data/vault.json` and `data/signal_log.json`
- [ ] Portfolio correlation grid (group vaulted genomes, screen for low return correlation)
- [ ] Swap `data/*.json` for SQLite once signal volume grows

## Data source caveats
- `yfinance` has no official SLA; if Yahoo changes its endpoint this breaks and needs a patch.
- ForexFactory's calendar feed is an unofficial public JSON endpoint with no auth/versioning
  guarantee -- same caveat applies.

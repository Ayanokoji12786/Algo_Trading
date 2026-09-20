# Algo Trading — Systematic Research Platform

A **research and paper-trading system**, not a live trading bot. It exists to answer one
question honestly: *does a researched trading hypothesis survive implementation, realistic
costs, point-in-time data discipline, and adversarial testing?* — not to maximize a backtest
number. Live trading is structurally disabled; see [Status](#status--what-this-is-not).

Built from two independent research documents (full text preserved as structured extractions
in `Docs/`, since the original PDFs are intentionally not committed to this repo):

1. **Global multi-asset futures** — a time-series momentum/trend system across equity index,
   rates, FX, and commodity futures, with a disabled carry satellite.
2. **India NSE + MCX** — a blended portfolio of NSE cross-sectional equity momentum and MCX
   commodity trend (50:50 risk-weighted), plus a standalone (never-blended) MCX curve-carry
   strategy.

Both run today against **synthetic, fabricated data** — real broker/vendor wiring exists
(Zerodha, Angel One, INDmoney, or any CSV export) but has not been execution-tested against a
live account. Every number this system currently produces is a *pipeline-correctness check*,
never a performance claim. That distinction is repeated throughout the code and docs on
purpose — see [`Docs/Final_Report.md`](Docs/Final_Report.md) for the full, warts-and-all
account, including two real bugs that were found and fixed along the way (one flipped a
headline result's sign).

---

## Table of contents

- [What this actually does](#what-this-actually-does)
- [Project structure](#project-structure)
- [How it works, end to end](#how-it-works-end-to-end)
- [The two systems](#the-two-systems)
- [Getting started](#getting-started)
- [Running it](#running-it)
- [Using real market data](#using-real-market-data)
- [Paper trading](#paper-trading)
- [Do you need to deploy this anywhere?](#do-you-need-to-deploy-this-anywhere)
- [Testing](#testing)
- [Where to read more](#where-to-read-more)
- [Status / what this is not](#status--what-this-is-not)

---

## What this actually does

At its core this is a **backtesting and paper-trading engine** for systematic strategies,
built around one non-negotiable rule: **no code path may ever see data from after the moment
it's making a decision.** That's enforced structurally (`PointInTimeStore`), not by
convention, and it's tested directly (leakage-regression tests spawn separate processes and
truncated data stores to prove decisions don't change when future data exists but shouldn't be
visible).

Around that core, the system:

- Turns two research documents into frozen, versioned, testable strategy code — never
  silently "improving" a parameter the research specified.
- Runs full backtests with realistic transaction costs, execution delays, and position-sizing
  rules, on both synthetic data (built in) and — once you wire it in — real market data.
- Stress-tests itself: parameter-neighborhood sweeps, leave-one-out attribution, cost/delay
  stress, walk-forward/holdout splits, a Deflated Sharpe Ratio and Probability-of-Backtest-
  Overfitting correction for multiple testing, and Monte Carlo resampling.
- Replays the exact same strategy logic in a "paper trading" loop (no shortcuts, no
  simplified parallel implementation) so a backtest and a paper run can never silently
  diverge — this is verified by an automated parity test, not just asserted in a comment.
- Refuses, at the code level, to ever place a live order. `mode="live"` cannot even be
  constructed.

## Project structure

```
Trading BOT 2.0/
├── README.md                     ← you are here
├── pyproject.toml                ← package metadata + dependencies
├── Docs/
│   ├── Implementation_Spec.md    ← global-futures research: extraction, audit, architecture
│   ├── India_Implementation_Spec.md  ← India NSE+MCX research: same treatment
│   ├── Vendor_Integration.md     ← how to wire in Zerodha/Angel One/INDmoney/any CSV vendor
│   └── Final_Report.md           ← the authoritative status report — read this first
├── scripts/
│   └── vendor_smoke_test.py      ← manual script to test a real broker connection yourself
├── experiments/
│   ├── log.jsonl                 ← append-only experiment ledger (every run, incl. failures)
│   └── reports/                  ← CSV/JSON output from the CLI runs (robustness sweeps, etc.)
├── src/trading_system/
│   ├── data/                     ← point-in-time data layer
│   │   ├── interfaces.py         ←   ContractMeta, DataSource protocol (the vendor contract)
│   │   ├── pit_store.py          ←   PointInTimeStore — the leakage-safety boundary
│   │   ├── synthetic.py          ←   fabricated global-futures data (development/testing)
│   │   ├── synthetic_equity.py   ←   fabricated NSE-style equity data
│   │   ├── synthetic_curve.py    ←   fabricated MCX-style multi-expiry commodity data
│   │   ├── combined.py           ←   merges multiple DataSources into one universe
│   │   ├── roll.py               ←   futures contract-roll rule (front/next contract logic)
│   │   └── filtered.py           ←   leave-one-out universe filtering, for robustness tests
│   ├── brokers/                  ← real vendor adapters (all implement the DataSource contract)
│   │   ├── base.py               ←   shared chunking/caching/normalization helpers
│   │   ├── zerodha_kite.py       ←   Zerodha Kite Connect
│   │   ├── angel_one.py          ←   Angel One SmartAPI
│   │   ├── indmoney.py           ←   INDmoney / INDstocks API
│   │   └── local_csv.py          ←   generic CSV/Parquet adapter — works with ANY vendor export
│   ├── features/                 ← pure, PIT-safe feature functions
│   │   ├── returns.py, volatility.py, trend_signal.py, cross_sectional.py, regime.py
│   ├── strategies/                ← the actual trading logic, one file per strategy
│   │   ├── trend.py               ←   global-futures 63/126/252-day trend ensemble
│   │   ├── carry.py + carry_activation.py  ← global carry satellite (built, disabled)
│   │   ├── cross_sectional_momentum.py     ← EQ_MOM_01 (NSE equity momentum)
│   │   ├── mcx_trend_sleeve.py             ← MCX_TREND_01 (MCX commodity trend)
│   │   └── mcx_carry.py                    ← MCX_CARRY_01 (standalone only, never blended)
│   ├── portfolio/                 ← turns strategy signals into position sizes
│   │   ├── sizing.py, aggregation.py       ← global-futures hierarchical risk sizing
│   │   ├── blend.py, covariance.py         ← India blended-portfolio risk-share + vol targeting
│   │   └── participation.py                ← liquidity participation cap
│   ├── execution/                 ← transaction cost + execution-timing models
│   │   ├── costs.py, india_costs.py, simulator.py
│   ├── backtest/                  ← the engines and every statistical test
│   │   ├── engine.py              ←   global-futures backtest engine
│   │   ├── blended_engine.py      ←   India per-sleeve blended backtest engine
│   │   ├── metrics.py             ←   Sharpe/Sortino/drawdown/Calmar/turnover etc.
│   │   ├── attribution.py, robustness.py, validation_split.py, regime_report.py
│   │   ├── dsr.py                 ←   Deflated Sharpe Ratio (multiple-testing correction)
│   │   ├── pbo.py                 ←   Probability of Backtest Overfitting (CSCV)
│   │   └── monte_carlo.py         ←   block-bootstrap + trade-order-permutation resampling
│   ├── live/                      ← paper trading + hard risk safeguards
│   │   ├── guardrails.py          ←   data staleness, daily loss, drawdown, duplicate orders
│   │   └── paper/
│   │       ├── paper_trader.py         ← global-futures paper trader
│   │       └── blended_paper_trader.py ← India blended-portfolio paper trader
│   ├── config/                    ← every tunable parameter lives here, nowhere else
│   │   ├── schema.py              ←   global-futures SystemConfig
│   │   └── india_schema.py        ←   India IndiaSystemConfig
│   ├── experiments/
│   │   └── tracker.py             ←   append-only experiment ledger
│   ├── cli/                       ← entry points you actually run
│   │   ├── run_backtest.py               ← single global-futures backtest
│   │   ├── run_robustness_suite.py       ← the full global-futures statistical battery
│   │   └── run_india_blended_backtest.py ← the India blended portfolio + standalone sleeves
│   └── util.py                    ← stable_hash, validate_symbol_name (security helpers)
└── tests/
    ├── unit/          ← ~50 files, one concern each
    └── integration/   ← full pipeline, leakage-regression, and parity tests
```

## How it works, end to end

```
  DataSource (synthetic or real vendor)
        │  get_universe() / get_prices(symbol)
        ▼
  PointInTimeStore                    ← the leakage-safety boundary. Everything downstream
        │  history_as_of(symbol, as_of)   can ONLY ask "what did we know as of this date?"
        ▼
  features/*.py                        ← pure functions: returns, vol, trend score,
        │                                 cross-sectional z-scores, regime diagnostics
        ▼
  strategies/*.py                      ← turns features into a directional score per
        │                                 instrument (or, for EQ_MOM_01/MCX sleeves,
        │                                 a fully-sized weight per instrument directly)
        ▼
  portfolio/sizing.py or blend.py      ← vol-scales, risk-equalizes across asset classes
        │                                 or sleeves, applies caps, targets a portfolio
        │                                 volatility (zero-correlation assumption for the
        │                                 global system; rolling covariance for India)
        ▼
  execution/costs.py + simulator.py    ← charges realistic transaction costs, enforces
        │                                 "you can't trade on information you don't have yet"
        ▼
  backtest/engine.py  or  blended_engine.py     ← runs the whole thing day-by-day, produces
        │                                          an equity curve + trade log
        ▼
  backtest/metrics.py, dsr.py, pbo.py,          ← every statistical view: performance,
  monte_carlo.py, attribution.py, robustness.py    multiple-testing correction, stress tests
        ▼
  live/paper/*.py     ← the EXACT SAME strategy/sizing code, replayed one day at a time,
                          with guardrails, for a live-style dry run (no live feed yet)
```

The same strategy and sizing code is used by the backtest engine and the paper trader — there
is no separate "simplified" paper-trading implementation. A dedicated parity test
(`tests/integration/test_blended_paper_trader.py`) proves the two stay byte-identical.

## The two systems

| | Global futures | India NSE + MCX |
|---|---|---|
| Universe | Equity index / rates / FX / commodity futures (4 asset classes) | NSE equities + MCX commodity futures |
| Core strategy | 63/126/252-day trend ensemble | EQ_MOM_01 (equity momentum) + MCX_TREND_01 (commodity trend), blended 50:50 |
| Satellite | Carry (disabled, built for later validation) | MCX_CARRY_01 (standalone only — never blended in, per its own research's integration rule) |
| Rebalance | Weekly (configurable) | Monthly (equity) + daily (commodity), running on independent schedules in one portfolio |
| Sizing | Hierarchical risk parity, zero-correlation vol estimate | Equal risk-share blend + rolling-covariance vol targeting |
| Cost model | Generic per-asset-class bps | Itemized Indian statutory costs (STT, stamp duty, SEBI fee, GST) |
| Entry point | `cli/run_backtest.py`, `cli/run_robustness_suite.py` | `cli/run_india_blended_backtest.py` |

## Getting started

Requires Python 3.10+.

```bash
cd "Trading BOT 2.0"
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

That installs the package in editable mode plus `pytest`. No external services, API keys, or
accounts are needed for anything below — everything runs against synthetic data out of the box.

## Running it

```bash
# One backtest of the global-futures trend baseline
python -m trading_system.cli.run_backtest

# The full statistical battery: parameter sweeps, leave-one-out, cost/delay
# stress, DSR, PBO, Monte Carlo (~1-2 minutes)
python -m trading_system.cli.run_robustness_suite

# The India blended portfolio + each sleeve standalone + the carry activation gate
python -m trading_system.cli.run_india_blended_backtest
```

Each prints a full JSON metrics report to the console and writes CSV/JSON artifacts to
`experiments/reports/`, plus an entry to the append-only `experiments/log.jsonl` ledger.
**Every number is a pipeline-correctness check on fabricated data** — read the printed
warnings; don't mistake a positive or negative Sharpe on synthetic data for a real finding.

## Using real market data

Nothing about the strategy, sizing, or backtest code changes — only the `DataSource` you hand
to `PointInTimeStore` changes. Four adapters exist in `src/trading_system/brokers/`:

- **Zerodha (Kite Connect)**, **Angel One (SmartAPI)**, **INDmoney (INDstocks API)** — built
  against each vendor's own documented API, unit-tested against mocked clients, but **not yet
  execution-tested against a live account** in this environment.
- **Any other vendor** — export historical data to CSV/Parquet and use `LocalFileDataSource`;
  zero new code required.

Full instructions, instrument-mapping examples, and the credential policy (this codebase
**never** accepts or stores API keys/passwords — you authenticate yourself, in your own
script, and hand this system an already-authenticated client object) are in
[`Docs/Vendor_Integration.md`](Docs/Vendor_Integration.md). Before trusting a real vendor
adapter, run `python scripts/vendor_smoke_test.py` with your own credentials filled in.

## Paper trading

```python
from trading_system.config.defaults import default_config
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic import SyntheticFuturesDataSource
from trading_system.strategies.trend import TrendStrategy
from trading_system.live.paper.paper_trader import PaperTrader

config = default_config()
store = PointInTimeStore(SyntheticFuturesDataSource(config.data))
trader = PaperTrader(config, store, TrendStrategy(config.trend))

records = trader.run_replay(list(store.trading_calendar()[-30:]))
for r in records:
    print(r.decision_date, r.portfolio_value, r.intended_trade)
```

Swap `SyntheticFuturesDataSource` for a real vendor adapter and this becomes a genuine
(if currently un-live-verified) daily paper-trading loop. The India equivalent is
`BlendedPaperTrader` in `live/paper/blended_paper_trader.py`, used the same way with a list of
`SleeveSpec`s. Guardrails (`live/guardrails.py`) trip and halt the replay on data staleness,
excessive daily loss, drawdown breach, or too many simultaneous positions.

## Do you need to deploy this anywhere?

**Not to use it as a research tool — no.** This is a Python library and a set of CLI scripts,
not a web service. There's no server, no API, no frontend. You run it exactly the way you'd
run any Python script: on your own laptop, a work machine, or any cloud VM if you want it
running on something that stays on. `pip install -e .` is the entire "deployment."

**If you want daily paper trading against real data**, you need something that runs your
script once a day at market open/close and stays powered on at that time:

- **Simplest**: your own machine + a scheduled job — `cron` (macOS/Linux) or Task Scheduler
  (Windows) calling a small script that builds a real `DataSource`, steps the paper trader
  forward one day, and logs the result somewhere you can check.
- **If your machine isn't reliably on**: a small always-on cloud VM (a $5-6/month DigitalOcean
  droplet, an AWS EC2 t3.micro/t4g.micro, a Raspberry Pi at home, etc.) running the same cron
  job. There's nothing India/US-region-specific about this — pick whatever's cheapest/closest
  to your broker's API.
- No GPU, no database, no web server, and no inbound network access are needed anywhere in
  this system as it stands today.

**If you eventually want real (live) trading**: this system will not do that no matter what
you configure — `mode="live"` cannot be constructed (`config/schema.py`'s `__post_init__`
raises unconditionally), and there is no order-placement code anywhere in the strategy/paper-
trading path. That's intentional, not a missing feature to work around: building a real
execution layer (order placement, fills, reconciliation, monitoring, kill-switches under real
money) is a substantially larger and different engineering job than what's built here, and per
the original research brief this system defaults to research-only until deliberately extended.
If you want to go there eventually, treat it as a new, carefully-scoped phase — not a config
flag.

## Testing

```bash
python -m pytest -q          # all 202 tests, ~1.5 minutes
python -m pytest tests/unit  # fast, isolated
python -m pytest tests/integration  # full pipeline + leakage + parity tests
```

Tests are the load-bearing documentation of correctness here — several real bugs (a scope bug
that let one strategy score another market's instruments, a risk-equalization formula that
inverted itself, a non-deterministic RNG seed that silently flipped a headline result's sign
between runs, a path-traversal hole in the data cache) were caught this way, not by inspection.
See `Docs/Final_Report.md`'s audit section for the full list.

## Where to read more

- **[`Docs/Final_Report.md`](Docs/Final_Report.md)** — start here. The authoritative,
  continuously-updated status report: what's built, what's tested, what every synthetic-data
  number does and doesn't mean, every bug found and fixed, and what's explicitly still open.
- **[`Docs/Implementation_Spec.md`](Docs/Implementation_Spec.md)** — the global-futures
  research, extracted and audited claim-by-claim before any code was written.
- **[`Docs/India_Implementation_Spec.md`](Docs/India_Implementation_Spec.md)** — same
  treatment for the India NSE+MCX research, plus how the two systems' parameters were
  deliberately kept separate rather than silently merged.
- **[`Docs/Vendor_Integration.md`](Docs/Vendor_Integration.md)** — broker/vendor setup.

## Status / what this is not

- **Not evidence that any strategy "works."** Every backtest number reported so far is against
  fabricated synthetic data, generated specifically to test whether the code is correct and
  leakage-free — never claimed to resemble real markets.
- **Not a live trading bot**, and structurally cannot become one via configuration.
- **Not execution-verified against any real broker account** — the vendor adapters are built
  correctly against public documentation but unverified live; run the smoke test first.
- **Is** a leakage-safe, tested, reproducible research pipeline that faithfully implements two
  research specifications, complete with the statistical rigor (multiple-testing correction,
  overfitting probability, Monte Carlo uncertainty bounds) needed to eventually trust a result
  from it, once real data is wired in.

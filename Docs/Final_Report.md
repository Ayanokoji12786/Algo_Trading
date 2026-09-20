# Final Engineering Report

Produced per `Prompt.md` §38–39 (the instructions document has since been removed from this
repo at the user's request — see git history commit `d57d678` — but its requirements remain
what this report was built against; `Docs/Implementation_Spec.md` retains the full extracted
text of its relevant sections). Source research: `Research.md` (also since removed from the
repo; `Docs/Implementation_Spec.md` §1 retains a structured extraction of everything used).

**Read this report as a status of a research pipeline, not a trading recommendation.** Every
backtest number in this document comes from a synthetic, fabricated dataset used to test
whether the *code* works — none of it is evidence that the researched trend hypothesis makes
money in real markets. That replication has not happened yet (see §J, §O).

---

## A. Implemented System

A modular Python research system (`src/trading_system/`, 90 passing tests) implementing:

- A point-in-time data boundary that structurally prevents look-ahead (`data/pit_store.py`).
- A frozen 63/126/252-day time-series-momentum ensemble as the sole active strategy (`strategies/trend.py`).
- Hierarchical, vol-scaled, risk-equalized position sizing to a configurable portfolio vol target (`portfolio/sizing.py`).
- A cost-aware, weight-based backtest engine with configurable rebalance frequency and execution delay (`backtest/engine.py`).
- A robustness/attribution suite: parameter-neighborhood sweeps, cost/delay/rebalance sweeps, leave-one-out tests, subperiod and holdout attribution, and a Deflated Sharpe Ratio multiple-testing correction (`backtest/robustness.py`, `attribution.py`, `dsr.py`).
- A carry satellite strategy, built but disabled by default, with its own (partial) activation gate and a multi-strategy equal-risk aggregator for the trend+carry complementarity comparison (`strategies/carry.py`, `carry_activation.py`, `portfolio/aggregation.py`).
- A paper-trading mode that reuses the exact backtest strategy code, plus hard risk guardrails and a mode gate that structurally blocks live trading (`live/`).
- A vendor-agnostic data layer with ready adapters for Zerodha Kite Connect, Angel One SmartAPI, and INDmoney/INDstocks, plus a generic file-based adapter for any other vendor (`brokers/`).
- An append-only experiment log recording every configuration tested, including the ones that performed badly (`experiments/tracker.py`).

**What runs today end-to-end**: `python -m trading_system.cli.run_backtest` (single baseline run) and `python -m trading_system.cli.run_robustness_suite` (the full suite), both against **synthetic data only**. No real market data has been loaded into this system yet.

---

## B. Research Mapping

| Research/Prompt requirement | Status | Implementation |
|---|---|---|
| 63/126/252-day trend ensemble | **Done** | `features/trend_signal.py`, `strategies/trend.py` |
| Vol-scaled sizing, hierarchical risk equalization, vol target | **Done** | `portfolio/sizing.py` |
| Weekly rebalance baseline, daily signal calc | **Done** | `backtest/engine.py`, `config/schema.py` |
| Execution timing / delay (0/+1/+2 sessions) | **Done** | `execution/simulator.py`, `robustness.execution_delay_sweep` |
| Transaction cost model | **Partial** | `execution/costs.py` — single per-asset-class bps figure only; roll costs, financing, and taxes are explicitly *not* modeled (needs real contract/jurisdiction data) |
| Cost stress (base/2×/3×) | **Done** | `CostConfig.scenario`, `robustness.cost_scenario_sweep` |
| Carry satellite, disabled by default | **Done** | `strategies/carry.py`, `SystemConfig.carry_enabled` |
| Carry activation gate | **Partial** | `strategies/carry_activation.py` — implements profitability/cost-survival/correlation criteria only; parameter-stability and cross-fold/regime checks are explicitly out of scope until real data exists (documented in the module itself) |
| Regime diagnostics (computed, not traded on) | **Not built** | No `features/regime/` module exists. This is a real gap against Research.md's explicit requirement — see §N |
| No ML in baseline; `challenger_models/` interface | **Partial** | No ML anywhere in the strategy path (principle honored), but no `challenger_models/` scaffold was built either |
| Value/profitability equity sleeve | **Not built** — explicitly deferred, blocked on point-in-time fundamentals data (`Implementation_Spec.md` §3) |
| Point-in-time data discipline | **Done** | `data/pit_store.py` + dedicated leakage regression tests |
| Backtest engine (entry/exit/size/cash/costs/execution timing) | **Partial** | `backtest/engine.py` — no partial fills, market-hours/trading-restriction modeling, or corporate-action handling (none of these concepts exist in the synthetic data) |
| Backtest metrics | **Partial** | `backtest/metrics.py` has CAGR/vol/Sharpe/Sortino/max DD+duration/Calmar/turnover; win rate, avg win/loss, profit factor, expectancy, and expected-shortfall/tail-loss metrics are **not implemented** |
| Benchmarks (buy-and-hold, simple trend/momentum, random entry) | **Not built** | No benchmark comparison module exists |
| Strategy-level attribution | **Partial** | Subperiod and leave-one-out attribution exist; correlation-based attribution only implemented for the trend-vs-carry pair, not generalized to N strategies |
| Complementarity test (A alone / B alone / A+B) | **Done** | `tests/integration/test_complementarity.py`, `cli/run_robustness_suite.py` |
| Parameter robustness (neighborhoods) | **Done** | `robustness.lookback_neighborhood_sweep`, `vol_window_sweep` |
| Out-of-sample / holdout | **Done** (mechanism); **not yet meaningful** (synthetic data) | `attribution.train_test_split_metrics` |
| Walk-forward testing | **Partial** | Subperiod consistency checking is implemented; true walk-forward *retraining* isn't applicable yet since the baseline has no fitted parameters (documented explicitly in `attribution.py`) |
| Stress testing (Prompt.md §24's full list) | **Partial** | Cost/delay/leave-one-out done; missing data, noisy data, crisis periods, rapid reversals, large gaps, reduced liquidity — **not done** |
| Monte Carlo / trade-order analysis | **Not built** | |
| Overfitting defense / experiment log | **Done** | `experiments/tracker.py` (append-only, every sweep run logged); `backtest/dsr.py` (Deflated Sharpe Ratio) |
| No data leakage | **Done** | Structural (`PointInTimeStore.history_as_of`) + regression tests + a dedicated direction-sanity check |
| Reproducibility | **Done** | Every parameter is a `config/schema.py` dataclass field; every experiment record stores its full config |
| Testing (unit + integration) | **Done** | 90 tests |
| Visualization | **Not built** | Only CSV/JSON artifacts and console tables exist — no equity-curve/drawdown/heatmap plots |
| Research dashboard | **Not built** | |
| Paper-trading mode | **Done** (mechanism); **limited** (no live feed) | `live/paper/paper_trader.py` |
| Live-trading gating | **Done** | `SystemConfig.mode="live"` is hard-blocked at construction |
| Risk safety guardrails | **Partial** | Data staleness, daily loss, drawdown, position count, duplicate orders, emergency shutdown implemented; API-failure and order-rejection handling are out of scope (no live broker connection exists to fail) |
| Vendor/data integration | **Done** (adapters); **untested live** | `brokers/` — Zerodha/Angel One/INDmoney/generic CSV |

---

## C. Data

**Used so far**: exclusively a synthetic, fabricated dataset (`data/synthetic.py`) — regime-switching random walks across 4 asset-class buckets (equity index, rates, FX, commodities), generated purely to exercise the pipeline. It is not real market data and carries no information about real markets.

**Available but untested against a real account**: adapters for Zerodha Kite Connect, Angel One SmartAPI, and INDmoney/INDstocks, plus a generic CSV/Parquet adapter for any other vendor (`brokers/`, `Docs/Vendor_Integration.md`). None have been run against a live authenticated session in this environment — Kite's connected session here isn't logged in, and no Angel One or INDmoney credentials were available. The adapters are built against each vendor's own public documentation and unit-tested against mocked clients matching that documented schema.

**Not yet available at all**: real contract-level futures data (rolls, margin, actual tradable contracts), point-in-time fundamentals (blocks the value/profitability sleeve entirely), and any real cost/tax feed (India STT figures used anywhere would need live verification, not the dated snapshot in the original research document).

---

## D. Features

`return_63d`, `return_126d`, `return_252d` (log returns), `sign()` of each, the composite trend score (mean of the three signs), and a 60-day EWMA annualized volatility estimate. That is the complete feature set — no RSI/MACD/Bollinger/ADX or other indicator stack was added, per the research's explicit instruction not to stack technical transforms of the same price history as if they were independent information.

---

## E. Strategies

**Trend (active)**: the frozen 63/126/252 ensemble described above, vol-scaled and risk-equalized. This is the only strategy contributing to the production baseline's portfolio.

**Carry (built, disabled)**: consumes scores through a `CarrySignalSource` protocol so a real vendor-backed carry input (FX rate differentials, bond term spreads, commodity roll yield, equity dividend yield — none of which this system has) can be substituted later without touching the strategy class. The only implementation of that protocol today, `SyntheticCarrySignalSource`, is pure fabricated noise with its own independent RNG stream, used solely to verify the module's wiring (disabled flag, activation gate, complementarity test) end to end. It correctly failed its own activation gate in testing (see §M) — a positive sign that the gate isn't naively permissive, not a finding about real carry.

**Not built**: cross-sectional equity momentum (explicitly a challenger/benchmark only per the research, never scheduled for this phase), value/profitability, ML challengers.

---

## F. Regime Detection

**Not implemented.** Research.md requires computing (but not trading on) trailing volatility percentile, trend strength/dispersion, cross-asset correlation, valuation states, term spread, liquidity proxies, and inflation/rate regime variables. None of this exists in the codebase. This is the single largest gap between the research specification and what was actually built — see §N.

---

## G. Signal Combination

Only exercised for the trend+carry complementarity comparison (carry is disabled in production). `portfolio/aggregation.py` implements **equal ex-ante risk per strategy**: each active strategy receives an equal share of the total risk budget, then equalizes across its own asset classes exactly as the single-strategy path does — sharing the same underlying sizing math (`portfolio/sizing.py`) so the two paths cannot silently diverge.

---

## H. Risk Management

Portfolio-level: vol targeting (10% annualized, explicitly a research convention, not an evidence-derived optimum), instrument/asset-class concentration caps, gross leverage cap — all under a documented zero-cross-instrument-correlation simplification for the portfolio-vol estimate (`portfolio/sizing.py`'s module docstring).

Operational: `live/guardrails.py` implements data-staleness detection, daily-loss limit, drawdown limit, maximum simultaneous positions, duplicate-order rejection, and an emergency-shutdown latch that blocks all further action once tripped. API-failure and order-rejection handling are explicitly out of scope — there is no live broker connection for either to apply to yet.

Deployment gating: `SystemConfig.mode` supports `research`/`backtest`/`paper` only — constructing `mode="live"` raises `ValueError` unconditionally, since no live execution path exists to gate.

---

## I. Backtest Results (synthetic data)

Baseline configuration (63/126/252 lookback, 60-day EWMA vol, 10% vol target, weekly rebalance, 0-session delay, base cost scenario), full 2000–2023 synthetic history, 16 instruments across 4 asset-class buckets:

| Metric | Value |
|---|---|
| Total return | −22.2% |
| CAGR | −1.04% |
| Annualized volatility | 5.95% |
| Sharpe | **−0.140** |
| Sortino | −0.228 |
| Max drawdown | −36.7% |
| Max drawdown duration | 3,245 days |
| Calmar | −0.028 |
| Avg turnover / rebalance | 0.42 |

**The frozen baseline is net-negative on this synthetic dataset.** Before reporting this at face value, a dedicated direction-sanity check (`tests/integration/test_strategy_sanity.py`) confirmed the strategy correctly goes long on a monotonic uptrend and short on a monotonic downtrend, and profits from either after near-zero costs — ruling out a sign/wiring bug. The negative result is a genuine property of this synthetic regime-switching dataset/parameter combination, most plausibly whipsaw losses where the 252-day lookback frequently straddles a regime transition (synthetic regimes last ~250–500 days). Per Prompt.md §37, this is reported as-is, not tuned away — and it says nothing about real markets, since the data is fabricated.

Leave-one-asset-class-out attribution shows this is *not* uniform: removing `equity_index` flips the result to a small positive Sharpe (+0.014), removing `commodities` also flips it positive (+0.112), while removing `rates` or `fx` makes it *worse* (−0.274, −0.268). On this dataset, the equity-index and commodities buckets are the drag; rates and FX are contributing positively. This kind of concentration is exactly what leave-one-out testing is supposed to surface (Prompt.md §21/§24).

Full sweep tables: `experiments/reports/robustness_suite_v1/*.csv`.

---

## J. Out-of-Sample Results

Chronological 80/20 split (final ~20% of the date range reserved, split date 2019-03-14):

| | In-sample | Holdout |
|---|---|---|
| Sharpe | −0.134 | −0.161 |
| CAGR | −1.00% | −1.19% |
| Max drawdown | −28.2% | −19.9% |

Consistent in sign and rough magnitude between segments — the holdout didn't reveal a sharp additional degradation, but both segments are negative, so there is nothing positive being "confirmed" here either. **This is a mechanism check, not a real out-of-sample validation** — real OOS validation requires the real-data replication that hasn't happened yet.

---

## K. Walk-Forward Results

Yearly subperiod breakdown (`experiments/reports/robustness_suite_v1/subperiod_breakdown.csv`) shows high year-to-year dispersion: clearly positive years (2001: Sharpe 1.79, 2005: 1.08, 2007: 1.56) alongside clearly negative years (2002: −1.21, 2006: −1.49, 2016: −1.64, 2020: −1.58). This is consistent with a trend follower that captures clean regimes well but suffers during transition years, on a dataset engineered to have exactly that regime structure.

**Important scope limitation, stated plainly**: this is subperiod *consistency* reporting, not walk-forward *retraining*. The baseline has no fitted parameters (63/126/252, the vol window, and the risk targets are frozen research inputs), so there is nothing to re-estimate fold over fold. True walk-forward validation in the classic sense only becomes meaningful once a fitted component exists (e.g., an ML challenger) — this is documented directly in `backtest/attribution.py`'s module docstring so the distinction isn't lost later.

---

## L. Stress Test Results

Implemented and run: transaction-cost stress (base/2×/3×: Sharpe −0.140 → −0.193 → −0.245, monotonically worse as expected), execution-delay stress (0/1/2 sessions: −0.140/−0.153/−0.135, no clear monotonic pattern — within noise), rebalance-frequency comparison (weekly −0.140 vs. daily −0.136, similar despite daily's turnover being ~2.4× higher), and full leave-one-asset-class-out / leave-one-instrument-out sweeps (§I).

**Not implemented**: missing-data handling stress, noisy-data injection, distinct high-/low-volatility subperiod splits, crisis-period analysis (the synthetic data has no real crises to test against), rapid-reversal stress, large-gap stress, reduced-liquidity stress, and Monte Carlo trade-order/return-sequence analysis. All of Prompt.md §24–25's requirements beyond cost/delay/leave-one-out remain open.

---

## M. Strategy Complementarity

Trend+carry comparison (synthetic carry placeholder):

| | Sharpe | Correlation with trend |
|---|---|---|
| Trend only | −0.140 | — |
| Carry only | −0.229 | 0.019 |
| Trend + Carry (equal risk) | −0.215 | — |

The measured correlation (0.019) confirms the synthetic carry source's independent-RNG design worked as intended — genuinely uncorrelated with trend, by construction. The activation gate (`strategies/carry_activation.py`) correctly **rejected** enabling carry: it failed on profitability (pure noise minus transaction costs is negative) and 2× cost survival, despite passing the low-correlation criterion. This is the gate behaving correctly — low correlation alone is not sufficient to justify adding a costly, valueless signal, and combining it with trend here made the blended result *worse* than trend alone, not better. **This result is specific to a fabricated placeholder and says nothing about real cross-asset carry.**

---

## N. Failure Analysis

Three categories of "failure," none of them a software defect:

1. **The baseline loses money on synthetic data** (§I) — verified not to be a sign/wiring bug via a dedicated direction-sanity test. Most likely cause: whipsaw at regime transitions given lookback horizons comparable to the synthetic regime length. This is a property of the *parameter choice interacting with this fabricated dataset*, not a claim about real markets, where regime persistence, magnitude, and noise characteristics all differ from what was fabricated here.
2. **The synthetic carry placeholder correctly fails its own activation gate** (§M) — working as intended, not a failure of the gate.
3. **Genuine implementation gaps** (not "failures" so much as incomplete scope): the regime-diagnostics module (§F) was never built; several of Prompt.md's required metrics (win rate, profit factor, expectancy, tail-loss/ES), stress dimensions (§L), the Monte Carlo analysis, the benchmark comparisons, and the visualization/dashboard layer are all absent. These are open work, not discovered problems with a built system — flagged here rather than left implicit.

No bugs were found and left unfixed. Two real bugs *were* found and fixed during development (a risk-equalization formula that inverted itself, and a local-file loader that mishandled a `DatetimeIndex`-based Parquet file) — both caught by the test suite before being reported here, which is the point of having one.

---

## O. Research Discrepancies

There is no discrepancy to report yet, in the proper sense — a discrepancy would require comparing this system's output against the research's claims on the *same, real* data, and that replication has not been performed. The negative synthetic-data result (§I) is not evidence against Research.md's trend hypothesis; the data it ran on was never claimed to resemble real markets. The one honest discrepancy worth naming: **Research.md's own headline claim is "no independent replication has been performed"** (its Executive Summary, verbatim, before the file was removed from this repo — retained in `Implementation_Spec.md` §2's audit) — that remains true today. This system is built to attempt that replication; it has not yet done so.

---

## P. Remaining Risks

- **No real data has touched this system.** Every number in §I–M is a pipeline-correctness check on fabricated data. This is the single largest remaining risk to any conclusion drawn from this project so far.
- **Vendor adapters are unverified against live accounts** (`Docs/Vendor_Integration.md`) — a documented API contract and a live account can disagree (renamed fields, undocumented rate limits, an unconfirmed daily-interval string for INDmoney specifically).
- **No point-in-time fundamentals source** — blocks the value/profitability equity sleeve indefinitely until one is found.
- **No real cost/tax data** — the cost model uses placeholder bps figures; India's STT and any real broker's actual commission schedule need live verification before any India-branch result could be trusted.
- **No regime-diagnostic module** — Research.md's explicit requirement to compute (not trade on) valuation/term-spread/correlation diagnostics is unmet; this also means the 2026 finding that trend weakens near valuation extremes (a key piece of the research's own risk disclosure) cannot currently be checked against this system's output at all.
- **Zero-correlation portfolio-vol assumption** (`portfolio/sizing.py`) will understate true portfolio vol whenever instruments are genuinely correlated — likely in real markets, especially within an asset class during stress.
- **The rates/bond-futures bucket is not reliably fillable** through the three Indian brokers now integrated (documented in `Vendor_Integration.md`) — any India-branch run needs to either source rates data elsewhere or explicitly report a 3-bucket, not 4-bucket, universe.

---

## Q. Next Experiments

Each with a stated hypothesis, per Prompt.md's requirement not to propose undirected feature additions:

1. **Build the regime-diagnostics module** (trailing vol percentile, trend dispersion, cross-asset correlation, term spread) as pure diagnostics wired to nothing. *Hypothesis: none yet — this is instrumentation, not a strategy change; its purpose is to let a future experiment test Research.md's valuation-boundary finding, not to assert it.*
2. **Run `scripts/vendor_smoke_test.py` against a real Zerodha/Angel One/INDmoney account** to confirm the adapters work against live data, fixing the one unconfirmed field in the INDmoney adapter if needed. *Hypothesis: the documented API contracts match live behavior closely enough that only minor field-name fixes, if any, are needed.*
3. **Replicate the core trend signal on real NSE/MCX/CDS daily data** via the now-built vendor adapters, restricted to the 3 buckets that are reliably fillable (equity index, commodities, FX), with the real, current NSE cost/STT schedule. *Hypothesis: given this is now the India-specific branch (not the global-futures universe Research.md preferred), performance and even the sign of the result may differ materially from any global-futures replication — report them as separate experiments, not interchangeable.*
4. **Add the missing backtest metrics** (win rate, avg win/loss, profit factor, expectancy, expected shortfall) and the benchmark comparison module (buy-and-hold, simple single-lookback trend, random-entry baseline) before drawing any conclusion from a real-data run — Prompt.md §17/§18 treat both as mandatory, not optional polish.
5. **Only after a real-data run exists**: revisit whether the negative synthetic-data Sharpe pattern (whipsaw-at-regime-transition) reproduces on real markets, where regime persistence and noise characteristics differ from the fabricated dataset — this cannot be answered from synthetic data alone, and should not be extrapolated from it.

---

## Final Status (Prompt.md §39)

**RESEARCH INTERPRETED:** YES
**IMPLEMENTATION COMPLETE:** PARTIAL — core trend pipeline, carry scaffold, robustness/attribution suite, paper-trading mode, and vendor layer are built and tested; regime-diagnostics module, value/profitability sleeve, ML challenger interface, benchmark comparisons, and visualization/dashboard are not.
**BACKTEST COMPLETE:** YES, on synthetic data only — not on real market data.
**OUT-OF-SAMPLE TEST COMPLETE:** PARTIAL — chronological holdout mechanism built and run on synthetic data; not yet meaningful without real data.
**WALK-FORWARD TEST COMPLETE:** PARTIAL — subperiod consistency reporting exists; true walk-forward retraining doesn't yet apply (no fitted component in the system).
**STRESS TEST COMPLETE:** PARTIAL — cost/delay/rebalance/leave-one-out done; missing-data, noisy-data, crisis-period, gap, liquidity, and Monte Carlo stress tests are not.
**DATA-LEAKAGE AUDIT COMPLETE:** YES — structural point-in-time enforcement plus dedicated regression and direction-sanity tests.
**PAPER-TRADING READY:** PARTIAL — mechanism built, tested, and reuses the exact backtest strategy code; not meaningful as an execution-quality measurement without a live data feed.
**LIVE TRADING ENABLED:** NO — hard-blocked at the configuration layer; no live execution path exists.

### What was built
A leakage-safe, config-driven, vendor-agnostic research system implementing Research.md's frozen trend baseline, a disabled carry satellite with its own activation gate, a robustness/attribution/DSR suite, a paper-trading mode, hard risk guardrails, and ready (if unverified-live) adapters for Zerodha, Angel One, and INDmoney plus a generic file-based fallback for any other vendor.

### What worked
The architecture holds together end-to-end (data → features → strategy → sizing → costs → backtest → metrics → attribution) on synthetic data, with no look-ahead bugs found across dedicated leakage and direction-sanity tests. The carry activation gate correctly rejected a valueless-but-uncorrelated placeholder signal rather than being fooled by low correlation alone.

### What failed
The frozen baseline is net-negative on the synthetic dataset used for pipeline testing — reported as-is per instruction, not tuned away, and explicitly not generalizable to real markets since the underlying data is fabricated.

### What remains uncertain
Everything about real-world performance: no real market data, no live-verified vendor connection, no point-in-time fundamentals, and no regime-diagnostic instrumentation exist yet. The research's own central limitation — no independent replication has been performed — remains true.

### What should be tested next
Real-data replication via the now-built vendor adapters (starting with a live smoke test), the regime-diagnostics module, the missing metrics/benchmarks, and only then a fresh look at whether the whipsaw pattern found on synthetic data has any real-market analogue — each as its own logged, falsifiable experiment, not as a retuning of the frozen baseline.

---

## Addendum: India NSE+MCX Blended System (separate research document)

A second, India-specific research document (`India NSE + MCX Quantitative Trading Research...`, user-supplied PDF, full extraction in `Docs/India_Implementation_Spec.md`) specified two primary hypotheses — `EQ_MOM_01` (NSE cross-sectional equity momentum) and `MCX_TREND_01` (MCX diversified time-series trend) — to be blended into one portfolio at 50:50 ex-ante risk, plus `MCX_CARRY_01` as a standalone-only complementary challenger. Built autonomously per explicit user instruction ("flag it and move on"); every open question encountered is flagged below and in `Docs/India_Implementation_Spec.md`, not left silently resolved.

**Implemented**: `CrossSectionalMomentumStrategy`, `MCXTrendSleeve`, `MCXCarryStrategy`, a new `BlendedPortfolioEngine` supporting per-sleeve rebalance frequencies (monthly/daily coexisting) and contract-roll resolution, a rolling-covariance portfolio-vol estimator, an itemized India transaction-cost model, synthetic NSE-equity and multi-expiry MCX-commodity data, and the exact discovery/validation/holdout date split the research specifies. 149 tests pass across the whole project (up from 90).

**A real bug was found and fixed during integration**: `CrossSectionalMomentumStrategy` initially scored every instrument in the shared NSE+MCX universe, not just NSE equities, because it had only ever been tested standalone. Caught by a manual smoke test before any formal test existed for it; a regression test now guards it (`tests/unit/test_cross_sectional_momentum.py::test_ignores_non_equity_instruments_in_a_shared_universe`).

**A result requiring a loud caveat**: on synthetic data, `MCX_CARRY_01` shows a strong standalone Sharpe (+0.92) and passes its own activation gate, while both trend sleeves are flat-to-negative. This is very likely a **synthetic-data construction artifact** — the carry signal reads today's curve slope with zero lag, while trend signals are backward-looking averages that lag a regime change, so carry "sees" the fabricated persistent regime faster than trend does by construction, not because real carry outperforms real trend. `IndiaSystemConfig` hard-blocks `mcx_carry_01` from ever getting a nonzero blended risk share regardless of this result — a synthetic pass changes nothing about the real gate, by design.

**Explicitly not implemented / flagged gaps**: real NSE/MCX data (synthetic only, same limitation as the global system), the EQ_MOM_01 rank-buffer hysteresis challenger, PBO (Probability of Backtest Overfitting) diagnostic, block-bootstrap/trade-order-permutation Monte Carlo, versioned exchange-calendar data beyond a single transcribed snapshot, most real instrument-master fields, the NSE quality challenger, options features, ML challengers, circuit-breaker/halt simulation, intraday execution, and an MCX commodities-transaction-tax (CTT) rate (not given anywhere in the source document — defaults to 0.0, which understates true MCX cost until a real figure is found).

### India System Status

**RESEARCH INTERPRETED:** YES
**IMPLEMENTATION COMPLETE:** PARTIAL — the two priority-one sleeves, the blend, and the standalone carry challenger are built and tested; hysteresis buffer, PBO, Monte Carlo, quality/ML/options challengers, and real exchange-calendar data are not.
**BACKTEST COMPLETE:** YES, synthetic data only.
**OUT-OF-SAMPLE TEST COMPLETE:** PARTIAL — the exact discovery/validation/holdout split from the research is implemented and run; not meaningful without real data.
**WALK-FORWARD TEST COMPLETE:** NOT DONE for this system yet (same caveat as the global system: no fitted parameters exist to walk forward on).
**STRESS TEST COMPLETE:** PARTIAL — 2×/3× cost stress via `IndiaCostConfig.scenario` exists; the research's full mandatory stress list (COVID-2020 subperiod, five worst weeks, roll-timing ±3 sessions, individual-commodity/sector removal, covariance shocks, missing-data scenarios) is not yet run for this system.
**DATA-LEAKAGE AUDIT COMPLETE:** YES — dedicated cross-sectional leakage regression test plus the same structural PIT enforcement as the rest of the codebase.
**PAPER-TRADING READY:** NO — the blended engine has no paper-trading wrapper yet (the existing `live/paper/PaperTrader` was built against the single/multi-strategy `BacktestEngine`, not the new per-sleeve `BlendedPortfolioEngine`).
**LIVE TRADING ENABLED:** NO.

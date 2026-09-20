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
| Regime diagnostics (computed, not traded on) | **Partial** | `features/regime.py` + `backtest/regime_report.py` compute trend dispersion, trailing vol percentile, and average pairwise correlation (all price-derived) as pure diagnostics, wired into nothing — CAPE/dividend-yield, term spread, liquidity proxies, and inflation/rate variables all need external data this system doesn't have and remain unimplemented |
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
| Monte Carlo / trade-order analysis | **Done** | `backtest/monte_carlo.py` — block-bootstrap and trade-order-permutation resampling, wired into `cli/run_robustness_suite.py` |
| Overfitting defense / experiment log | **Done** | `experiments/tracker.py` (append-only, every sweep run logged); `backtest/dsr.py` (Deflated Sharpe Ratio); `backtest/pbo.py` (Probability of Backtest Overfitting via CSCV) |
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

**Partial.** `features/regime.py` computes trend dispersion, trailing volatility percentile, and average pairwise correlation — everything on Research.md's list derivable from price data alone — and `backtest/regime_report.py` builds a historical `date → diagnostics` series plus regime-bucketed performance reporting (Prompt.md §10's explicit requirement). Strictly diagnostics: nothing in the codebase feeds these into any strategy's sizing. Valuation states (CAPE/dividend-yield), bond term spread, liquidity proxies, and inflation/rate regime variables all require real external macro/reference data this system does not have, and remain unimplemented — that piece of the original gap stands.

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

**These are the corrected numbers, from a run made after fixing the reproducibility bug described in §N item 4.** An earlier run of this exact command, in a different Python process, reported a *negative* baseline (Sharpe −0.140) and built an entire narrative around it (whipsaw losses at regime transitions). That negative result has turned out not to be reproducible from the stated configuration at all — it was itself a symptom of the bug: each process silently used a *different* "random" dataset while claiming the same `random_seed=42`. The corrected, now actually-reproducible run below supersedes that one; the earlier whipsaw narrative is retracted, not merely corrected, since it was explaining a result that doesn't recur under the configuration it claimed to be testing.

Baseline configuration (63/126/252 lookback, 60-day EWMA vol, 10% vol target, weekly rebalance, 0-session delay, base cost scenario), full 2000–2023 synthetic history, 16 instruments across 4 asset-class buckets:

| Metric | Value |
|---|---|
| Total return | +33.4% |
| CAGR | +1.21% |
| Annualized volatility | 5.73% |
| Sharpe | **+0.231** |
| Sortino | +0.374 |
| Max drawdown | −14.8% |
| Max drawdown duration | 1,605 days |
| Calmar | +0.081 |
| Avg turnover / rebalance | 0.39 |

**The frozen baseline is now modestly net-positive on this synthetic dataset.** The direction-sanity check (`tests/integration/test_strategy_sanity.py`) still holds regardless of this change — it confirms the strategy correctly goes long on a monotonic uptrend and short on a monotonic downtrend, ruling out a sign/wiring bug independent of which random dataset is in play. **Read this result the same cautious way as the previous (retracted) one, just with the sign flipped**: it is a property of this particular fabricated dataset and these particular parameters, not evidence that time-series trend "works" — a different (but now genuinely reproducible) `random_seed` would likely show a different sign again, since nothing about fabricated regime-switching noise should be expected to consistently favor either direction. The Deflated Sharpe Ratio and PBO results (§L) speak to whether even this positive number should be trusted as more than noise — they say **be skeptical**, not **it works**.

Leave-one-asset-class-out attribution: removing `equity_index` improves the result further (Sharpe 0.440), removing `commodities` is roughly neutral (0.249 vs. baseline 0.231), while removing `rates` or `fx` makes it noticeably *worse* (0.066, 0.104) — so on this dataset, rates and FX are the main positive contributors and equity-index is a mild drag. This kind of concentration is exactly what leave-one-out testing is supposed to surface (Prompt.md §21/§24), and it is a different pattern from what the earlier (buggy) run showed — another illustration of how much a single non-reproducible dataset can mislead attribution-level conclusions, not just headline ones.

Full sweep tables: `experiments/reports/robustness_suite_v1/*.csv`.

---

## J. Out-of-Sample Results

Chronological 80/20 split (final ~20% of the date range reserved, split date 2019-03-14), corrected run:

| | In-sample | Holdout |
|---|---|---|
| Sharpe | +0.246 | +0.185 |
| CAGR | +1.28% | +0.97% |
| Max drawdown | −14.8% | −13.2% |

Consistent in sign between segments, with a moderate drop in magnitude — the holdout is weaker than in-sample but not a collapse. **This is a mechanism check, not a real out-of-sample validation** — real OOS validation requires the real-data replication that hasn't happened yet, and per §I, even the sign of this synthetic result shouldn't be over-read.

---

## K. Walk-Forward Results

Yearly subperiod breakdown (`experiments/reports/robustness_suite_v1/subperiod_breakdown.csv`, corrected run) still shows high year-to-year dispersion, as expected for a trend follower on a regime-switching dataset: clearly positive years (2008: Sharpe 1.42, 2010: 1.23, 2018: 1.10) alongside clearly negative years (2001: −1.02, 2004: −1.03, 2016: −0.99, 2022: −1.12). The specific years differ from the earlier (retracted) run, as expected since the underlying "random" data was actually different each time — the general shape (some clean-regime years, some transition-heavy years, given roughly one positive year for every one-to-two negative ones) is the more durable observation here, not any individual year's number.

**Important scope limitation, stated plainly**: this is subperiod *consistency* reporting, not walk-forward *retraining*. The baseline has no fitted parameters (63/126/252, the vol window, and the risk targets are frozen research inputs), so there is nothing to re-estimate fold over fold. True walk-forward validation in the classic sense only becomes meaningful once a fitted component exists (e.g., an ML challenger) — this is documented directly in `backtest/attribution.py`'s module docstring so the distinction isn't lost later.

---

## L. Stress Test Results

Implemented and run (corrected numbers): transaction-cost stress (base/2×/3×: Sharpe +0.231 → +0.180 → +0.130, monotonically worse as expected — costs erode roughly 20-45% of the Sharpe as the multiplier rises, but never flip its sign in this run), execution-delay stress (0/1/2 sessions: +0.231/+0.318/+0.222 — the +1-session result being *better* than delay-0 is a reminder these are noisy synthetic draws, not a real execution-timing edge), rebalance-frequency comparison (weekly +0.231 vs. daily +0.141, weekly clearly better here despite daily's turnover being ~2.5× higher), and full leave-one-asset-class-out / leave-one-instrument-out sweeps (§I).

Monte Carlo analysis (`backtest/monte_carlo.py`, new) on the baseline's daily returns: block-bootstrap resampling (500 sims, preserving short-horizon serial dependence) gives a terminal-return band of roughly [−14%, +36%, +109%] at the 5th/50th/95th percentiles and a worst-rolling-year band of [−17%, −12%, −9%] — i.e. even resampling blocks of this same "positive" return series, a materially negative outcome is well within plausible range, not a tail curiosity. Trade-order permutation (reshuffling which days the recorded trades' return occurred on) gives a much tighter terminal-return band (~0.65% at all percentiles, since permutation preserves the total return of the exact set of realized daily returns and the position sizes/exposures the permuted order enters at happen to nearly cancel out in this synthetic run) — the two methods deliberately test different things and are not expected to agree.

**Still not implemented**: missing-data handling stress, noisy-data injection, distinct high-/low-volatility subperiod splits, crisis-period analysis (the synthetic data has no real crises to test against), rapid-reversal stress, large-gap stress, reduced-liquidity stress. The remainder of Prompt.md §24's stress list beyond cost/delay/leave-one-out/Monte Carlo remains open.

**Statistical credibility (DSR, PBO)**: the Deflated Sharpe Ratio for the baseline, correcting for the 41 configurations tried across every sweep above, is **0.99997** — i.e. after accounting for how many variants were searched, the observed +0.231 Sharpe is still well above the ~0.18 Sharpe that multiple-testing on noise alone would be expected to produce. That sounds reassuring in isolation, but the **Probability of Backtest Overfitting (PBO)**, computed via CSCV over the five lookback-neighborhood trials, is **0.337** — meaningfully below the 0.5 "coin flip" line (good), but not close to 0 either, so there is real, non-trivial selection-instability risk in which lookback looks best. Read together: this positive synthetic result is not simply noise dressed up as a discovery, but it is also not a confidently stable one — exactly the kind of mixed, honest signal a multiple-testing-aware report is supposed to surface rather than average away.

---

## M. Strategy Complementarity

Trend+carry comparison (synthetic carry placeholder, corrected run):

| | Sharpe | Correlation with trend |
|---|---|---|
| Trend only | +0.231 | — |
| Carry only | +0.024 | 0.014 |
| Trend + Carry (equal risk) | +0.206 | — |

The measured correlation (0.014) confirms the synthetic carry source's independent-RNG design worked as intended — genuinely uncorrelated with trend, by construction. The activation gate (`strategies/carry_activation.py`) correctly **rejected** enabling carry: it failed on profitability (pure noise minus transaction costs nets to roughly flat) and 2× cost survival, despite passing the low-correlation criterion. This is the gate behaving correctly — low correlation alone is not sufficient to justify adding a costly, valueless signal, and combining it with trend here made the blended result *worse* than trend alone (0.206 vs. 0.231), not better. **This result is specific to a fabricated placeholder and says nothing about real cross-asset carry.**

---

## N. Failure Analysis

Three categories of "failure," none of them a software defect:

1. **An earlier, non-reproducible run appeared to show the baseline losing money on synthetic data** — this was retracted (§I) once the reproducibility bug in item 4 below was found: that "failure" didn't reflect the configured dataset at all, it reflected a different, effectively-random dataset each process silently substituted for it. The corrected, actually-reproducible baseline is modestly positive (Sharpe +0.231, §I), with DSR/PBO results (§L) suggesting real-but-not-fully-stable synthetic-data skill. The lesson here is about process discipline, not about the strategy: a plausible-sounding causal story (whipsaw at regime transitions) was built around a number that turned out not to reproduce, which is exactly the failure mode Prompt.md §28's reproducibility requirement exists to prevent.
2. **The synthetic carry placeholder correctly fails its own activation gate** (§M) — working as intended, not a failure of the gate.
3. **Genuine implementation gaps** (not "failures" so much as incomplete scope): several of Prompt.md's required metrics (win rate, profit factor, expectancy, tail-loss/ES), most of §L's stress dimensions, the benchmark comparisons, and the visualization/dashboard layer are all still absent (the regime-diagnostics module and Monte Carlo analysis, previously listed here, are now built — see §F/§L). These are open work, not discovered problems with a built system — flagged here rather than left implicit.
4. **A real reproducibility bug**: every synthetic data generator seeded its per-symbol RNG from Python's built-in `hash()`, which is randomized per process — "the same config" silently produced different fabricated data across separate runs, directly violating Prompt.md §28. Found by comparing two runs of the robustness suite that were supposed to be identical and weren't; fixed with a stable hash and a dedicated cross-process regression test (see §I's note for how this affects the specific numbers reported there).

No bugs were found and left unfixed. Two real bugs *were* found and fixed during development (a risk-equalization formula that inverted itself, and a local-file loader that mishandled a `DatetimeIndex`-based Parquet file) — both caught by the test suite before being reported here, which is the point of having one.

---

## O. Research Discrepancies

There is no discrepancy to report yet, in the proper sense — a discrepancy would require comparing this system's output against the research's claims on the *same, real* data, and that replication has not been performed. Neither sign of the synthetic-data result (§I) is evidence for or against Research.md's trend hypothesis; the data it ran on was never claimed to resemble real markets. The one honest discrepancy worth naming: **Research.md's own headline claim is "no independent replication has been performed"** (its Executive Summary, verbatim, before the file was removed from this repo — retained in `Implementation_Spec.md` §2's audit) — that remains true today. This system is built to attempt that replication; it has not yet done so.

---

## P. Remaining Risks

- **No real data has touched this system.** Every number in §I–M is a pipeline-correctness check on fabricated data. This is the single largest remaining risk to any conclusion drawn from this project so far.
- **Vendor adapters are unverified against live accounts** (`Docs/Vendor_Integration.md`) — a documented API contract and a live account can disagree (renamed fields, undocumented rate limits, an unconfirmed daily-interval string for INDmoney specifically).
- **No point-in-time fundamentals source** — blocks the value/profitability equity sleeve indefinitely until one is found.
- **No real cost/tax data** — the cost model uses placeholder bps figures; India's STT and any real broker's actual commission schedule need live verification before any India-branch result could be trusted.
- **No valuation/term-spread/liquidity/inflation regime data** — the price-derived diagnostics (trend dispersion, vol percentile, correlation) are now built (`features/regime.py`), but the 2026 finding that trend weakens near valuation extremes (a key piece of the research's own risk disclosure) needs valuation data this system still doesn't have, so it cannot yet be checked against this system's output.
- **Zero-correlation portfolio-vol assumption** (`portfolio/sizing.py`) will understate true portfolio vol whenever instruments are genuinely correlated — likely in real markets, especially within an asset class during stress.
- **The rates/bond-futures bucket is not reliably fillable** through the three Indian brokers now integrated (documented in `Vendor_Integration.md`) — any India-branch run needs to either source rates data elsewhere or explicitly report a 3-bucket, not 4-bucket, universe.

---

## Q. Next Experiments

Each with a stated hypothesis, per Prompt.md's requirement not to propose undirected feature additions:

1. **Use the now-built regime diagnostics** (`backtest/regime_report.py`) to check whether the frozen baseline's performance actually differs across detected regime buckets on real data, once real data exists — the price-derived diagnostics are built and tested, but a valuation-based version of Research.md's boundary finding still needs external valuation data this system doesn't have. *Hypothesis: none yet — this is instrumentation, not a strategy change; its purpose is to let a future experiment test Research.md's valuation-boundary finding, not to assert it.*
2. **Run `scripts/vendor_smoke_test.py` against a real Zerodha/Angel One/INDmoney account** to confirm the adapters work against live data, fixing the one unconfirmed field in the INDmoney adapter if needed. *Hypothesis: the documented API contracts match live behavior closely enough that only minor field-name fixes, if any, are needed.*
3. **Replicate the core trend signal on real NSE/MCX/CDS daily data** via the now-built vendor adapters, restricted to the 3 buckets that are reliably fillable (equity index, commodities, FX), with the real, current NSE cost/STT schedule. *Hypothesis: given this is now the India-specific branch (not the global-futures universe Research.md preferred), performance and even the sign of the result may differ materially from any global-futures replication — report them as separate experiments, not interchangeable.*
4. **Add the missing backtest metrics** (win rate, avg win/loss, profit factor, expectancy, expected shortfall) and the benchmark comparison module (buy-and-hold, simple single-lookback trend, random-entry baseline) before drawing any conclusion from a real-data run — Prompt.md §17/§18 treat both as mandatory, not optional polish.
5. **Only after a real-data run exists**: check whether the sign and magnitude of any synthetic-data result generalizes at all to real markets, where regime persistence and noise characteristics differ from the fabricated dataset. Given §I/§N's experience — a specific synthetic "finding" flipped sign entirely once a reproducibility bug was fixed — this cannot be answered from synthetic data alone, and no synthetic-data sign or magnitude should be extrapolated from it, in either direction.

---

## Final Status (Prompt.md §39)

**RESEARCH INTERPRETED:** YES
**IMPLEMENTATION COMPLETE:** PARTIAL — core trend pipeline, carry scaffold, robustness/attribution suite, price-derived regime diagnostics, PBO, Monte Carlo, paper-trading mode, and vendor layer are built and tested; value/profitability sleeve, ML challenger interface, benchmark comparisons, valuation/macro regime data, and visualization/dashboard are not.
**BACKTEST COMPLETE:** YES, on synthetic data only — not on real market data.
**OUT-OF-SAMPLE TEST COMPLETE:** PARTIAL — chronological holdout mechanism built and run on synthetic data; not yet meaningful without real data.
**WALK-FORWARD TEST COMPLETE:** PARTIAL — subperiod consistency reporting exists; true walk-forward retraining doesn't yet apply (no fitted component in the system).
**STRESS TEST COMPLETE:** PARTIAL — cost/delay/rebalance/leave-one-out and Monte Carlo (block-bootstrap + trade-order permutation) done; missing-data, noisy-data, crisis-period, gap, and liquidity stress tests are not.
**DATA-LEAKAGE AUDIT COMPLETE:** YES — structural point-in-time enforcement plus dedicated regression and direction-sanity tests.
**PAPER-TRADING READY:** PARTIAL — mechanism built, tested, and reuses the exact backtest strategy code; not meaningful as an execution-quality measurement without a live data feed.
**LIVE TRADING ENABLED:** NO — hard-blocked at the configuration layer; no live execution path exists.

### What was built
A leakage-safe, config-driven, vendor-agnostic research system implementing Research.md's frozen trend baseline, a disabled carry satellite with its own activation gate, a robustness/attribution/DSR suite, a paper-trading mode, hard risk guardrails, and ready (if unverified-live) adapters for Zerodha, Angel One, and INDmoney plus a generic file-based fallback for any other vendor.

### What worked
The architecture holds together end-to-end (data → features → strategy → sizing → costs → backtest → metrics → attribution) on synthetic data, with no look-ahead bugs found across dedicated leakage and direction-sanity tests. The carry activation gate correctly rejected a valueless-but-uncorrelated placeholder signal rather than being fooled by low correlation alone.

### What failed
A real reproducibility bug (§N item 4): every synthetic data generator seeded its RNG from Python's randomized-per-process built-in `hash()`, so "the same config" silently produced different fabricated data on different runs — which had already produced a specific, plausible-sounding, but ultimately non-reproducible "finding" (the baseline losing money) that this report initially wrote up before the bug was caught and fixed. The corrected baseline is modestly positive; that number is likewise not to be over-read (§I) — the point of flagging this is the process failure, not either sign of the synthetic result.

### What remains uncertain
Everything about real-world performance: no real market data, no live-verified vendor connection, and no point-in-time fundamentals exist yet (price-derived regime diagnostics now do, but the valuation/macro data needed to test the research's own boundary finding still doesn't). The research's own central limitation — no independent replication has been performed — remains true.

### What should be tested next
Real-data replication via the now-built vendor adapters (starting with a live smoke test), the missing metrics/benchmarks, and only then a fresh look — using the now-built regime diagnostics — at what actually drives real-market performance, since the synthetic result's sign has already been shown (§I/§N) not to be a stable thing to extrapolate from — each as its own logged, falsifiable experiment, not as a retuning of the frozen baseline.

---

## Addendum: India NSE+MCX Blended System (separate research document)

A second, India-specific research document (`India NSE + MCX Quantitative Trading Research...`, user-supplied PDF, full extraction in `Docs/India_Implementation_Spec.md`) specified two primary hypotheses — `EQ_MOM_01` (NSE cross-sectional equity momentum) and `MCX_TREND_01` (MCX diversified time-series trend) — to be blended into one portfolio at 50:50 ex-ante risk, plus `MCX_CARRY_01` as a standalone-only complementary challenger. Built autonomously per explicit user instruction ("flag it and move on"); every open question encountered is flagged below and in `Docs/India_Implementation_Spec.md`, not left silently resolved.

**Implemented**: `CrossSectionalMomentumStrategy`, `MCXTrendSleeve`, `MCXCarryStrategy`, a new `BlendedPortfolioEngine` supporting per-sleeve rebalance frequencies (monthly/daily coexisting) and contract-roll resolution, a rolling-covariance portfolio-vol estimator, an itemized India transaction-cost model, synthetic NSE-equity and multi-expiry MCX-commodity data, and the exact discovery/validation/holdout date split the research specifies. 149 tests pass across the whole project (up from 90).

**A real bug was found and fixed during integration**: `CrossSectionalMomentumStrategy` initially scored every instrument in the shared NSE+MCX universe, not just NSE equities, because it had only ever been tested standalone. Caught by a manual smoke test before any formal test existed for it; a regression test now guards it (`tests/unit/test_cross_sectional_momentum.py::test_ignores_non_equity_instruments_in_a_shared_universe`).

**A result requiring a loud caveat**: on synthetic data, `MCX_CARRY_01` shows a strong standalone Sharpe (+1.14) and passes its own activation gate, while both trend sleeves are flat-to-negative. This is very likely a **synthetic-data construction artifact** — the carry signal reads today's curve slope with zero lag, while trend signals are backward-looking averages that lag a regime change, so carry "sees" the fabricated persistent regime faster than trend does by construction, not because real carry outperforms real trend. `IndiaSystemConfig` hard-blocks `mcx_carry_01` from ever getting a nonzero blended risk share regardless of this result — a synthetic pass changes nothing about the real gate, by design.

**A second, more serious bug was found and fixed after this addendum's numbers were first drafted**: every synthetic data generator derived per-symbol RNG seeds from Python's built-in `hash()`, which is randomized per process — so "the same config" silently produced different fabricated data across separate runs, violating Prompt.md §28's reproducibility requirement. Fixed with a stable SHA256-based hash and verified with a cross-process regression test (`tests/integration/test_cross_process_reproducibility.py`); the specific numbers throughout this addendum and `Docs/India_Implementation_Spec.md` reflect the corrected, now-reproducible run. The qualitative pattern (blended negative, MCX trend negative, carry strongly positive) held before and after the fix — only exact figures changed.

**Explicitly not implemented / flagged gaps**: real NSE/MCX data (synthetic only, same limitation as the global system), the EQ_MOM_01 rank-buffer hysteresis challenger, versioned exchange-calendar data beyond a single transcribed snapshot, most real instrument-master fields, the NSE quality challenger, options features, ML challengers, circuit-breaker/halt simulation, intraday execution, and an MCX commodities-transaction-tax (CTT) rate (not given anywhere in the source document — defaults to 0.0, which understates true MCX cost until a real figure is found). PBO and Monte Carlo (`backtest/pbo.py`, `backtest/monte_carlo.py`) now exist generically, built for the global-futures suite — they have not yet been applied to this India system's own trials.

### India System Status

**RESEARCH INTERPRETED:** YES
**IMPLEMENTATION COMPLETE:** PARTIAL — the two priority-one sleeves, the blend, and the standalone carry challenger are built and tested; hysteresis buffer, quality/ML/options challengers, and real exchange-calendar data are not. PBO/Monte Carlo exist generically but haven't been applied to this system's own trials yet.
**BACKTEST COMPLETE:** YES, synthetic data only.
**OUT-OF-SAMPLE TEST COMPLETE:** PARTIAL — the exact discovery/validation/holdout split from the research is implemented and run; not meaningful without real data.
**WALK-FORWARD TEST COMPLETE:** NOT DONE for this system yet (same caveat as the global system: no fitted parameters exist to walk forward on).
**STRESS TEST COMPLETE:** PARTIAL — 2×/3× cost stress via `IndiaCostConfig.scenario` exists; the research's full mandatory stress list (COVID-2020 subperiod, five worst weeks, roll-timing ±3 sessions, individual-commodity/sector removal, covariance shocks, missing-data scenarios) is not yet run for this system.
**DATA-LEAKAGE AUDIT COMPLETE:** YES — dedicated cross-sectional leakage regression test plus the same structural PIT enforcement as the rest of the codebase.
**PAPER-TRADING READY:** YES for both systems — `live/paper/PaperTrader` wraps the single-strategy `BacktestEngine`, and `live/paper/BlendedPaperTrader` (new) wraps the per-sleeve `BlendedPortfolioEngine`. Both call the same shared helpers as their engines (`backtest/blended_engine.py`'s module-level `select_decision_dates`, `resolve_contracts`, `median_traded_value` are now shared functions rather than duplicated methods) so backtest and paper cannot silently diverge, and `tests/integration/test_blended_paper_trader.py` includes a strict byte-level parity test that verifies the trader's final NAV and positions match the engine's for the same trading calendar. Same honest limitation as before: with no live market data feed, "paper trading" is a historical replay through the stepping loop, and the expected-vs-simulated-execution slippage is always 0 (both sides use the same historical close), which will only become a real measurement once a live/delayed quote feed is connected.
**LIVE TRADING ENABLED:** NO.

## Post-Milestone Audit (this pass)

An extensive security-and-correctness audit was run over every module. Findings and fixes below; all 202 tests pass (up from 172), including new dedicated regression tests for each item.

**Real bugs found and fixed:**

1. **Path traversal via symbol name.** `LocalFileDataSource.get_prices`, `brokers/base.py:read_or_none`, and `brokers/base.py:write_cache` all concatenated a `symbol` string into a filesystem path with no validation. A universe listing containing e.g. `"../../etc/passwd"` could have read/written outside the intended directory. Fixed with `trading_system/util.py:validate_symbol_name` (allowlist-based) called from every path-building site. Regression test: `tests/unit/test_symbol_validation.py`, `tests/unit/test_path_traversal_defense.py`.

2. **INDmoney adapter used a naive datetime for epoch-ms conversion**, which `.timestamp()` interprets as local time on the host machine. A US-Eastern user and an IST user would send different epoch-ms values for "the same date" and get different data back, violating reproducibility across environments. Fixed by attaching `Asia/Kolkata` tzinfo explicitly (matches the vendor's documented "All timestamps are in IST" convention). Regression test: `tests/unit/test_indmoney_timezone.py`.

3. **`apply_participation_cap` didn't cap sell/exit trades.** Iterating only `target_weights.items()` meant a symbol present in `current_weights` but absent from `target_weights` (a full exit) bypassed the cap and disappeared from the returned dict — the caller sold the whole position in one bar regardless of liquidity. Fixed by iterating the union. Regression test: `tests/unit/test_participation_cap_exits.py`.

4. **Non-atomic cache write.** `brokers/base.py:write_cache` wrote directly to the final path; an interrupted process could leave a truncated/corrupted parquet that the next read would explode on. Fixed with staging-file + `Path.replace()` (POSIX-atomic rename within one filesystem).

5. **Silent asset-class fallback in the blended engine and paper trader.** `self._asset_class_by_symbol.get(sym, "nse_equity")` had let an earlier scope bug (a strategy returning weights for the wrong asset class) go undetected because unknown symbols were silently reclassified as NSE equity, then charged equity STT/stamp duty. Both engine and paper trader now raise `KeyError` on unknown symbols rather than fabricate an asset class.

6. **`MCXTrendSleeve` empty-underlying collision.** Symbols with empty `underlying` labels would collide under the `""` key, producing a single mixed signal not traceable to any commodity. Now filters `if not meta.underlying: continue`, matching `MCXCarryStrategy`'s existing filter.

7. **`RiskGuardrails.check_drawdown` was defined but never called.** The drawdown-from-peak limit was documented in the guardrails module but no caller invoked it, so it was silently unenforced. Both `PaperTrader` and `BlendedPaperTrader` now track `_peak_nav` and call `check_drawdown` after every step's PnL update. Regression test: `tests/integration/test_drawdown_enforcement.py`.

8. **Cache read bypassed `normalize_ohlcv`.** A stale or wrong-shape cached file would be loaded without column-shape validation, breaking downstream code far from the actual defect. Cached reads now run through `normalize_ohlcv` too.

9. **INDmoney error message dumped the entire vendor payload** including request metadata — a leak risk since this adapter sends the Authorization token on every request. Errors now log only `status` and `message` fields explicitly.

10. **Silent config-validation gaps.** `CostConfig`, `IndiaCostConfig`, and `SystemConfig` accepted invalid `scenario`/`mode` typos silently at construction, only surfacing as a `KeyError` deep in a backtest. All three now validate in `__post_init__`. Regression test: `tests/unit/test_config_validation.py`.

11. **`PointInTimeStore.history_as_of` returned a possibly-view DataFrame.** The leakage-safety guarantee relied on pandas' `SettingWithCopyWarning` protecting internal state; that protection is being deprecated in pandas 3.0's copy-on-write model. Now returns an explicit `.copy()` so the guarantee holds identically across pandas versions.

**Also swept for and confirmed absent:** `eval`/`exec`/`pickle.load`/`__import__`/`compile`; `subprocess`/`os.system`/`shell=True`; hardcoded credentials or API keys; bare `except:`/`except Exception:` catchers; unseeded random generators (all use `np.random.default_rng(explicit_seed)`); TODOs/FIXMEs/XXX/HACK markers. The credential policy is intact: no adapter accepts or stores API keys, passwords, or TOTP secrets — each takes an already-authenticated client object built by the caller in their own script.

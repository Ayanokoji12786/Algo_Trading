# Implementation Specification & Research Audit

Status: **pre-coding deliverable**, produced per `Prompt.md` §§1–7 ("Do not begin coding immediately").
Source documents: `Docs/Prompt.md` (engineering instructions), `Docs/Research.md` (quantitative research handoff).

This document does three things only: (1) extracts the research into a structured spec, (2) audits every
quantitative/methodological claim, (3) proposes the software architecture and phased plan. **No strategy,
backtest, or data code is written yet.** Coding begins only after the open questions in §6 are resolved.

---

## 1. Extracted Specification

### 1.1 Recommended strategy (the thing to build first)

| Item | Specification | Source |
|---|---|---|
| Strategy family | Time-series momentum / trend-following | Research §"Bottom-line research decision" |
| Market | Diversified liquid futures: equity index, rates/bonds, FX, commodities (4 buckets) | Research "Market and instruments" |
| Frequency | Signals computed **daily**; execution/rebalance **weekly** (baseline). Daily vs weekly rebalance is itself an experiment to run, not just an assumption. | Research "Entry and exit logic" |
| Core signal | `s_{i,t} = [sign(R_63) + sign(R_126) + sign(R_252)] / 3`, using returns available no later than t‑1 | Research "Core trend signal" |
| Signal values | {-1, -1/3, +1/3, +1} (no explicit zero/neutral state in baseline) | Research §"Core trend signal" |
| Position sizing | `q_{i,t} ∝ s_{i,t} / max(σ̂_{i,t}, σ_min)`, σ̂ from a slow trailing estimator (research suggests 60-day EWMA as a testable default, not a fixed requirement) | Research "Position sizing" |
| Risk hierarchy | (1) inverse-vol scale within asset class → (2) equalize risk across asset classes → (3) scale whole portfolio to a fixed vol target → (4) cap instrument/asset-class/margin exposure | Research "Position sizing" |
| Portfolio vol target | 10% annualized — explicitly labeled "a reproducible paper-research default... not an evidence-derived optimum" | Research "Position sizing" |
| Execution timing | No earlier than the next tradable session after the information is observable; must also test +1 and +2 session delays | Research "Cost and execution model", "Entry logic" |
| Stops | **None in baseline.** Exit is signal decay/reversal + portfolio risk controls only. Stop-loss variants may be tested as a separate hypothesis, kept only if they improve OOS after extra turnover cost. | Research "Entry and exit logic" |
| Cost model | commissions + exchange/clearing fees + ½ spread + slippage + market impact + roll costs + financing + taxes | Research "Cost and execution model" |
| Cost scenarios | Base, 2×, 3× cost/slippage stress required | Research "Cost and execution model" |
| Carry module | Build separately, ship **disabled** (`carry_enabled = false`). Activation requires: positive net value after costs, parameter/sign stability, acceptable tails, incremental value vs. trend, materially lower return/drawdown correlation with trend across subperiods, survives 2× costs. | Research "Carry satellite" |
| Regime detection | Compute diagnostics only (vol percentile, trend dispersion, cross-asset correlation, valuation states, term spread, liquidity, inflation/rate regime) — **do not gate trading on them** in baseline. Baseline regime response = volatility-based risk scaling, not a fitted on/off classifier. | Research "Regime detection" |
| ML | **None in baseline signal or regime layer.** Later `challenger_models/` interface permitted (regularized linear → GBM → shallow NN, in that order of preference), trained with nested chronological walk-forward, targeting risk-adjusted forward return / probability of profitability — not next-bar classification accuracy. Promote only if it beats the frozen simple baseline on net OOS economics. | Research "Machine learning specification" |
| Equity challenger (phase 2, optional) | Value + profitability/quality sleeve, monthly rebalance, only if survivorship-safe point-in-time fundamentals are obtainable | Research "Value/profitability satellite" |
| Excluded entirely from phase 1 | RSI/MACD/BB/ADX indicator stacks as independent alpha, cross-sectional equity momentum as core (challenger/benchmark only), pairs/stat-arb mean reversion, HFT/microstructure, options/vol harvesting, NLP/news/sentiment, deep learning, reinforcement learning | Research strategy-universe table |

### 1.2 Data requirements

- Per-contract: raw daily OHLC/settlement, volume, open interest, contract ID, expiry, first/last trade date, multiplier, tick size, currency.
- **Actual front/deferred contracts**, not just a vendor continuous series — continuous series allowed for *signal generation only*, PnL/execution must use tradable contracts.
- Explicit roll dates and realized roll trades, per a **pre-declared** roll rule (not chosen after seeing backtest results).
- Exchange calendars/session metadata, FX conversion rates to base currency.
- Commissions, exchange/clearing fees, bid-ask/slippage estimates (historical or conservative), margin schedules, jurisdiction tax data.
- Universe selection must come from a pre-declared liquidity/history rule applied to exchange metadata — **not** selected after seeing which contracts backtest well.
- India branch (if pursued): current NSE STT (0.05% securities-futures sell side, 0.15% options sell side, effective 2026-04-01) and Client Direct API algo-registration constraints, fetched dynamically, never hardcoded as timeless constants.

### 1.3 Validation requirements

- Chronological ordering preserved throughout; no random train/test splits.
- Point-in-time discipline: every external/fundamental/macro value stamped and applied at its actual publication vintage.
- Untouched final holdout, touched only once methodology is frozen.
- Walk-forward validation (expanding or rolling), parameters frozen before the final test.
- Full experiment log — every tested variation, including failures — to support multiple-testing correction (Deflated Sharpe Ratio or equivalent).
- Robustness sweeps required: neighboring trend horizons, alternative vol estimators, daily vs weekly rebalance, execution delay (+1, +2 sessions), cost stress (1×/2×/3×), alternative roll rules, leave-one-market-out, leave-one-asset-class-out, subperiod/decade/regime breakdowns.
- Metrics (minimum): gross & net CAGR, ann. vol, Sharpe, Sortino, max drawdown + duration, Calmar, expected shortfall/tail losses, turnover, exposure, break-even cost per trade, win rate, avg win/loss, profit factor, expectancy, rolling Sharpe/vol/drawdown, monthly/yearly return tables, per-asset/asset-class/decade/regime attribution.
- Explicit falsification conditions (§8 of Research.md) — if any is found true, the recommendation must be downgraded/rejected and reported as such, not tuned away.

### 1.4 Deployment gating (from Prompt.md, non-negotiable)

`RESEARCH MODE` → `BACKTEST MODE` → `PAPER MODE` → (live trading, explicitly separated, disabled by default, never auto-enabled). Paper trading must reuse the exact backtest strategy logic — no parallel simplified implementation.

---

## 2. Research-to-Implementation Audit

Legend: **VERIFIED** / **REQUIRES REPLICATION** / **AMBIGUOUS** / **UNSUPPORTED** / **CONFLICTING**

| # | Claim / spec item | Category | Notes |
|---|---|---|---|
| 1 | Time-series momentum shows cross-asset persistence over ~1–12mo (Moskowitz/Ooi/Pedersen), and positive trend returns across decades since 1880 (Hurst/Ooi/Pedersen) | **REQUIRES REPLICATION** | This is the load-bearing claim for the whole system. Research explicitly states *"No independent multi-decade, point-in-time replication has been performed."* Must be reconstructed from our own contract-level data before it can inform any decision. Treat as a prior, not a result. |
| 2 | TSM becomes unreliable near historical equity/bond valuation extremes (Suominen & Hjalmarsson, 2026) | **REQUIRES REPLICATION** | Single recent study, not yet independently reproduced. Correctly treated by Research as a *diagnostic*, not a trading gate — we follow that. |
| 3 | 63/126/252-trading-day ensemble as "the" signal | **AMBIGUOUS + a design choice presented as if settled** | The academic literature supports the *general* 1–12mo persistence window; the specific tri-signal average and exact day-counts (63/126/252) are the research author's operationalization, not a value taken directly from a cited paper. Must be treated as the frozen baseline to test, and its neighborhood swept (Prompt.md §21) — not assumed correct because it's written with precision. |
| 4 | 60-day EWMA volatility estimator | **AMBIGUOUS (explicitly flagged as such by Research itself)** | Research says "a 60-trading-day EWMA or similarly slow estimator is an appropriate baseline **to test**" — this is presented as a testable default, not a fixed spec. We will freeze one choice for the baseline and log it as an assumption (see §5), then test alternates as robustness. |
| 5 | 10% annualized portfolio vol target | **UNSUPPORTED as an optimum, explicitly labeled a convention** | Research says this outright: "a comparison convention, not a scientifically established optimum." No audit finding needed — already self-flagged. We adopt it as configurable, not hardcoded. |
| 6 | Weekly rebalance as baseline (vs. daily signal calc) | **AMBIGUOUS** | Research presents this as the baseline but simultaneously requires daily-vs-weekly to be run "as a robustness/cost experiment." This is mildly self-conflicting: is weekly the baseline or an empirical question? We resolve it as: weekly is the frozen baseline for headline results; daily is a required robustness comparison run in parallel, not a replacement. |
| 7 | Carry has multi-asset peer-reviewed evidence (Koijen/Moskowitz/Pedersen/Vrugt) but common bad periods in recession/liquidity stress | **VERIFIED (as literature) / REQUIRES REPLICATION (as applied to our carry module)** | Literature citation itself is treated as solid; whether *our* carry implementation is actually diversifying is explicitly gated behind empirical tests we must run. Correctly kept disabled by Research's own design — we preserve that. |
| 8 | Value–momentum negative correlation (Asness/Moskowitz/Pedersen) | **VERIFIED (as literature), phase-2 only** | Strong published evidence, but implementation blocked on point-in-time fundamentals availability, which Research itself says was not supplied. This entire sleeve is **not buildable now** without a PIT fundamentals data source — see open question in §6. |
| 9 | ML (Gu/Kelly/Xiu) improves prediction in large equity cross-sections, but overfitting/microcap risk (Jo & Kim 2026) | **VERIFIED (as literature) / correctly excluded from baseline** | No conflict: Research's own conclusion ("no ML in first layer") follows from citing both the positive and cautionary papers. We implement the `challenger_models/` interface but do not activate it in phase 1. |
| 10 | NSE STT 0.05%/0.15% effective 2026-04-01 | **VERIFIED claim, but must be re-checked live, not hardcoded** | Research explicitly warns these are dated and will change; today's date in this session is 2026-09-20, i.e. *after* the stated effective date, so the new rates are presumably already in force — but this must be confirmed against NSE's current published schedule at implementation time, not assumed from the research document's snapshot. |
| 11 | "Standard contracts... provide the longest clean history" for backtesting, smaller contracts mapped later for paper/live | **AMBIGUOUS** | No concrete contract list, exchange, or vendor is specified anywhere in Research.md. This is a placeholder methodology, not an executable spec — see open question in §6 (data source). |
| 12 | Global futures vs. NSE-only deployment | **CONFLICTING with practical constraints** | Research recommends global liquid futures as the primary research universe but explicitly says an India deployment is a *separate experiment* requiring independent validation, and does not resolve which the user actually wants or can access (broker, capital, legal access to global futures unspecified). This is a first-order open question, not something to silently pick. |
| 13 | "No clean strategy-pure live result was established... evidence is mainly historical simulation/reconstruction" (self-assessment, all three candidate strategies) | **UNSUPPORTED, self-flagged by Research** | Research is explicit that none of the three candidates (trend, carry, value/profitability) have a live track record backing them in this document. This tempers confidence project-wide; we should not let backtest results — even after all robustness testing — be reported as more than "survived our adversarial replication," per Prompt.md §37/§40. |
| 14 | Multiple-testing correction via Deflated Sharpe Ratio "or an equivalent procedure" | **AMBIGUOUS** | No specific procedure is mandated; "or equivalent" leaves the exact statistical test to the implementer. We will pick DSR (Bailey & López de Prado) as the concrete default and document that choice as an implementation decision, not a silent one. |

### 2.1 Internal conflicts in Research.md worth naming explicitly

- **Regime logic tension**: Research simultaneously (a) presents strong recent evidence that TSM fails near valuation extremes, and (b) argues against turning this into a trading rule until independently replicated. This isn't a contradiction so much as intentional caution, but it means the regime module's practical value in phase 1 is *diagnostic-only* — it will not visibly affect any backtest number until/unless promoted later. We flag this so it isn't mistaken for an oversight when the regime module "doesn't do anything" to returns initially.
- **Weekly vs. daily rebalance**, discussed above (audit item 6).
- **"Do not rank by backtested return" vs. an implicit ranking already given**: Research explicitly says the candidate set is "not ranked by backtested return" (none exist yet) but then still assigns trend > carry > value/profitability by confidence and build order. This is a ranking by *literature strength and implementability*, not backtest performance — consistent with Prompt.md's mandate, not actually conflicting, but worth stating precisely so we don't inherit unstated backtest-based bias.

---

## 3. Things That Cannot Be Implemented Exactly As Specified (blockers)

1. **No data vendor/source named.** Research requires contract-level OHLC+OI+roll history for four global futures buckets, survivorship-safe. Nothing in either doc names a vendor, API, or file source. This blocks Module 1 (data ingestion) entirely until resolved.
2. **No broker/cost data named.** Real commission schedules, margin schedules, and historical bid-ask/slippage are required inputs to the cost model; Research explicitly allows "conservative estimates" as a fallback, which we can implement, but it must be labeled as an estimate, not measured cost.
3. **No point-in-time fundamentals source** for the value/profitability equity sleeve — Research itself says this wasn't supplied. That sleeve is **out of scope** until such a source exists; we will not fake it with non-PIT (e.g., latest-available) fundamentals, since that would be exactly the look-ahead leakage Prompt.md §7 prohibits.
4. **No capital, broker, jurisdiction, or leverage constraints from the user.** Research adopted "least aggressive" defaults (research/paper only, daily, high-liquidity, no leverage assumption) — we inherit these defaults but they are assumptions, not requirements (see §5).
5. **No live/current NSE tax and algo-registration figures fetched** — Research's numbers are a dated citation, not a live lookup; if the India branch is pursued, this must be re-verified at build time, not copied from Research.md.

These block full end-to-end implementation but do **not** block building the architecture, config system, indicator/return-calculation modules, cost/backtest engine logic, and validation harness against synthetic or placeholder data first — which is the correct build order regardless.

---

## 4. Do-Not-Silently-Modify Register

No modifications to the research have been made yet. This section will be populated (per Prompt.md §3's required 6-field format: original spec / problem / proposed modification / reason / expected effect / needs separate validation?) the moment any parameter is changed during implementation — e.g., if 63/126/252 must shift because of data-history limits, or if the 10% vol target needs adjustment for a particular data vendor's contract granularity. Currently empty because no code exists yet.

---

## 5. Assumptions Register (explicit, not silent)

| Assumption | Why needed | Must be validated separately? |
|---|---|---|
| Volatility estimator = 60-day EWMA of daily returns, annualized | Research names this only as "an appropriate baseline to test"; a concrete formula is needed to write code | Yes — sweep alternate windows/estimators per Prompt.md §21 |
| Weekly rebalance = every Friday's close (or last session of week) using signals computed through the prior close | Research says "weekly" without specifying which day or lag convention | Yes — sensitivity to rebalance-day choice should be checked |
| Deflated Sharpe Ratio (Bailey & López de Prado) is the multiple-testing statistic used | Research says "DSR or equivalent" without picking one | No — this is an analysis-method choice, not a strategy parameter |
| Roll rule = roll on a fixed days-before-expiry threshold using volume/OI crossover as tiebreak (exact rule TBD at Module 1 design time) | Research requires "pre-declared" rule but does not supply one | Yes — must be declared *before* any backtest is run, and never changed after seeing results |
| Cost model starts with conservative fixed estimates per asset class in absence of a real broker feed | Research allows conservative estimates as fallback | Yes — flagged as "Base (estimated)" cost scenario, never presented as measured |
| Universe selection rule = top-N by trailing liquidity (volume × price) within each of the 4 buckets, history ≥ some minimum years, decided before any performance is seen | Fills the "pre-declared liquidity/history rule" requirement Research demands but doesn't specify | Yes |

---

## 6. Open Questions Requiring a User Decision

These are genuine blockers, not stylistic choices — implementation cannot proceed correctly without them:

1. **Data source**: Do you have access to a specific data vendor/API for futures contract-level history (e.g., Databento, Norgate, CSI, Interactive Brokers historical data, a local CSV dump), or should the system be built against a pluggable data-source interface with a synthetic/sample dataset for development, deferring real historical replication until a vendor is chosen?
2. **Market scope**: Global liquid futures (per Research's primary recommendation) — which requires legal/broker access you haven't specified — or an NSE-only build (per the doc's explicit "separate experiment" branch)? This determines the entire data/cost/tax module.
3. **Language/stack**: Any existing preference (Python is the de facto standard for this kind of quant research stack — pandas/numpy/vectorbt or a hand-rolled event-driven backtester — but confirming before scaffolding avoids rework)?
4. **Scope for the first milestone**: Given the size of this spec (40 sections in Prompt.md), should the first deliverable be a complete-but-minimal vertical slice (data → trend signal → sizing → cost-aware backtest → core metrics, on one asset bucket or a synthetic dataset) to prove the architecture before expanding to full walk-forward/stress/carry/ML machinery? (Recommended, since Prompt.md §37/§40 explicitly reward getting a small honest result over a large unvalidated one.)

I'm not proceeding to code until at least (1)–(3) are answered, since they determine the data-ingestion module's actual interface, not just its stub shape.

### 6.1 Decisions (resolved)

| Question | Decision |
|---|---|
| Data source | Pluggable `DataSource` interface, developed against a synthetic dataset now; a real vendor is wired in later without changing downstream code. |
| Market scope | Global liquid futures (equity index, rates, FX, commodities) — the research's primary recommendation. Broker/legal-access confirmation deferred to the real-data phase. |
| Stack | Python (pandas/numpy/pytest) — the de facto standard for this kind of research system and consistent with the architecture already proposed in §7. |
| First milestone | Minimal vertical slice: synthetic data → trend signal → vol-scaled sizing → cost-aware backtest → core metrics, proving the pipeline end-to-end (leakage-safe) before expanding to walk-forward/stress/carry/ML. |

Real historical contract-level data, actual rolls, and real cost/tax figures remain **not yet available** — every backtest number produced against synthetic data in this milestone is a pipeline-correctness check, not a performance claim about the researched strategy. That distinction will be repeated at every reporting point so results are never mistaken for replication evidence.

---

## 7. Proposed Architecture

Mapped directly to Prompt.md §4's required module list, as a Python package layout (pending confirmation of stack in §6.3):

```
trading_system/
  config/              # centralized, versioned config (Prompt.md §5) — symbols, dates, params, cost scenarios, risk limits
  data/
    ingestion/         # vendor-specific loaders behind a common interface
    validation/        # timestamp/dup/missing/invalid-price/abnormal-value checks
    cleaning/          # corporate actions, splits, dividends, roll construction
    pit_store/         # point-in-time storage: every value tagged with knowledge-time, not event-time
  features/
    indicators/        # returns, sign, realized vol, momentum — each with a documented research justification
    regime/            # regime diagnostics (vol percentile, valuation state, term spread, correlation) — computed, not wired to trading in phase 1
  strategies/
    trend/             # the 63/126/252 ensemble — isolated, independently testable
    carry/             # separate module, disabled by config flag, never imported into the active signal path unless enabled
    challenger_models/ # placeholder interface for future ML challengers, inert in phase 1
  signals/             # per-strategy Signal objects: direction, strength, timestamp, strategy id, metadata
  portfolio/
    sizing/            # vol-scaling, hierarchical risk equalization
    risk/              # concentration/margin/liquidity caps, staleness checks, kill-switch
    aggregation/        # multi-strategy signal combination (inert with one active sleeve)
  execution/
    simulator/         # next-session/delayed execution, partial fills, market hours
    costs/             # commissions, spread, slippage, impact, roll costs, financing, taxes — scenario-driven (base/2x/3x)
  backtest/
    engine/            # event-driven backtest loop; walk-forward & holdout orchestration
    metrics/           # all Prompt.md §17 metrics + DSR/multiple-testing correction
    attribution/       # per-strategy, per-asset-class, per-regime, per-subperiod breakdowns
  experiments/
    tracker/           # experiment log: id, hypothesis, config, data version, result, conclusion — append-only
  reporting/
    visualization/     # equity curve, drawdown, heatmaps, rolling stats, regime overlays
    dashboard/         # research dashboard (read-only, not a profitability claim)
  live/
    paper/             # reuses backtest strategy code verbatim; logs expected vs. simulated vs. actual
    guardrails/         # mode switch RESEARCH -> BACKTEST -> PAPER -> (LIVE, disabled by default, separately gated)
  tests/
    unit/               # indicators, sizing, risk limits, cost calc, PIT safeguards
    integration/        # data -> features -> strategy -> portfolio -> backtest
```

Key architectural invariants (non-negotiable, from Prompt.md):

- **No single script.** Each box above is independently importable and independently testable.
- **Config-driven, not hardcoded.** Every parameter in §1.1's table becomes a config field with a recorded default, not a literal in code.
- **PIT boundary enforced at the data layer**, not left to strategy code to "remember" — features simply cannot see data past their timestamp because the store won't serve it.
- **Carry and ML are wired but inert** — present in the architecture, excluded from the active signal path by config flag, so enabling them later is a config change, not a rewrite.
- **Live trading path is structurally separate** from backtest/paper, gated off by default per Prompt.md §34/§35.

---

## 8. Phased Implementation Plan

1. **Scaffold + config** — package layout, config schema, experiment tracker skeleton, empty test harness. No strategy logic yet.
2. **Data layer against a synthetic/sample dataset** (unblocks all downstream work while §6.1's vendor question is resolved) — ingestion interface, validation, PIT store, roll-construction logic against dummy contracts.
3. **Feature layer** — returns, sign, realized vol estimator, trend ensemble signal — each unit-tested for leakage (no feature may read data timestamped after its own decision time).
4. **Trend strategy + sizing + risk hierarchy** — isolated module, produces a `Signal` stream, independently inspectable per Prompt.md §9.
5. **Backtest engine v1** — single strategy, base-cost scenario only, on synthetic data — validates the whole pipe end-to-end before trusting any number.
6. **Cost/execution realism** — delay variants, 1×/2×/3× cost scenarios, roll cost accounting.
7. **Metrics + reporting** — full Prompt.md §17 metric set, equity/drawdown/heatmap visualizations.
8. **Swap in real data** once §6.1/§6.2 are answered; re-run steps 5–7 against real contracts. This is the first point actual performance numbers mean anything.
9. **Robustness suite** — parameter neighborhoods, leave-one-out, walk-forward, holdout.
10. **Carry module** (built, shipped disabled) + its own activation-gate tests.
11. **Experiment log discipline + multiple-testing correction (DSR)** applied retroactively across everything tested so far.
12. **Paper-trading mode**, reusing the frozen strategy code.
13. **Final report** per Prompt.md §38–39.

ML challenger interface and the value/profitability equity sleeve are explicitly deferred beyond this plan pending §6's data-source resolution — they are architected for (empty `challenger_models/` and a stubbed equity-PIT interface) but not built out until justified.

---

## 9. Milestone 1 Status (vertical slice, synthetic data)

Implemented and passing (26 unit + integration tests, `pytest`):

- Config schema (`src/trading_system/config/`) — every parameter in §1.1's table is a dataclass field, not a literal.
- Point-in-time data boundary (`data/pit_store.py`) — `history_as_of()` is the only read path for signal code; a dedicated `close_matrix()` exists only for backtest mark-to-market accounting and is documented as off-limits to signal/feature code.
- Synthetic data source (`data/synthetic.py`) — regime-switching random walks across 4 asset-class buckets, used only to prove the pipeline; explicitly not evidence.
- Features (`features/`) — log return, sign, EWMA annualized vol, the 63/126/252 composite trend score — each a pure function of an already-PIT-sliced series.
- Trend strategy (`strategies/trend.py`) — isolated, inspectable, produces `Signal` objects per Prompt.md §9.
- Hierarchical risk-equalized sizing (`portfolio/sizing.py`) — inverse-vol scale → equal ex-ante risk per asset class → portfolio vol-target scaling → instrument/asset-class/gross-leverage caps. Documented assumption: portfolio vol is estimated under zero cross-instrument correlation pending a real covariance estimate.
- Cost model (`execution/costs.py`) — per-asset-class bps, scenario multiplier (base/2×/3×); roll costs/financing/taxes explicitly deferred (not modeled) until real contract/jurisdiction data exists.
- Execution timing (`execution/simulator.py`) — configurable delay between signal information cutoff and executed session.
- Backtest engine (`backtest/engine.py`) — weekly/daily rebalance, weight-based NAV simulation, cost charged at rebalance, full trade log.
- Metrics (`backtest/metrics.py`) — CAGR, vol, Sharpe, Sortino, max drawdown + duration, Calmar, turnover.
- Experiment tracker (`experiments/tracker.py`) — append-only JSONL log, one record per run, per Prompt.md §29.
- Leakage regression tests: a decision date's signal is proven bit-for-bit identical whether or not the underlying store holds data past that date; execution-delay changes are proven to only shift timing, never the signal itself.

**Explicitly not yet done** (next milestones, per §8's phased plan): real data source, actual contract rolls/margin/financing/taxes, walk-forward/holdout validation, parameter-neighborhood robustness sweeps, leave-one-out tests, carry module, multiple-testing correction (DSR), visualization/dashboard, paper-trading mode. The synthetic-data run in `cli/run_backtest.py` produces metrics (CAGR ≈2.6%, Sharpe ≈0.46 on one seed) that exist solely to confirm the pipeline runs without error and without NaNs/blow-ups — they carry no information about whether the real trend hypothesis works, and must never be quoted as if they did.

## 10. Milestone 2 Status (robustness/attribution suite, carry satellite, paper trading)

Implemented and passing (90 unit + integration tests total):

- Full robustness suite run against the synthetic baseline (`experiments/reports/robustness_suite_v1/`): lookback-neighborhood sweep, vol-window sweep, cost-scenario sweep (base/2×/3×), execution-delay sweep (0/1/2 sessions), rebalance-frequency sweep (weekly/daily), leave-one-asset-class-out, leave-one-instrument-out, yearly subperiod breakdown, in-sample/holdout split, and a Deflated Sharpe Ratio correction over all 41 trials run.
- **Result on this synthetic dataset/seed: the frozen baseline is net-negative (Sharpe ≈ −0.14, CAGR ≈ −1.0%) after realistic costs.** Before accepting that at face value, a dedicated direction-sanity check (`tests/integration/test_strategy_sanity.py`) confirmed the strategy correctly goes long on a monotonic uptrend and short on a monotonic downtrend, and profits from either after near-zero costs — ruling out a sign/wiring bug. The negative aggregate result is therefore a real (if unglamorous) property of this particular synthetic regime-switching dataset and parameter combination, most likely whipsaw losses at regime transitions given lookbacks (up to 252 days) comparable to or longer than the synthetic regime length (~250–500 days). This is reported plainly per Prompt.md §37 — **it is a pipeline-mechanics/honesty-of-reporting result, not evidence about real markets**, since the underlying data is fabricated.
- Trend+carry complementarity test: the synthetic carry placeholder (independent RNG stream by construction) measured a 0.019 correlation with trend — confirming the independence design works — and correctly **failed** the activation gate on profitability grounds (pure noise minus costs is negative), which is the correct behavior for a gate that shouldn't be fooled by an uncorrelated-but-worthless signal.
- Carry satellite built (`strategies/carry.py`, `strategies/carry_activation.py`), disabled by default, with an explicitly scoped activation-gate function (documented as a *necessary, not sufficient* subset of Research.md's full gate).
- Multi-strategy equal-ex-ante-risk aggregator (`portfolio/aggregation.py`) added so `BacktestEngine` can run trend-only, carry-only, or trend+carry without duplicating sizing logic.
- Paper-trading mode (`live/paper/paper_trader.py`) reuses the exact same `Strategy`/`compute_target_weights` code as the backtest (verified by a test asserting position parity at a shared decision date) and logs every field Prompt.md §33 requires. Honest limitation: with no live data feed, "actual market price" and "simulated execution price" are the same historical close, so the expected-vs-simulated-execution diff is always 0.0 and explicitly flagged as not meaningful yet.
- Risk guardrails (`live/guardrails.py`): data staleness, daily loss, drawdown, max simultaneous positions, duplicate-order rejection, emergency-shutdown latch. `SystemConfig.mode="live"` remains hard-blocked at construction time (Prompt.md §34/§35) since no live execution path exists.

## 11. Milestone 3: Vendor/Broker Integration

Per explicit user request: the data layer must work with **any** vendor, with **Zerodha (Kite Connect), Angel One (SmartAPI), and INDmoney (INDstocks API)** as first-class, ready-to-use adapters, and a documented path for anyone else to add their own with minimal code. Full detail in **[Docs/Vendor_Integration.md](Vendor_Integration.md)**; summary here:

- The mechanism that makes "any vendor" true is not new — it's the existing `DataSource` protocol (`get_universe`, `get_prices`) from Milestone 1. All three broker adapters and a generic local-file adapter (`brokers/`) implement exactly that, so nothing downstream changes per vendor.
- **Zerodha**: verified live against this project's connected Kite MCP session on 2026-09-20 — `search_instruments` (no login required) confirmed the exact instrument schema (instrument_token, exchange, tradingsymbol, segment, expiry, tick_size, lot_size) across NSE/NFO/MCX/CDS. `historical_data()` itself could not be exercised live (the connected session isn't logged in), so its response parsing is written to Kite Connect's documented schema and unit-tested against a mock.
- **Angel One**: built against SmartAPI's publicly documented `getCandleData()` contract (confirmed via web research, no live session available). Not execution-tested against a real account.
- **INDmoney**: initially assumed (incorrectly) not to have a public API — web research corrected this: it has one, branded "INDstocks Trading API" (`api-docs.indstocks.com`), REST-based, with a documented historical-candle endpoint. Built against that documented contract. **One field is an explicit unconfirmed guess** (the daily-interval string, assumed `"1day"`) — flagged in the code and docs rather than silently assumed correct.
- **Generic local-file adapter**: works with any vendor that can export to CSV/Parquet — the true "any vendor" fallback, requiring zero new code.
- **Credential policy enforced structurally**: no adapter accepts or stores API keys/passwords/TOTP; each takes an already-authenticated client object the user constructs themselves.
- **Honesty gap flagged explicitly**: none of the three broker adapters have been execution-tested against a live authenticated account in this environment. `scripts/vendor_smoke_test.py` is provided for the user to run that check themselves before trusting one.
- **Scope reconciliation**: Zerodha/Angel One/INDmoney are NSE/BSE/MCX/CDS-focused Indian brokers. Using them activates Research.md's **India-specific branch** (separate tax/cost model, separate instrument universe, separate validation run) rather than the global-futures universe §6.1 picked as the primary research target. This is not a silent scope change — both tracks now exist side by side, and results from each must be reported separately (see Vendor_Integration.md's closing section for exactly which asset-class buckets are/aren't fillable through these brokers).

## 12. Summary Position

- Research interpreted: **yes**, in full, including its self-declared limitations.
- Nothing in Research.md has been silently changed. Every place where a concrete number is presented as "a default to test" rather than a finding has been carried forward as configurable, not hardcoded.
- The single biggest risk to the entire project, stated by the research itself, is that **no independent replication has happened yet** — this document does not change that; it sets up the system that will attempt it.
- The synthetic-data robustness suite (Milestone 2) found the frozen baseline net-negative on this dataset — reported plainly, not tuned away, after confirming it isn't a bug.
- Vendor integration (Milestone 3) makes real-data replication achievable without further architecture changes, but real execution-testing against a live broker account, and the India-branch cost/tax model, both remain open until the user runs them.

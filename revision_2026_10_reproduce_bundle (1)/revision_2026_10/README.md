# Revision 2026-10 — additional analyses requested by the advisor

Source of the requests: `D:\uni\AIID\Hướng sửa bài.md` (advisor, 2026-09-30), reviewed against
`final.docx` (18/9/2026). This folder only ADDS files; no script or output elsewhere in the repo is
modified. Manuscript work happens in `D:\uni\AIID\final_v2.md` (copy of `final.md`).

## Environment

- Python 3.13: `C:\Users\trucf\AppData\Local\Programs\Python\Python313\python.exe`
  (pyfixest 0.60 `pyfixest.core.demean`, duckdb 1.5.4, pyarrow 24, numpy 2.4, scipy 1.17, matplotlib 3.10).
  The `python` on PATH (3.14) lacks these packages.
- Estimation is done by Frisch–Waugh–Lovell: variables are demeaned once on the full fixed-effect set
  (pair–HS2, exporter–year, importer–year, HS2–year) with `pyfixest.core.demean`, then OLS on the
  demeaned columns. Cluster-robust variances are computed directly from the scores; two-way (pair + year)
  variances use Cameron–Gelbach–Miller, V = V_pair + V_year − V_pair×year, with fixest's default
  small-sample conventions (cluster.df = "min", t.df = "min", so two-way p-values use t with 15 df).
- PPML models (16.75M rows) are NOT re-estimated (RAM); all PPML numbers stay as published.
- `cache/` holds memory-mapped demeaned arrays; it is disposable and can be deleted after the run.

## Layout and run order

| Step | Script | Purpose |
|---|---|---|
| 17a | `scripts/17a_replication_gate.py` | Re-estimate Table 4 cols (4)–(5); must match stored coefficients, SEs and N before anything else runs |
| 17b | `scripts/17b_fta_depth_diagnostics.py` | Advisor item 4: FTA vs DTA-depth correlation, distribution, within-FE collinearity, joint-model effects at representative depths |
| 17c | `scripts/17c_link_size_heterogeneity.py` | Advisor item 1: GPR × Depth × LaggedTrade, log-USD variant, four size groups, size × year robustness |
| 17c2 | `scripts/17c2_size_diagnostics.py` | Post-hoc: split samples, size-group-specific time FE, excluding 2022, excluding intra-EU, Table 4 col (5) without intra-EU |
| 17c3 | `scripts/17c3_eu_interaction.py` | Post-hoc: Table 4 col (5) + GPR × intra-EU on the full sample |
| 17d | `scripts/17d_optional_checks.py` | Figure 3 with the true covariance; dropping 2020 / 2020–21 (COVID); value-weighted survival LPM |
| 17e | `scripts/17e_figures.py` | Figures from the CSVs in `tables/` (run after 17c2 and 17d) |
| 17f | `scripts/17f_eu_checks.py` | Post-hoc: Table 7 (44 economies) with and without intra-EU pairs, survival LPM and PPML (pyfixest `fepois`, replicated against fixest first) |

Results and interpretation: `RESULTS_MEMO.md` (Vietnamese). Steps marked post-hoc were added after 17c and
are reported as diagnostics, not as pre-registered tests.

Shared helpers: `scripts/r17_common.py`. Tables go to `tables/`, figures to `figures/`, logs to `logs/`.

## Pre-registered decision rules for link-size heterogeneity (fixed 2026-10-04, before estimation)

Outcome: one-year survival of an at-risk pair–HS2 link (LPM), same sample and fixed effects as Table 4.

Specifications (all with pair–HS2, exporter–year, importer–year, HS2–year fixed effects):

- **S1 (advisor's specification, joint):** Table 4 col (5) plus GPR×LaggedTrade, Depth×LaggedTrade,
  FTA×LaggedTrade, GPR×FTA×LaggedTrade and GPR×Depth×LaggedTrade. LaggedTrade = ln(1 + lagged value,
  USD million), as in the paper, centred at its sample median so that GPR×Depth is the effect for the
  median link. Implied GPR×Depth effects reported at the 10th–90th percentiles of LaggedTrade.
- **S1-depth:** the same on Table 4 col (4) (no FTA terms).
- **S2:** S1 with size measured as ln(lagged value in USD), centred at its median, because ln(1 + USD m)
  is almost flat below USD 100,000, where more than half of the links lie.
- **S3 (primary for classification):** four groups of lagged value, g = 1..4:
  < USD 10k, 10k–100k, 100k–1M, ≥ 1M. Group-specific GPR×Depth (θ_g) and GPR×FTA terms, group-specific
  Depth and FTA level terms, group dummies, GPR×group dummies, plus the continuous LaggedTrade control.
- **S3b:** S3 with GPR×group replaced by group × year fixed effects. **S1b:** S1 with GPR×LaggedTrade
  replaced by LaggedTrade × year slopes.

Absolute effect: θ_g (percentage points of survival). Relative effect: ρ_g = −θ_g / p̄_g, where p̄_g is
the mean exit rate of group g in the estimation sample (proportional change in the exit probability).

Classification uses S3 with two-way (pair + year) clustered inference, as in the paper's tables;
pair-clustered results are reported alongside. If the two disagree, the text calls the pattern suggestive.

- **Absolute concentration** in small links: θ_1 is the most negative group effect and θ_1 − θ_4 < 0 with
  p < 0.05.
- **Relative decline** with size: ρ_1 − ρ_4 > 0 with p < 0.05.
- **Scenario A:** absolute concentration AND relative decline → link-size heterogeneity is the main
  evidence for selective adjustment ("consistent with a fixed-cost mechanism", never "proves").
- **Scenario B:** absolute concentration but no relative decline → losses of links are concentrated
  among small links because exits occur there, while depth raises the exit probability proportionally
  across sizes; "selective pruning" is not used as a finding; fixed costs are one of several readings.
- **Scenario C:** no absolute concentration → selective pruning is dropped; only the negative survival
  effect is reported.

## Optional checks (approved 2026-10-04)

1. Figure 3 with the true covariance of (GPR×FTA, GPR×Depth): net effect γ1 + γ2·Depth, 95% band from
   Var = V11 + Depth²·V22 + 2·Depth·V12; report the depth where the net effect crosses zero and where the
   upper bound first falls below zero.
2. COVID: Table 4 col (5) excluding 2020, and excluding 2020–2021.
3. Value-weighted survival LPM: Table 4 col (5) weighted by lagged trade value (USD m); the coefficient
   is the change in the share of lagged trade value carried by surviving links.

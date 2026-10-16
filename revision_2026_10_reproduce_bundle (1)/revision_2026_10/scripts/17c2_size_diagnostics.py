"""Step 17c2 — post-hoc diagnostics for the link-size result of step 17c.

NOT pre-registered. Step 17c classified the pooled size-group model (S3) as
scenario C: the depth x GPR survival effect is not concentrated among small
links and is largest for links above USD 1 million. The published Table 5
Panel B, which re-estimates the model on established-link subsamples, gives a
much smaller effect for large links. These checks locate the source of the
difference and test whether the pattern is driven by 2022 or by intra-EU links.

  (a) split samples: Table 4 col (5) estimated separately in each size group
      (every fixed effect re-estimated, as in Panel B)
  (b) S3c: pooled size-group model with size-group-specific exporter-year,
      importer-year and HS2-year effects (common pair-HS2 effects)
  (c) S3 excluding 2022
  (d) S3 excluding intra-EU pairs (both partners EU members in t-1)
  (e) Table 4 col (5) excluding intra-EU pairs
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r17_common import (  # noqa: E402
    LOGS,
    PAIR_CLUSTER,
    REPO,
    SIZE_LABELS,
    SURVIVAL_FE,
    SURVIVAL_FILE,
    TABLES,
    FESample,
    Log,
    factorize,
    fit_and_tabulate,
    gpr_by_year,
    lincom,
    read_columns,
    singleton_keep,
    size_group,
    wald,
)

log = Log(LOGS / "17c2_size_diagnostics.log")

cols = [
    "survive_t",
    "year",
    "trade_value_l1_musd",
    "log1p_trade_value_l1_musd",
    "fta_active_l1",
    "depth_strict_l1_10",
    *SURVIVAL_FE,
    PAIR_CLUSTER,
]
raw = read_columns(SURVIVAL_FILE, cols)
lookup = np.full(2100, np.nan)
for year, value in gpr_by_year("gpr_mean_z").items():
    lookup[year] = value
G_all = lookup[raw["year"]]
group_all = size_group(raw["trade_value_l1_musd"])

# exporter / importer from the deterministic pair-HS2 id (see python/13a, step 13a)
pair_index = raw["pair_hs2_fe_id"] // 100
exp_rank = pair_index // 160 + 1
imp_rank = pair_index % 160 + 1
countries = pd.read_csv(REPO / "data" / "processed" / "country_sample_160.csv")
rank_to_iso = dict(zip(countries["final_sample_rank"].astype(int), countries["country_iso3"]))
EU_CORE = {
    "AUT", "BEL", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA",
    "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "SVK", "SVN", "ESP", "SWE", "BGR", "ROU",
}
missing = sorted((EU_CORE | {"HRV", "GBR"}) - set(rank_to_iso.values()))
log("EU/UK economies missing from the sample:", missing or "none")
status_year = raw["year"] - 1  # agreements are measured in t-1


iso_by_rank = np.array([rank_to_iso.get(r, "") for r in range(161)], dtype=object)
core_rank = np.isin(iso_by_rank, sorted(EU_CORE))
hrv_rank = iso_by_rank == "HRV"
gbr_rank = iso_by_rank == "GBR"


def eu_member(ranks: np.ndarray) -> np.ndarray:
    """EU membership in the status year t-1 (Croatia from 2013, UK to 2020)."""
    return core_rank[ranks] | (hrv_rank[ranks] & (status_year >= 2013)) | (gbr_rank[ranks] & (status_year <= 2020))


intra_eu = eu_member(exp_rank) & eu_member(imp_rank)
log(f"intra-EU at-risk link-years: {intra_eu.mean():.1%} of the panel; mean depth intra-EU = "
    f"{raw['depth_strict_l1_10'][intra_eu].mean():.2f}, other FTA links = "
    f"{raw['depth_strict_l1_10'][(~intra_eu) & (raw['fta_active_l1'] == 1)].mean():.2f}")


def subsample(mask: np.ndarray, tag: str, extra_fe: list[np.ndarray] | None = None, fe_override: list[np.ndarray] | None = None):
    idx = np.flatnonzero(mask)
    base = fe_override if fe_override is not None else [raw[c] for c in SURVIVAL_FE]
    codes = [factorize(c[idx])[0] for c in base] + [factorize(e[idx])[0] for e in (extra_fe or [])]
    keep = singleton_keep(codes, iterative=False)
    sel = idx[keep]
    sample = FESample(tag, [c[keep] for c in codes], raw[PAIR_CLUSTER][sel], raw["year"][sel], log=log)
    log(f"{tag}: n = {sel.size:,}")
    return sample, sel


def model5_columns(sel: np.ndarray) -> dict[str, np.ndarray]:
    F = raw["fta_active_l1"][sel].astype(np.float64)
    D = raw["depth_strict_l1_10"][sel].astype(np.float64)
    G = G_all[sel]
    return {
        "y_survive": raw["survive_t"][sel].astype(np.float64),
        "gf": G * F,
        "gd": G * D,
        "f": F,
        "d": D,
        "l": raw["log1p_trade_value_l1_musd"][sel].astype(np.float64),
    }


def s3_demean(sample: FESample, sel: np.ndarray, with_group_terms: bool) -> list[str]:
    F = raw["fta_active_l1"][sel].astype(np.float64)
    D = raw["depth_strict_l1_10"][sel].astype(np.float64)
    G = G_all[sel]
    grp = group_all[sel]
    sample.demean(
        {
            "y_survive": raw["survive_t"][sel].astype(np.float64),
            "l": raw["log1p_trade_value_l1_musd"][sel].astype(np.float64),
        }
    )
    names = []
    for g in range(4):
        b = (grp == g).astype(np.float64)
        block = {f"gd_b{g}": G * D * b, f"gf_b{g}": G * F * b, f"d_b{g}": D * b, f"f_b{g}": F * b}
        if with_group_terms and g > 0:
            block[f"b{g}"] = b
            block[f"g_b{g}"] = G * b
        sample.demean(block)
        names += list(block)
    return names + ["l"]


def size_summary(model: str, fit: dict, vcovs: dict, sel: np.ndarray) -> tuple[list[dict], list[dict]]:
    names, beta = fit["names"], fit["beta"]
    grp = group_all[sel]
    exit_t = 1.0 - raw["survive_t"][sel]
    rates = np.array([exit_t[grp == g].mean() for g in range(4)])
    idx = [names.index(f"gd_b{g}") for g in range(4)]
    rows, tests = [], []
    for scheme, (V, df, _) in vcovs.items():
        for g in range(4):
            c = np.zeros(len(names))
            c[idx[g]] = 1.0
            th = lincom(beta, V, c, df)
            rel = lincom(beta, V, -c / rates[g], df)
            rows.append({"model": model, "inference": scheme, "group": SIZE_LABELS[g], "exit_rate": rates[g],
                         "theta_pp": 100 * th["estimate"], "theta_se_pp": 100 * th["std_error"], "theta_p": th["p_value"],
                         "relative_pct": 100 * rel["estimate"], "relative_se_pct": 100 * rel["std_error"], "relative_p": rel["p_value"]})
        c_abs = np.zeros(len(names))
        c_abs[idx[0]], c_abs[idx[3]] = 1.0, -1.0
        c_rel = np.zeros(len(names))
        c_rel[idx[0]], c_rel[idx[3]] = -1.0 / rates[0], 1.0 / rates[3]
        d_abs, d_rel = lincom(beta, V, c_abs, df), lincom(beta, V, c_rel, df)
        R = np.zeros((3, len(names)))
        for r in range(3):
            R[r, idx[r]], R[r, idx[r + 1]] = 1.0, -1.0
        eq = wald(beta, V, R, df)
        thetas = beta[idx]
        abs_conc = bool(np.argmin(thetas) == 0 and d_abs["estimate"] < 0 and d_abs["p_value"] < 0.05)
        rel_decl = bool(d_rel["estimate"] > 0 and d_rel["p_value"] < 0.05)
        tests.append({"model": model, "inference": scheme, "wald_equal_theta_p": eq["p_value"],
                      "theta_small_minus_large_pp": 100 * d_abs["estimate"], "theta_small_minus_large_p": d_abs["p_value"],
                      "rho_small_minus_large_pct": 100 * d_rel["estimate"], "rho_small_minus_large_p": d_rel["p_value"],
                      "most_negative_group": SIZE_LABELS[int(np.argmin(thetas))],
                      "scenario": "A" if (abs_conc and rel_decl) else ("B" if abs_conc else "C")})
    return rows, tests


group_rows, test_rows, coef_tables = [], [], []

# (a) split samples, one size group at a time
for g in range(4):
    sample, sel = subsample(group_all == g, f"split_group{g}")
    sample.demean(model5_columns(sel))
    fit, table, vcovs = fit_and_tabulate(sample, "y_survive", ["gf", "gd", "f", "d", "l"], f"split_{SIZE_LABELS[g]}")
    coef_tables.append(table)
    rate = (1.0 - raw["survive_t"][sel]).mean()
    for scheme, (V, df, _) in vcovs.items():
        k = fit["names"].index("gd")
        se = np.sqrt(V[k, k])
        group_rows.append({"model": "(a) split samples", "inference": scheme, "group": SIZE_LABELS[g], "exit_rate": rate,
                           "theta_pp": 100 * fit["beta"][k], "theta_se_pp": 100 * se,
                           "theta_p": float(table[(table.inference == scheme) & (table.term == "gd")]["p_value"].iloc[0]),
                           "relative_pct": -100 * fit["beta"][k] / rate, "relative_se_pct": 100 * se / rate,
                           "relative_p": float(table[(table.inference == scheme) & (table.term == "gd")]["p_value"].iloc[0]),
                           "n": sel.size})
    del sample

# (b) S3c: size-group-specific time-varying fixed effects, common pair-HS2 effects
gy = group_all.astype(np.int64) * 1_000_000
fe_b = [raw["pair_hs2_fe_id"], raw["exporter_year_fe_id"] + gy, raw["importer_year_fe_id"] + gy, raw["hs2_year_fe_id"] + gy]
sample, sel = subsample(np.ones(group_all.size, dtype=bool), "s3c_group_specific_time_fe", fe_override=fe_b)
names = s3_demean(sample, sel, with_group_terms=False)
fit, table, vcovs = fit_and_tabulate(sample, "y_survive", names, "(b) S3c group-specific time FE")
coef_tables.append(table)
r, t = size_summary("(b) S3c group-specific time FE", fit, vcovs, sel)
group_rows += r
test_rows += t
del sample

# (c) S3 excluding 2022
sample, sel = subsample(raw["year"] != 2022, "s3_excl2022")
names = s3_demean(sample, sel, with_group_terms=True)
fit, table, vcovs = fit_and_tabulate(sample, "y_survive", names, "(c) S3 excluding 2022")
coef_tables.append(table)
r, t = size_summary("(c) S3 excluding 2022", fit, vcovs, sel)
group_rows += r
test_rows += t
del sample

# (d) S3 excluding intra-EU pairs
sample, sel = subsample(~intra_eu, "s3_excl_intra_eu")
names = s3_demean(sample, sel, with_group_terms=True)
fit, table, vcovs = fit_and_tabulate(sample, "y_survive", names, "(d) S3 excluding intra-EU")
coef_tables.append(table)
r, t = size_summary("(d) S3 excluding intra-EU", fit, vcovs, sel)
group_rows += r
test_rows += t
del sample

# (e) Table 4 col (5) excluding intra-EU pairs
sample, sel = subsample(~intra_eu, "model5_excl_intra_eu")
sample.demean(model5_columns(sel))
fit, table, vcovs = fit_and_tabulate(sample, "y_survive", ["gf", "gd", "f", "d", "l"], "(e) Table 4 col 5 excluding intra-EU")
coef_tables.append(table)
log(table[table.term.isin(["gf", "gd"])].to_string(index=False, float_format=lambda v: f"{v:.6f}"))
del sample

groups = pd.DataFrame(group_rows)
tests = pd.DataFrame(test_rows)
groups.to_csv(TABLES / "17c2_size_diagnostics_groups.csv", index=False)
tests.to_csv(TABLES / "17c2_size_diagnostics_tests.csv", index=False)
pd.concat(coef_tables, ignore_index=True).to_csv(TABLES / "17c2_size_diagnostics_coefficients.csv", index=False)
log(groups.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
log(tests.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
log("done")

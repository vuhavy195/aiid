"""Step 17c — link-size heterogeneity in the depth-survival interaction (advisor item 1).

Specifications follow README.md ("Pre-registered decision rules", fixed before
estimation):
  S1        Table 4 col (5) + GPR x Depth x LaggedTrade with all lower-order terms
            (LaggedTrade = ln(1 + USD m), centred at the sample median)
  S1-depth  the same on Table 4 col (4)
  S1b       S1 with GPR x LaggedTrade replaced by LaggedTrade x year slopes
  S2        S1 with size measured as ln(USD), centred at its median
  S3        four lagged-size groups (<10k, 10k-100k, 100k-1M, >=1M USD)
  S3b       S3 with GPR x group replaced by group x year fixed effects
Classification into scenarios A/B/C uses S3 with two-way (pair + year) inference.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r17_common import (  # noqa: E402
    CACHE,
    LOGS,
    PAIR_CLUSTER,
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
    size_group,
    wald,
)

log = Log(LOGS / "17c_link_size_heterogeneity.log")

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
keep = np.load(CACHE / "survival_keep_mask.npy")
raw = {k: v[keep] for k, v in raw.items()}
n = raw["survive_t"].size
log(f"estimation sample n = {n:,}")

lookup = np.full(2100, np.nan)
for year, value in gpr_by_year("gpr_mean_z").items():
    lookup[year] = value
G = lookup[raw["year"]]
F = raw["fta_active_l1"].astype(np.float64)
D = raw["depth_strict_l1_10"].astype(np.float64)
L = raw["log1p_trade_value_l1_musd"].astype(np.float64)
usd = raw["trade_value_l1_musd"].astype(np.float64) * 1e6
L2 = np.log(usd)
m_L, m_L2 = np.median(L), np.median(L2)
Lc, L2c = L - m_L, L2 - m_L2
group = size_group(raw["trade_value_l1_musd"])
exit_t = 1.0 - raw["survive_t"].astype(np.float64)
log(f"median LaggedTrade = {m_L:.5f} (USD {np.expm1(m_L) * 1e6:,.0f}); median ln(USD) = {m_L2:.4f} (USD {np.exp(m_L2):,.0f})")

# ------------------------------------------------------------- descriptives
desc_rows = []
total_value = usd.sum()
for g, label in enumerate(SIZE_LABELS):
    sel = group == g
    desc_rows.append(
        {
            "group": label,
            "n": int(sel.sum()),
            "share_links": sel.mean(),
            "exit_rate": exit_t[sel].mean(),
            "share_lagged_value": usd[sel].sum() / total_value,
            "share_of_all_exits": exit_t[sel].sum() / exit_t.sum(),
            "value_share_of_exits_within_group": (usd[sel] * exit_t[sel]).sum() / usd[sel].sum(),
            "fta_share": F[sel].mean(),
            "mean_depth": D[sel].mean(),
            "mean_depth_fta": D[sel & (F == 1)].mean(),
        }
    )
desc_rows.append(
    {
        "group": "all",
        "n": n,
        "share_links": 1.0,
        "exit_rate": exit_t.mean(),
        "share_lagged_value": 1.0,
        "share_of_all_exits": 1.0,
        "value_share_of_exits_within_group": (usd * exit_t).sum() / total_value,
        "fta_share": F.mean(),
        "mean_depth": D.mean(),
        "mean_depth_fta": D[F == 1].mean(),
    }
)
desc = pd.DataFrame(desc_rows)
desc.to_csv(TABLES / "17c_size_group_descriptives.csv", index=False)
log(desc.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
exit_rate = desc.set_index("group")["exit_rate"].to_dict()

# ------------------------------------------------------------- main sample
sample = FESample(
    "survival_main",
    [factorize(raw[c])[0] for c in SURVIVAL_FE],
    raw[PAIR_CLUSTER],
    raw["year"],
    log=log,
)
years = np.unique(raw["year"])
# Build and demean in blocks to keep memory low (each column is 64 MB).
sample.demean(
    {
        "g_lc": G * Lc,
        "d_lc": D * Lc,
        "f_lc": F * Lc,
        "gf_lc": G * F * Lc,
        "gd_lc": G * D * Lc,
    }
)
sample.demean(
    {
        "l2": L2c,
        "g_l2": G * L2c,
        "d_l2": D * L2c,
        "f_l2": F * L2c,
        "gf_l2": G * F * L2c,
        "gd_l2": G * D * L2c,
    }
)
for start in range(1, len(years), 5):
    sample.demean({f"lc_y{t}": Lc * (raw["year"] == t) for t in years[start : start + 5]})
for g in range(4):
    b = (group == g).astype(np.float64)
    block = {
        f"gd_b{g}": G * D * b,
        f"gf_b{g}": G * F * b,
        f"d_b{g}": D * b,
        f"f_b{g}": F * b,
    }
    if g > 0:
        block[f"b{g}"] = b
        block[f"g_b{g}"] = G * b
    sample.demean(block)
    del block, b

specs = {
    "S1_joint_lagged_trade": ["gf", "gd", "f", "d", "l", "g_lc", "d_lc", "f_lc", "gf_lc", "gd_lc"],
    "S1_depth_lagged_trade": ["gd", "d", "l", "g_lc", "d_lc", "gd_lc"],
    "S1b_joint_size_by_year": ["gf", "gd", "f", "d", "l", "d_lc", "f_lc", "gf_lc", "gd_lc"] + [f"lc_y{t}" for t in years[1:]],
    "S2_joint_log_usd": ["gf", "gd", "f", "d", "l2", "g_l2", "d_l2", "f_l2", "gf_l2", "gd_l2"],
    "S3_size_groups": [f"{p}_b{g}" for g in range(4) for p in ("gd", "gf", "d", "f")]
    + ["b1", "b2", "b3", "g_b1", "g_b2", "g_b3", "l"],
}

coef_tables, fits = [], {}
for model, names in specs.items():
    log(f"fitting {model} ({len(names)} regressors)")
    fit, table, vcovs = fit_and_tabulate(sample, "y_survive", names, model)
    coef_tables.append(table)
    fits[model] = (fit, vcovs)
    for scheme, (V, df, info) in vcovs.items():
        if info:
            log(f"  {model} {scheme}: {info}")
del sample

# ------------------------------------------------------------- S3b (group x year FE)
log("fitting S3b_size_groups_group_year_fe (5 fixed effects)")
group_year = group.astype(np.int64) * 10000 + raw["year"].astype(np.int64)
sample_gy = FESample(
    "survival_group_year_fe",
    [factorize(raw[c])[0] for c in SURVIVAL_FE] + [factorize(group_year)[0]],
    raw[PAIR_CLUSTER],
    raw["year"],
    log=log,
)
columns = {"y_survive": raw["survive_t"].astype(np.float64), "l": L}
for g in range(4):
    b = (group == g).astype(np.float64)
    columns[f"gd_b{g}"] = G * D * b
    columns[f"gf_b{g}"] = G * F * b
    columns[f"d_b{g}"] = D * b
    columns[f"f_b{g}"] = F * b
sample_gy.demean(columns)
del columns
names_3b = [f"{p}_b{g}" for g in range(4) for p in ("gd", "gf", "d", "f")] + ["l"]
fit, table, vcovs = fit_and_tabulate(sample_gy, "y_survive", names_3b, "S3b_size_groups_group_year_fe")
coef_tables.append(table)
fits["S3b_size_groups_group_year_fe"] = (fit, vcovs)
del sample_gy

coefs = pd.concat(coef_tables, ignore_index=True)
coefs.to_csv(TABLES / "17c_coefficients.csv", index=False)

# ------------------------------------------------------------- implied effects, continuous specs
reference_usd = [1e3, 1e4, 1e5, 1e6, 1e7]
rows = []
for model, size_var, centre, to_size in (
    ("S1_joint_lagged_trade", "gd_lc", m_L, lambda u: np.log1p(u / 1e6)),
    ("S1_depth_lagged_trade", "gd_lc", m_L, lambda u: np.log1p(u / 1e6)),
    ("S1b_joint_size_by_year", "gd_lc", m_L, lambda u: np.log1p(u / 1e6)),
    ("S2_joint_log_usd", "gd_l2", m_L2, np.log),
):
    fit, vcovs = fits[model]
    names = fit["names"]
    for scheme, (V, df, _) in vcovs.items():
        for u in reference_usd:
            c = np.zeros(len(names))
            c[names.index("gd")] = 1.0
            c[names.index(size_var)] = to_size(u) - centre
            res = lincom(fit["beta"], V, c, df)
            rows.append({"model": model, "inference": scheme, "lagged_value_usd": u, **res})
        k = names.index(size_var)
        se = np.sqrt(V[k, k])
        rows.append(
            {
                "model": model,
                "inference": scheme,
                "lagged_value_usd": "triple-interaction coefficient",
                "estimate": fit["beta"][k],
                "std_error": se,
                "p_value": float(coefs[(coefs.model == model) & (coefs.inference == scheme) & (coefs.term == size_var)]["p_value"].iloc[0]),
            }
        )
implied = pd.DataFrame(rows)
implied.to_csv(TABLES / "17c_implied_effects_continuous.csv", index=False)
log(implied.to_string(index=False, float_format=lambda v: f"{v:.6f}"))

# ------------------------------------------------------------- size-group effects and tests
median_depth_fta = float(np.median(D[F == 1]))
group_rows, test_rows = [], []
for model in ("S3_size_groups", "S3b_size_groups_group_year_fe"):
    fit, vcovs = fits[model]
    names, beta = fit["names"], fit["beta"]
    idx = [names.index(f"gd_b{g}") for g in range(4)]
    idx_f = [names.index(f"gf_b{g}") for g in range(4)]
    rates = np.array([exit_rate[label] for label in SIZE_LABELS])
    for scheme, (V, df, _) in vcovs.items():
        for g, label in enumerate(SIZE_LABELS):
            c = np.zeros(len(names))
            c[idx[g]] = 1.0
            theta = lincom(beta, V, c, df)
            rel = lincom(beta, V, -c / rates[g], df)
            c_net = np.zeros(len(names))
            c_net[idx_f[g]] = 1.0
            c_net[idx[g]] = median_depth_fta
            net = lincom(beta, V, c_net, df)
            group_rows.append(
                {
                    "model": model,
                    "inference": scheme,
                    "group": label,
                    "exit_rate": rates[g],
                    "theta_gpr_x_depth": theta["estimate"],
                    "theta_se": theta["std_error"],
                    "theta_p": theta["p_value"],
                    "theta_ci_low": theta["ci_low"],
                    "theta_ci_high": theta["ci_high"],
                    "relative_change_exit_prob": rel["estimate"],
                    "relative_se": rel["std_error"],
                    "relative_p": rel["p_value"],
                    "relative_ci_low": rel["ci_low"],
                    "relative_ci_high": rel["ci_high"],
                    "net_effect_fta_median_depth": net["estimate"],
                    "net_effect_se": net["std_error"],
                    "net_effect_p": net["p_value"],
                }
            )
        R_abs = np.zeros((3, len(names)))
        R_rel = np.zeros((3, len(names)))
        for r in range(3):
            R_abs[r, idx[r]], R_abs[r, idx[r + 1]] = 1.0, -1.0
            R_rel[r, idx[r]], R_rel[r, idx[r + 1]] = -1.0 / rates[r], 1.0 / rates[r + 1]
        eq_abs = wald(beta, V, R_abs, df)
        eq_rel = wald(beta, V, R_rel, df)
        c_abs = np.zeros(len(names))
        c_abs[idx[0]], c_abs[idx[3]] = 1.0, -1.0
        d_abs = lincom(beta, V, c_abs, df)  # theta_<10k - theta_>=1M
        c_rel = np.zeros(len(names))
        c_rel[idx[0]], c_rel[idx[3]] = -1.0 / rates[0], 1.0 / rates[3]
        d_rel = lincom(beta, V, c_rel, df)  # rho_<10k - rho_>=1M
        thetas = beta[idx]
        abs_conc = bool(np.argmin(thetas) == 0 and d_abs["estimate"] < 0 and d_abs["p_value"] < 0.05)
        rel_decl = bool(d_rel["estimate"] > 0 and d_rel["p_value"] < 0.05)
        scenario = "A" if (abs_conc and rel_decl) else ("B" if abs_conc else "C")
        test_rows.append(
            {
                "model": model,
                "inference": scheme,
                "wald_equal_theta_F": eq_abs["F"],
                "wald_equal_theta_p": eq_abs["p_value"],
                "wald_equal_relative_F": eq_rel["F"],
                "wald_equal_relative_p": eq_rel["p_value"],
                "theta_small_minus_large": d_abs["estimate"],
                "theta_small_minus_large_se": d_abs["std_error"],
                "theta_small_minus_large_p": d_abs["p_value"],
                "rho_small_minus_large": d_rel["estimate"],
                "rho_small_minus_large_se": d_rel["std_error"],
                "rho_small_minus_large_p": d_rel["p_value"],
                "most_negative_group": SIZE_LABELS[int(np.argmin(thetas))],
                "absolute_concentration": abs_conc,
                "relative_decline": rel_decl,
                "scenario": scenario,
            }
        )
groups_df = pd.DataFrame(group_rows)
tests_df = pd.DataFrame(test_rows)
groups_df.to_csv(TABLES / "17c_size_group_effects.csv", index=False)
tests_df.to_csv(TABLES / "17c_size_group_tests.csv", index=False)
log(groups_df.to_string(index=False, float_format=lambda v: f"{v:.5f}"))
log(tests_df.T.to_string())

primary = tests_df[(tests_df.model == "S3_size_groups") & (tests_df.inference == "pair_year")].iloc[0]
secondary = tests_df[(tests_df.model == "S3_size_groups") & (tests_df.inference == "pair")].iloc[0]
(LOGS / "17c_scenario.txt").write_text(
    f"Primary classification (S3, two-way pair + year): scenario {primary['scenario']}\n"
    f"Secondary (S3, pair clusters): scenario {secondary['scenario']}\n"
    f"Robustness (S3b, two-way): scenario {tests_df[(tests_df.model == 'S3b_size_groups_group_year_fe') & (tests_df.inference == 'pair_year')].iloc[0]['scenario']}\n"
    f"median depth among FTA links used for net effects: {median_depth_fta:.2f}\n",
    encoding="utf-8",
)
log((LOGS / "17c_scenario.txt").read_text(encoding="utf-8"))
log("done")

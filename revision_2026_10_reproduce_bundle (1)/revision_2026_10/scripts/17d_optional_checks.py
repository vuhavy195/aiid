"""Step 17d — optional checks approved 2026-10-04.

1. Figure 3 with the true covariance of (GPR x FTA, GPR x Depth) from Table 4
   col (5): net effect, 95% band, zero crossing and the depth beyond which the
   band excludes zero. The zero-covariance band used for the published figure
   is reproduced for comparison.
2. COVID: Table 4 col (5) excluding 2020, and excluding 2020-2021 (singletons
   recomputed on each subsample, as fixest does). The 2020 run is validated
   against the stored leave-one-year-out estimate.
3. Value-weighted survival LPM: Table 4 col (5) weighted by lagged trade value.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r17_common import (  # noqa: E402
    CACHE,
    LOGS,
    PAIR_CLUSTER,
    REPO,
    SURVIVAL_FE,
    SURVIVAL_FILE,
    TABLES,
    FESample,
    Log,
    factorize,
    fit_and_tabulate,
    read_columns,
    singleton_keep,
)

log = Log(LOGS / "17d_optional_checks.log")
X_NAMES = ["gf", "gd", "f", "d", "l"]

# ------------------------------------------------------------- 1. Figure 3 curve
grid = np.round(np.arange(0, 3.8001, 0.001), 3)
curve_rows, threshold_rows = [], []
for scheme in ("pair", "pair_year"):
    npz = np.load(CACHE / f"vcov_joint_size_adjusted_{scheme}.npz")
    beta, V, df = npz["beta"], npz["V"], int(npz["df"])
    names = list(npz["names"])
    i, j = names.index("gf"), names.index("gd")
    crit = stats.t.ppf(0.975, df)
    net = beta[i] + grid * beta[j]
    for cov_label, cov in (("true covariance", V[i, j]), ("zero covariance (published figure)", 0.0)):
        se = np.sqrt(V[i, i] + grid**2 * V[j, j] + 2 * grid * cov)
        low, high = net - crit * se, net + crit * se
        p = 2 * stats.t.sf(np.abs(net / se), df)
        zero_cross = -beta[i] / beta[j]
        above = grid > zero_cross
        beyond = grid[above & (high < 0)]
        beyond_10 = grid[above & (p < 0.10)]
        below = grid[(grid < zero_cross) & (low > 0)]
        threshold_rows.append(
            {
                "inference": scheme,
                "band": cov_label,
                "cov_gf_gd": cov,
                "zero_crossing_provisions": zero_cross * 10,
                "band_excludes_zero_from_provisions": beyond.min() * 10 if beyond.size else np.nan,
                "p_below_0_10_from_provisions": beyond_10.min() * 10 if beyond_10.size else np.nan,
                "band_above_zero_up_to_provisions": below.max() * 10 if below.size else np.nan,
            }
        )
        if cov_label == "true covariance":
            curve_rows.append(
                pd.DataFrame(
                    {
                        "inference": scheme,
                        "depth": grid,
                        "provisions": grid * 10,
                        "net_effect": net,
                        "std_error": se,
                        "ci_low": low,
                        "ci_high": high,
                        "p_value": p,
                    }
                )
            )
    log(f"{scheme}: cov(GPRxFTA, GPRxDepth) = {V[i, j]:.3e}, corr = {V[i, j] / np.sqrt(V[i, i] * V[j, j]):.3f}")
thresholds = pd.DataFrame(threshold_rows)
thresholds.to_csv(TABLES / "17d_figure3_thresholds.csv", index=False)
pd.concat(curve_rows, ignore_index=True).iloc[::10].to_csv(TABLES / "17d_figure3_curve.csv", index=False)
log(thresholds.to_string(index=False, float_format=lambda v: f"{v:.4g}"))

# ------------------------------------------------------------- data for 2 and 3
cols = [
    "survive_t",
    "year",
    "trade_value_l1_musd",
    "log1p_trade_value_l1_musd",
    "fta_active_l1",
    "depth_strict_l1_10",
    "gpr_x_fta_l1",
    "gpr_x_depth_strict_l1_10",
    *SURVIVAL_FE,
    PAIR_CLUSTER,
]
raw = read_columns(SURVIVAL_FILE, cols)


def model5_columns(sel: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "y_survive": raw["survive_t"][sel].astype(np.float64),
        "gf": raw["gpr_x_fta_l1"][sel],
        "gd": raw["gpr_x_depth_strict_l1_10"][sel],
        "f": raw["fta_active_l1"][sel].astype(np.float64),
        "d": raw["depth_strict_l1_10"][sel],
        "l": raw["log1p_trade_value_l1_musd"][sel],
    }


tables = []

# ------------------------------------------------------------- 2. COVID
for tag, drop_years in (("drop2020", [2020]), ("drop2020_2021", [2020, 2021])):
    in_years = ~np.isin(raw["year"], drop_years)
    idx = np.flatnonzero(in_years)
    codes = [factorize(raw[c][idx])[0] for c in SURVIVAL_FE]
    keep_sub = singleton_keep(codes, iterative=False)
    sel = idx[keep_sub]
    log(f"{tag}: n = {sel.size:,}")
    sample = FESample(
        f"survival_{tag}",
        [c[keep_sub] for c in codes],
        raw[PAIR_CLUSTER][sel],
        raw["year"][sel],
        log=log,
    )
    sample.demean(model5_columns(sel))
    _, table, _ = fit_and_tabulate(sample, "y_survive", X_NAMES, f"joint_size_adjusted_{tag}")
    tables.append(table)
    del sample, codes, keep_sub, sel, idx

loyo = pd.read_csv(REPO / "outputs" / "tables" / "step13c_survival_leave_one_year_out.csv")
loyo = loyo[(loyo["excluded_year"] == 2020) & (loyo["term"] == "shock_x_depth")]
ours = tables[0][tables[0]["term"] == "gd"]
for scheme, fixest_label in (("pair", "pair_cluster"), ("pair_year", "pair_plus_year_cluster")):
    a = ours[ours["inference"] == scheme].iloc[0]
    b = loyo[loyo["inference"] == fixest_label].iloc[0]
    log(f"validation vs stored LOYO 2020 [{scheme}]: estimate {a['estimate']:.8f} vs {b['estimate']:.8f}; SE {a['std_error']:.8f} vs {b['std_error']:.8f}; N {a['nobs']:,} vs {b['nobs']:,}")

# ------------------------------------------------------------- 3. value-weighted
keep = np.load(CACHE / "survival_keep_mask.npy")
sel = np.flatnonzero(keep)
weights = raw["trade_value_l1_musd"][sel].astype(np.float64)
exit_t = 1.0 - raw["survive_t"][sel]
log(f"value-weighted exit rate = {np.average(exit_t, weights=weights):.5f}; unweighted = {exit_t.mean():.5f}")
sample_w = FESample(
    "survival_value_weighted",
    [factorize(raw[c][sel])[0] for c in SURVIVAL_FE],
    raw[PAIR_CLUSTER][sel],
    raw["year"][sel],
    weights=weights,
    log=log,
)
sample_w.demean(model5_columns(sel), batch=6)
_, table, _ = fit_and_tabulate(sample_w, "y_survive", X_NAMES, "joint_size_adjusted_value_weighted")
tables.append(table)

out = pd.concat(tables, ignore_index=True)
out.to_csv(TABLES / "17d_covid_and_value_weighted.csv", index=False)
log(out[out["term"].isin(["gf", "gd"])].to_string(index=False, float_format=lambda v: f"{v:.6f}"))
log("done")

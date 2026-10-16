"""Step 17a — replication gate for Table 4, columns (4) and (5).

Re-estimates the size-adjusted depth model and the joint size-adjusted model
of trade-link survival and compares every coefficient and standard error with
outputs/tables/step13b_hs2_survival_all_coefficients.csv (fixest 0.14.2).
Nothing downstream runs unless this gate passes.
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
    REPO,
    SURVIVAL_FE,
    SURVIVAL_FILE,
    TABLES,
    FESample,
    Log,
    factorize,
    fit_and_tabulate,
    gpr_by_year,
    read_columns,
    singleton_keep,
)

TARGET_N = 8_045_131
BETA_TOL = 1e-6  # relative
SE_TOL = 2e-3  # relative; small-sample K conventions differ by < 0.1%

log = Log(LOGS / "17a_replication_gate.log")

columns = [
    "survive_t",
    "year",
    "log1p_trade_value_l1_musd",
    "fta_active_l1",
    "depth_strict_l1_10",
    "gpr_x_fta_l1",
    "gpr_x_depth_strict_l1_10",
    *SURVIVAL_FE,
    PAIR_CLUSTER,
]
data = read_columns(SURVIVAL_FILE, columns)
n_full = data["survive_t"].shape[0]
log("rows read:", f"{n_full:,}")

# GPR level by year, checked against the stored interaction columns.
gpr = gpr_by_year("gpr_mean_z")
lookup = np.full(2100, np.nan)
for year, value in gpr.items():
    lookup[year] = value
g = lookup[data["year"]]
fta = data["fta_active_l1"].astype(np.float64)
depth = data["depth_strict_l1_10"].astype(np.float64)
gap_f = np.max(np.abs(data["gpr_x_fta_l1"] - g * fta))
gap_d = np.max(np.abs(data["gpr_x_depth_strict_l1_10"] - g * depth))
log(f"max |gpr_x_fta - gpr*fta| = {gap_f:.3e}; max |gpr_x_depth - gpr*depth| = {gap_d:.3e}")
if max(gap_f, gap_d) > 1e-6:
    raise SystemExit("GPR reconstruction does not match the stored interactions.")

fe_codes = [factorize(data[c])[0] for c in SURVIVAL_FE]
keep_one = singleton_keep(fe_codes, iterative=False)
keep_iter = singleton_keep(fe_codes, iterative=True)
log(f"kept after one-pass singleton removal: {keep_one.sum():,}; iterative: {keep_iter.sum():,}")
if keep_one.sum() == TARGET_N:
    keep, rule = keep_one, "one-pass"
elif keep_iter.sum() == TARGET_N:
    keep, rule = keep_iter, "iterative"
else:
    raise SystemExit("Neither singleton rule reproduces N = 8,045,131.")
log("singleton rule matching fixest:", rule)
np.save(CACHE / "survival_keep_mask.npy", keep)

sample = FESample(
    "survival_main",
    [codes[keep] for codes in fe_codes],
    data[PAIR_CLUSTER][keep],
    data["year"][keep],
    log=log,
)
log(f"sample n = {sample.n:,}; FE levels = {sample.fe_levels}; pairs = {sample.n_pair:,}; years = {sample.n_year}")

sample.demean(
    {
        "y_survive": data["survive_t"][keep].astype(np.float64),
        "gf": data["gpr_x_fta_l1"][keep],
        "gd": data["gpr_x_depth_strict_l1_10"][keep],
        "f": fta[keep],
        "d": depth[keep],
        "l": data["log1p_trade_value_l1_musd"][keep],
    }
)

models = {
    "depth_size_adjusted": ["gd", "d", "l"],
    "joint_size_adjusted": ["gf", "gd", "f", "d", "l"],
}
tables = []
for model, names in models.items():
    fit, table, vcovs = fit_and_tabulate(sample, "y_survive", names, model)
    tables.append(table)
    for scheme, (V, df, info) in vcovs.items():
        np.savez(
            CACHE / f"vcov_{model}_{scheme}.npz",
            beta=fit["beta"],
            V=V,
            df=df,
            names=np.array(names),
        )
        if info:
            log(f"{model} {scheme}: {info}")
ours = pd.concat(tables, ignore_index=True)

term_map = {
    "gf": "gpr_x_fta_l1",
    "gd": "gpr_x_depth_strict_l1_10",
    "f": "fta_active_l1",
    "d": "depth_strict_l1_10",
    "l": "log1p_trade_value_l1_musd",
}
scheme_map = {"pair": "pair_cluster", "pair_year": "pair_plus_year_cluster"}
ours["term_fixest"] = ours["term"].map(term_map)
ours["inference_fixest"] = ours["inference"].map(scheme_map)

stored = pd.read_csv(REPO / "outputs" / "tables" / "step13b_hs2_survival_all_coefficients.csv")
stored = stored[["model", "inference", "term", "estimate", "std_error", "p_value", "nobs"]].rename(
    columns={
        "inference": "inference_fixest",
        "term": "term_fixest",
        "estimate": "estimate_fixest",
        "std_error": "std_error_fixest",
        "p_value": "p_value_fixest",
        "nobs": "nobs_fixest",
    }
)
merged = ours.merge(stored, on=["model", "inference_fixest", "term_fixest"])
if len(merged) != len(ours):
    raise SystemExit("Could not match every coefficient with the stored fixest output.")
merged["rel_diff_estimate"] = (merged["estimate"] - merged["estimate_fixest"]).abs() / merged["estimate_fixest"].abs()
merged["rel_diff_se"] = (merged["std_error"] - merged["std_error_fixest"]).abs() / merged["std_error_fixest"]
merged["abs_diff_p"] = (merged["p_value"] - merged["p_value_fixest"]).abs()

report_cols = [
    "model",
    "inference",
    "term_fixest",
    "estimate",
    "estimate_fixest",
    "std_error",
    "std_error_fixest",
    "p_value",
    "p_value_fixest",
    "rel_diff_estimate",
    "rel_diff_se",
    "abs_diff_p",
    "nobs",
    "nobs_fixest",
]
merged[report_cols].to_csv(TABLES / "17a_replication_comparison.csv", index=False)

n_ok = bool((merged["nobs"] == merged["nobs_fixest"]).all())
beta_ok = bool((merged["rel_diff_estimate"] < BETA_TOL).all())
se_ok = bool((merged["rel_diff_se"] < SE_TOL).all())
log(merged[report_cols].to_string(index=False, float_format=lambda v: f"{v:.6g}"))
log(f"max rel diff estimate = {merged['rel_diff_estimate'].max():.2e} (tol {BETA_TOL})")
log(f"max rel diff SE       = {merged['rel_diff_se'].max():.2e} (tol {SE_TOL})")
log(f"max abs diff p-value  = {merged['abs_diff_p'].max():.2e}")
status = "PASS" if (n_ok and beta_ok and se_ok) else "FAIL"
(LOGS / "17a_gate_status.txt").write_text(
    f"{status}\nN ok: {n_ok}\nestimates ok: {beta_ok}\nSE ok: {se_ok}\nsingleton rule: {rule}\n",
    encoding="utf-8",
)
log("GATE:", status)
if status != "PASS":
    raise SystemExit(1)

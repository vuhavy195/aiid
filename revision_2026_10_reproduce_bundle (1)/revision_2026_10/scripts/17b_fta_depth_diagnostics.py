"""Step 17b — FTA membership vs DTA depth (advisor item 4; internal check).

1. Correlation and distribution of FTA and depth in the three estimation
   samples (trade value, survival, re-entry) and at the pair-year level.
2. Independent variation: entries into agreements and depth changes within
   existing agreements (pair-year panel).
3. Within-fixed-effect collinearity: correlations and variance-inflation
   factors of the regressors after partialling out the fixed effects (FWL),
   which is the variation the models actually use.
4. Joint-model net effects (FTA + depth x GPR) at representative depths,
   compared with the FTA-only estimates.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r17_common import (  # noqa: E402
    CACHE,
    DTA_PAIR_YEAR_FILE,
    LOGS,
    PAIR_CLUSTER,
    PPML_FILE,
    RECOVERY_FILE,
    REPO,
    SURVIVAL_FE,
    SURVIVAL_FILE,
    TABLES,
    FESample,
    Log,
    factorize,
    gpr_by_year,
    lincom,
    read_columns,
    singleton_keep,
)

log = Log(LOGS / "17b_fta_depth_diagnostics.log")
QUANTILES = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]


def describe(label: str, fta: np.ndarray, depth: np.ndarray, gf: np.ndarray, gd: np.ndarray) -> dict:
    f = fta.astype(np.float64)
    d = depth.astype(np.float64)
    member = f == 1
    dm = d[member]
    row = {
        "sample": label,
        "n": int(f.size),
        "share_fta": f.mean(),
        "share_depth0_among_fta": float((dm == 0).mean()),
        "share_depth_pos_among_nonfta": float((d[~member] > 0).mean()),
        "mean_depth_fta": dm.mean(),
        "sd_depth_fta": dm.std(),
        "corr_fta_depth": np.corrcoef(f, d)[0, 1],
        "corr_gprxfta_gprxdepth": np.corrcoef(gf, gd)[0, 1],
        "share_fta_below_5_4_provisions": float((dm < 0.54).mean()),
        "share_fta_below_19_provisions": float((dm < 1.9).mean()),
        "max_depth_fta": dm.max(),
        "n_distinct_depth_fta": int(np.unique(np.round(dm * 10)).size),
    }
    for q, value in zip(QUANTILES, np.quantile(dm, QUANTILES)):
        row[f"q{int(q * 100):02d}_depth_fta"] = value
    return row


def histogram(label: str, fta: np.ndarray, depth: np.ndarray) -> pd.DataFrame:
    provisions = np.round(depth[fta == 1] * 10).astype(int)
    counts = np.bincount(provisions, minlength=39)
    return pd.DataFrame(
        {
            "sample": label,
            "provisions": np.arange(counts.size),
            "n": counts,
            "share": counts / counts.sum(),
        }
    )


def collinearity(sample: FESample, raw: dict[str, np.ndarray], label: str, weighting: str) -> list[dict]:
    """Within-FE correlation matrix and VIFs from the demeaned columns."""
    names = list(raw)
    sample.demean(raw)
    X = sample.load(names)
    w = sample.weights
    gram = (X * w[:, None]).T @ X if sample.weighted else X.T @ X
    scale = np.sqrt(np.diag(gram))
    corr = gram / np.outer(scale, scale)
    vif = np.diag(np.linalg.inv(corr))
    out = []
    for i, name in enumerate(names):
        r = raw[name].astype(np.float64)
        if sample.weighted:
            mean = np.average(r, weights=w)
            var_raw = np.average((r - mean) ** 2, weights=w)
            var_within = np.average(X[:, i] ** 2, weights=w)
        else:
            var_raw = r.var()
            var_within = (X[:, i] ** 2).mean()
        row = {
            "sample": label,
            "weighting": weighting,
            "variable": name,
            "share_variance_left_after_fe": var_within / var_raw,
            "vif_joint_model": vif[i],
        }
        for j, other in enumerate(names):
            row[f"within_corr_{other}"] = corr[i, j]
        out.append(row)
    pair_idx = [names.index("gprxfta"), names.index("gprxdepth")]
    sub = corr[np.ix_(pair_idx, pair_idx)]
    log(f"{label} [{weighting}] within-FE corr(GPRxFTA, GPRxDepth) = {sub[0, 1]:.3f}; VIFs = "
        + ", ".join(f"{n}={v:.1f}" for n, v in zip(names, vif)))
    del X
    return out


descriptives, histograms, collin = [], [], []

# ---------------------------------------------------------------- survival
log("== survival sample")
cols = ["fta_active_l1", "depth_strict_l1_10", "gpr_x_fta_l1", "gpr_x_depth_strict_l1_10", "log1p_trade_value_l1_musd"]
sv = read_columns(SURVIVAL_FILE, cols)
keep = np.load(CACHE / "survival_keep_mask.npy")
sv = {k: v[keep] for k, v in sv.items()}
descriptives.append(describe("survival (N = 8,045,131)", sv["fta_active_l1"], sv["depth_strict_l1_10"], sv["gpr_x_fta_l1"], sv["gpr_x_depth_strict_l1_10"]))
histograms.append(histogram("survival", sv["fta_active_l1"], sv["depth_strict_l1_10"]))
surv_fta_quantiles = np.quantile(sv["depth_strict_l1_10"][sv["fta_active_l1"] == 1], [0.10, 0.25, 0.50, 0.75, 0.90])

# demeaned columns already cached by 17a under the same names
fe_sv = read_columns(SURVIVAL_FILE, SURVIVAL_FE + [PAIR_CLUSTER, "year"])
survival_sample = FESample(
    "survival_main",
    [factorize(fe_sv[c][keep])[0] for c in SURVIVAL_FE],
    fe_sv[PAIR_CLUSTER][keep],
    fe_sv["year"][keep],
    log=log,
)
alias = {"gprxfta": "gf", "gprxdepth": "gd", "fta": "f", "depth": "d", "lagged_size": "l"}
raw_sv = {
    "gprxfta": sv["gpr_x_fta_l1"],
    "gprxdepth": sv["gpr_x_depth_strict_l1_10"],
    "fta": sv["fta_active_l1"].astype(np.float64),
    "depth": sv["depth_strict_l1_10"],
    "lagged_size": sv["log1p_trade_value_l1_musd"],
}
# point the new names at the cached files written by 17a
for new, old in alias.items():
    src, dst = survival_sample._path(old), survival_sample._path(new)
    if src.exists() and not dst.exists():
        dst.hardlink_to(src)
collin += collinearity(survival_sample, raw_sv, "survival", "unweighted (as estimated)")
del fe_sv, raw_sv

# ---------------------------------------------------------------- PPML
log("== trade-value (PPML) panel")
pp_cols = ["fta_active_l1", "depth_strict_l1_10", "gpr_x_fta_l1", "gpr_x_depth_strict_l1_10", "trade_value_musd", PAIR_CLUSTER, "year"] + SURVIVAL_FE
pp = read_columns(PPML_FILE, pp_cols)
descriptives.append(describe("trade value (panel N = 16,752,461)", pp["fta_active_l1"], pp["depth_strict_l1_10"], pp["gpr_x_fta_l1"], pp["gpr_x_depth_strict_l1_10"]))
histograms.append(histogram("trade value", pp["fta_active_l1"], pp["depth_strict_l1_10"]))
ppml_fta_quantiles = np.quantile(pp["depth_strict_l1_10"][pp["fta_active_l1"] == 1], [0.10, 0.25, 0.50, 0.75, 0.90])

pp_codes = [factorize(pp[c])[0] for c in SURVIVAL_FE]
pp_keep = singleton_keep(pp_codes, iterative=False)
log(f"PPML panel after one-pass singleton removal: {pp_keep.sum():,} (published N 16,752,356)")
raw_pp = {
    "gprxfta": pp["gpr_x_fta_l1"][pp_keep],
    "gprxdepth": pp["gpr_x_depth_strict_l1_10"][pp_keep],
    "fta": pp["fta_active_l1"][pp_keep].astype(np.float64),
    "depth": pp["depth_strict_l1_10"][pp_keep],
}
pp_codes_kept = [c[pp_keep] for c in pp_codes]
ppml_sample = FESample("ppml_unweighted", pp_codes_kept, pp[PAIR_CLUSTER][pp_keep], pp["year"][pp_keep], log=log)
collin += collinearity(ppml_sample, raw_pp, "trade value", "unweighted")
del ppml_sample

# PPML weights observations by their expected value, so most of its weight sits
# on large relationships. A weighted demeaning on 16.75M rows exceeds this
# machine's memory; instead the check is repeated, unweighted, on pair-HS2
# groups whose average trade is at least USD 1 million (internal approximation).
value = pp["trade_value_musd"][pp_keep]
pair_col = pp[PAIR_CLUSTER][pp_keep]
year_col = pp["year"][pp_keep]
del pp, pp_codes
grp = pp_codes_kept[0]
group_mean = np.bincount(grp, weights=value) / np.bincount(grp)
large = group_mean[grp] >= 1.0
log(f"large pair-HS2 groups (mean >= USD 1m): {large.mean():.1%} of rows, {value[large].sum() / value.sum():.1%} of trade value")
large_codes = [c[large] for c in pp_codes_kept]
large_keep = singleton_keep(large_codes, iterative=False)
large_sample = FESample(
    "ppml_large_groups",
    [c[large_keep] for c in large_codes],
    pair_col[large][large_keep],
    year_col[large][large_keep],
    log=log,
)
collin += collinearity(
    large_sample,
    {name: arr[large][large_keep] for name, arr in raw_pp.items()},
    "trade value, groups with mean >= USD 1m",
    "unweighted",
)
del large_sample, large_codes, pp_codes_kept, raw_pp, value, grp, pair_col, year_col

# ---------------------------------------------------------------- re-entry
log("== post-exit re-entry panel")
rc_fe = ["pair_hs2_fe_id", "exporter_exit_year_fe_id", "importer_exit_year_fe_id", "hs2_exit_year_fe_id"]
rc = read_columns(
    RECOVERY_FILE,
    ["fta_active_l1", "depth_strict_l1_10", "gpr_x_fta_l1", "gpr_x_depth_strict_l1_10", "log1p_pre_exit_trade_musd", "reentry_1y_available", "exit_year", PAIR_CLUSTER] + rc_fe,
)
avail = rc["reentry_1y_available"] == 1
rc = {k: v[avail] for k, v in rc.items()}
descriptives.append(describe("re-entry, one-year window (N = 1,152,080)", rc["fta_active_l1"], rc["depth_strict_l1_10"], rc["gpr_x_fta_l1"], rc["gpr_x_depth_strict_l1_10"]))
histograms.append(histogram("re-entry", rc["fta_active_l1"], rc["depth_strict_l1_10"]))
rc_codes = [factorize(rc[c])[0] for c in rc_fe]
rc_keep = singleton_keep(rc_codes, iterative=False)
log(f"re-entry (pair-HS2 FE) after one-pass singleton removal: {rc_keep.sum():,} (published N 839,585)")
rc_sample = FESample("reentry_pairhs2", [c[rc_keep] for c in rc_codes], rc[PAIR_CLUSTER][rc_keep], rc["exit_year"][rc_keep], log=log)
collin += collinearity(
    rc_sample,
    {
        "gprxfta": rc["gpr_x_fta_l1"][rc_keep],
        "gprxdepth": rc["gpr_x_depth_strict_l1_10"][rc_keep],
        "fta": rc["fta_active_l1"][rc_keep].astype(np.float64),
        "depth": rc["depth_strict_l1_10"][rc_keep],
        "lagged_size": rc["log1p_pre_exit_trade_musd"][rc_keep],
    },
    "re-entry (pair-HS2 FE)",
    "unweighted (as estimated)",
)
del rc, rc_sample

# ---------------------------------------------------------------- pair-year
log("== pair-year agreement panel")
py = pd.read_parquet(
    DTA_PAIR_YEAR_FILE,
    columns=["unordered_pair_id", "year", "fta_active_l1", "depth_strict_l1"],
).drop_duplicates(["unordered_pair_id", "year"])
py["depth10"] = py["depth_strict_l1"] / 10
py = py.dropna(subset=["fta_active_l1", "depth10"]).sort_values(["unordered_pair_id", "year"])
log(f"pair-year depth10 range: {py['depth10'].min():.2f}-{py['depth10'].max():.2f} (expected 0-3.8)")
if not 3.0 <= py["depth10"].max() <= 4.0:
    raise SystemExit("depth_strict_l1 is not on the expected count scale.")
gpr_year = py["year"].map(gpr_by_year("gpr_mean_z")).to_numpy()
descriptives.append(
    describe(
        "unordered pair-years (unweighted)",
        py["fta_active_l1"].to_numpy(),
        py["depth10"].to_numpy(),
        gpr_year * py["fta_active_l1"].to_numpy(),
        gpr_year * py["depth10"].to_numpy(),
    )
)
histograms.append(histogram("pair-years", py["fta_active_l1"].to_numpy(), py["depth10"].to_numpy()))
grouped = py.groupby("unordered_pair_id")
lag_f = grouped["fta_active_l1"].shift()
lag_d = grouped["depth10"].shift()
both_member = (py["fta_active_l1"] == 1) & (lag_f == 1)
depth_change = both_member & (py["depth10"] != lag_d)
per_pair = pd.DataFrame(
    {
        "ever_fta": grouped["fta_active_l1"].max(),
        "always_fta": grouped["fta_active_l1"].min(),
        "entered": grouped["fta_active_l1"].apply(lambda s: bool(((s.diff() == 1)).any())),
        "left": grouped["fta_active_l1"].apply(lambda s: bool(((s.diff() == -1)).any())),
    }
)
per_pair["depth_changed_within_fta"] = depth_change.groupby(py["unordered_pair_id"]).any()
member_years = py[py["fta_active_l1"] == 1]
between_sd = member_years.groupby("unordered_pair_id")["depth10"].mean().std()
within_sd = (member_years["depth10"] - member_years.groupby("unordered_pair_id")["depth10"].transform("mean")).std()
variation = pd.DataFrame(
    [
        {"statistic": "unordered pairs", "value": len(per_pair)},
        {"statistic": "pairs with an agreement in force in some year (t-1 status)", "value": int(per_pair["ever_fta"].sum())},
        {"statistic": "pairs with an agreement in force in every year", "value": int(per_pair["always_fta"].sum())},
        {"statistic": "pairs entering an agreement during 2007-2023", "value": int(per_pair["entered"].sum())},
        {"statistic": "pairs leaving an agreement during 2007-2023", "value": int(per_pair["left"].sum())},
        {"statistic": "pairs whose depth changed while an agreement stayed in force", "value": int(per_pair["depth_changed_within_fta"].sum())},
        {"statistic": "member pair-years with a depth change vs previous year", "value": int(depth_change.sum())},
        {"statistic": "member pair-years", "value": int((py["fta_active_l1"] == 1).sum())},
        {"statistic": "between-pair SD of depth among members (/10)", "value": float(between_sd)},
        {"statistic": "within-pair SD of depth among members (/10)", "value": float(within_sd)},
    ]
)
log(variation.to_string(index=False))

# ---------------------------------------------------------------- joint effects
log("== joint-model net effects at representative depths")
stored_sv = pd.read_csv(REPO / "outputs" / "tables" / "step13b_hs2_survival_all_coefficients.csv")
fta_only_sv = stored_sv[(stored_sv["model"] == "fta_size_adjusted") & (stored_sv["term"] == "gpr_x_fta_l1")]
stored_pp = pd.read_csv(REPO / "outputs" / "tables" / "step10b_hs2_core_coefficients.csv")
fta_only_pp = stored_pp[(stored_pp["model"] == "hs2_fta") & (stored_pp["term"] == "gpr_x_fta_l1")]
joint_pp = pd.read_csv(REPO / "outputs" / "tables" / "step10c_hs2_robustness_coefficients.csv")
joint_pp = joint_pp[joint_pp["model"] == "joint_fta_depth"].drop_duplicates("term").set_index("term")["estimate"]
b1_pp, b2_pp = joint_pp["gpr_x_fta_l1"], joint_pp["gpr_x_depth_strict_l1_10"]

rows = []
labels = ["p10", "p25", "p50", "p75", "p90"]
for scheme in ("pair", "pair_year"):
    npz = np.load(CACHE / f"vcov_joint_size_adjusted_{scheme}.npz")
    beta, V, df = npz["beta"], npz["V"], int(npz["df"])
    names = list(npz["names"])
    ref = fta_only_sv[fta_only_sv["inference"] == ("pair_cluster" if scheme == "pair" else "pair_plus_year_cluster")].iloc[0]
    points = list(zip(labels, surv_fta_quantiles)) + [("zero crossing 5.4", 0.54), ("10 provisions", 1.0), ("19 provisions", 1.9)]
    for label, depth_value in points:
        c = np.zeros(len(beta))
        c[names.index("gf")] = 1.0
        c[names.index("gd")] = depth_value
        res = lincom(beta, V, c, df)
        rows.append({"model": "survival LPM (Table 4 col 5)", "inference": scheme, "depth_point": label, "depth_value": depth_value, "provisions": depth_value * 10, **res, "fta_only_estimate": ref["estimate"], "fta_only_se": ref["std_error"]})
for label, depth_value in zip(labels, ppml_fta_quantiles):
    rows.append({"model": "trade value PPML (Table 3 col 3)", "inference": "point estimate only (covariance not stored)", "depth_point": label, "depth_value": depth_value, "provisions": depth_value * 10, "estimate": b1_pp + depth_value * b2_pp, "fta_only_estimate": fta_only_pp["estimate"].iloc[0], "fta_only_se": fta_only_pp["std_error"].iloc[0]})
joint = pd.DataFrame(rows)
log(joint[["model", "inference", "depth_point", "provisions", "estimate", "std_error", "p_value", "fta_only_estimate"]].to_string(index=False, float_format=lambda v: f"{v:.5f}"))

# ---------------------------------------------------------------- save
desc = pd.DataFrame(descriptives)
log(desc.T.to_string(float_format=lambda v: f"{v:.4f}"))
desc.to_csv(TABLES / "17b_fta_depth_descriptives.csv", index=False)
pd.concat(histograms, ignore_index=True).to_csv(TABLES / "17b_depth_histogram_members.csv", index=False)
variation.to_csv(TABLES / "17b_pair_year_variation.csv", index=False)
pd.DataFrame(collin).to_csv(TABLES / "17b_within_fe_collinearity.csv", index=False)
joint.to_csv(TABLES / "17b_joint_effects_at_depth.csv", index=False)
log("done")

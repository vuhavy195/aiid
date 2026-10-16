"""Step 17f — post-hoc: does the restricted-sample (44 economies) evidence depend on intra-EU pairs?

NOT pre-registered. Step 17c2 found that Table 4 col (5) loses its depth x GPR
survival effect once intra-EU pairs are excluded. This step repeats that check
for Table 7 (country-specific GPR), on both margins:

  Panel B (survival LPM): restricted-sample global GPR and average pair GPR,
      replicated first, then re-estimated without intra-EU pairs.
  Panel A (trade value PPML, 2.52M rows): the same two shock measures with
      pyfixest's fepois, replicated against the stored fixest estimates first;
      the no-EU re-estimation runs only if replication passes.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r17_common import (  # noqa: E402
    LOGS,
    PAIR_CLUSTER,
    REPO,
    SURVIVAL_FE,
    TABLES,
    FESample,
    Log,
    factorize,
    fit_and_tabulate,
    read_columns,
    singleton_keep,
)

log = Log(LOGS / "17f_eu_checks.log")
SURV_FILE = REPO / "data" / "processed" / "estimation_hs2_survival_country_gpr.parquet"
PPML_FILE = REPO / "data" / "processed" / "estimation_hs2_ppml_country_gpr.parquet"
stored = pd.read_csv(REPO / "outputs" / "tables" / "step15c_country_gpr_coefficients.csv")

countries = pd.read_csv(REPO / "data" / "processed" / "country_sample_160.csv")
rank_to_iso = dict(zip(countries["final_sample_rank"].astype(int), countries["country_iso3"]))
iso_by_rank = np.array([rank_to_iso.get(r, "") for r in range(161)], dtype=object)
EU_CORE = sorted({
    "AUT", "BEL", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA",
    "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "SVK", "SVN", "ESP", "SWE", "BGR", "ROU",
})
core_rank = np.isin(iso_by_rank, EU_CORE)
hrv_rank = iso_by_rank == "HRV"
gbr_rank = iso_by_rank == "GBR"


def intra_eu_flag(pair_hs2_fe_id: np.ndarray, year: np.ndarray, cluster: np.ndarray) -> np.ndarray:
    pair_index = pair_hs2_fe_id // 100
    er = pair_index // 160 + 1
    ir = pair_index % 160 + 1
    check = (np.minimum(er, ir) - 1) * 160 + (np.maximum(er, ir) - 1)
    if not np.array_equal(check, cluster):
        raise SystemExit("pair_hs2_fe_id does not decode to the stored pair cluster id.")
    s = year - 1

    def member(r):
        return core_rank[r] | (hrv_rank[r] & (s >= 2013)) | (gbr_rank[r] & (s <= 2020))

    return member(er) & member(ir)


SHOCKS = {
    "restricted_global_gpr": ("gpr_x_fta_l1", "gpr_x_depth_strict_l1_10", None),
    "pair_average_country_gpr": ("pair_avg_gpr_x_fta_l1", "pair_avg_gpr_x_depth_l1_10", "pair_country_gpr_average_z"),
}
rows = []

# --------------------------------------------------------------------- survival
log("== Panel B: survival LPM")
cols = ["survive_t", "year", "log1p_trade_value_l1_musd", "fta_active_l1", "depth_strict_l1_10",
        "gpr_x_fta_l1", "gpr_x_depth_strict_l1_10", "pair_country_gpr_average_z",
        "pair_avg_gpr_x_fta_l1", "pair_avg_gpr_x_depth_l1_10", *SURVIVAL_FE, PAIR_CLUSTER]
sv = read_columns(SURV_FILE, cols)
eu = intra_eu_flag(sv["pair_hs2_fe_id"], sv["year"], sv[PAIR_CLUSTER])
log(f"restricted survival panel: {eu.size:,} rows, intra-EU share {eu.mean():.1%}")

for sample_label, mask in (("all 44 economies", np.ones(eu.size, dtype=bool)), ("excluding intra-EU", ~eu)):
    idx = np.flatnonzero(mask)
    codes = [factorize(sv[c][idx])[0] for c in SURVIVAL_FE]
    keep = singleton_keep(codes, iterative=False)
    sel = idx[keep]
    tag = "country_surv_all" if sample_label.startswith("all") else "country_surv_noeu"
    sample = FESample(tag, [c[keep] for c in codes], sv[PAIR_CLUSTER][sel], sv["year"][sel], log=log)
    log(f"{sample_label}: n = {sel.size:,}")
    base = {
        "y_survive": sv["survive_t"][sel].astype(np.float64),
        "l": sv["log1p_trade_value_l1_musd"][sel].astype(np.float64),
        "f": sv["fta_active_l1"][sel].astype(np.float64),
        "d": sv["depth_strict_l1_10"][sel].astype(np.float64),
    }
    for shock, (fta_col, depth_col, main_col) in SHOCKS.items():
        base[f"{shock}_xf"] = sv[fta_col][sel]
        base[f"{shock}_xd"] = sv[depth_col][sel]
        if main_col:
            base[f"{shock}_main"] = sv[main_col][sel]
    sample.demean(base)
    for shock, (_, _, main_col) in SHOCKS.items():
        names = ["l", "f", "d", f"{shock}_xf", f"{shock}_xd"]
        if main_col:
            dm = np.load(sample._path(f"{shock}_main"))
            if dm.var() > 1e-12 * max(1.0, base[f"{shock}_main"].var()):
                names.append(f"{shock}_main")
            else:
                log(f"  {shock}: level term absorbed by the fixed effects (dropped, as fixest does)")
        _, table, _ = fit_and_tabulate(sample, "y_survive", names, f"survival {shock} [{sample_label}]")
        for _, r in table[table["term"].isin([f"{shock}_xf", f"{shock}_xd"])].iterrows():
            rows.append({"margin": "survival (LPM)", "shock": shock, "sample": sample_label, "inference": r["inference"],
                         "term": "shock_x_fta" if r["term"].endswith("_xf") else "shock_x_depth",
                         "estimate": r["estimate"], "std_error": r["std_error"], "p_value": r["p_value"], "nobs": r["nobs"]})
    del sample
del sv

# --------------------------------------------------------------------- trade value (PPML)
log("== Panel A: trade value PPML (pyfixest fepois)")
try:
    import pyfixest as pf

    pcols = ["trade_value_musd", "year", "fta_active_l1", "depth_strict_l1_10", "gpr_x_fta_l1",
             "gpr_x_depth_strict_l1_10", "pair_avg_gpr_x_fta_l1", "pair_avg_gpr_x_depth_l1_10",
             *SURVIVAL_FE, PAIR_CLUSTER]
    pp = pd.read_parquet(PPML_FILE, columns=pcols)
    pp["fta_active_l1"] = pp["fta_active_l1"].astype(np.float64)
    pp["intra_eu"] = intra_eu_flag(pp["pair_hs2_fe_id"].to_numpy(), pp["year"].to_numpy(), pp[PAIR_CLUSTER].to_numpy())
    log(f"restricted trade panel: {len(pp):,} rows, intra-EU share {pp['intra_eu'].mean():.1%}")
    gate_ok = True
    for sample_label, frame in (("all 44 economies", pp), ("excluding intra-EU", pp[~pp["intra_eu"]])):
        if sample_label != "all 44 economies" and not gate_ok:
            log("PPML replication gate failed; no-EU PPML not run.")
            break
        for shock, (fta_col, depth_col, _) in SHOCKS.items():
            fml = (f"trade_value_musd ~ fta_active_l1 + depth_strict_l1_10 + {fta_col} + {depth_col}"
                   " | pair_hs2_fe_id + exporter_year_fe_id + importer_year_fe_id + hs2_year_fe_id")
            for scheme, vcov in (("pair", {"CRV1": PAIR_CLUSTER}), ("pair_year", {"CRV1": f"{PAIR_CLUSTER}+year"})):
                fit = pf.fepois(fml, data=frame, vcov=vcov, fixef_rm="none", iwls_tol=1e-10, iwls_maxiter=100,
                                copy_data=False, store_data=False, lean=True)
                tidy = fit.tidy()
                for term, label in ((fta_col, "shock_x_fta"), (depth_col, "shock_x_depth")):
                    est, se = float(tidy.loc[term, "Estimate"]), float(tidy.loc[term, "Std. Error"])
                    p = float(2 * stats.norm.sf(abs(est / se)))
                    rows.append({"margin": "trade value (PPML)", "shock": shock, "sample": sample_label, "inference": scheme,
                                 "term": label, "estimate": est, "std_error": se, "p_value": p, "nobs": int(fit._N)})
                    if sample_label == "all 44 economies":
                        ref = stored[(stored["model"] == f"trade_{shock}") & (stored["term"] == label)
                                     & (stored["inference"] == ("pair_cluster" if scheme == "pair" else "pair_plus_year_cluster"))].iloc[0]
                        rel_b = abs(est - ref["estimate"]) / abs(ref["estimate"])
                        rel_se = abs(se - ref["std_error"]) / ref["std_error"]
                        log(f"  gate {shock} {label} {scheme}: est {est:.6f} vs {ref['estimate']:.6f} (rel {rel_b:.1e}); SE {se:.6f} vs {ref['std_error']:.6f} (rel {rel_se:.1e})")
                        if rel_b > 1e-4 or rel_se > 2e-2:
                            gate_ok = False
                del fit
except MemoryError:
    log("PPML skipped: out of memory")

out = pd.DataFrame(rows)
out.to_csv(TABLES / "17f_eu_checks.csv", index=False)
log(out.to_string(index=False, float_format=lambda v: f"{v:.6f}"))

# survival replication check against stored fixest output
for shock in SHOCKS:
    for label in ("shock_x_fta", "shock_x_depth"):
        for scheme, fixest_label in (("pair", "pair_cluster"), ("pair_year", "pair_plus_year_cluster")):
            ours = out[(out["margin"] == "survival (LPM)") & (out["shock"] == shock) & (out["sample"] == "all 44 economies")
                       & (out["term"] == label) & (out["inference"] == scheme)].iloc[0]
            ref = stored[(stored["model"] == f"survival_{shock}") & (stored["term"] == label) & (stored["inference"] == fixest_label)].iloc[0]
            log(f"survival gate {shock} {label} {scheme}: est {ours['estimate']:.6f} vs {ref['estimate']:.6f}; "
                f"SE {ours['std_error']:.6f} vs {ref['std_error']:.6f}; N {ours['nobs']:,} vs {int(ref['nobs']):,}")
log("done")

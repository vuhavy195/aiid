"""Step 17c3 — post-hoc: formal EU test on the full survival sample.

NOT pre-registered. Table 4 col (5) plus an intra-EU x GPR term (and the
intra-EU level, which moves only with Croatia's accession and Brexit). Inside
the EU, FTA = 1 and depth is almost constant, so EU-specific depth slopes are
not separately identified; the question is how much of GPR x Depth an
EU-specific response to GPR absorbs.
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
)

log = Log(LOGS / "17c3_eu_interaction.log")
raw = read_columns(SURVIVAL_FILE, ["year", *SURVIVAL_FE, PAIR_CLUSTER])
keep = np.load(CACHE / "survival_keep_mask.npy")
raw = {k: v[keep] for k, v in raw.items()}

countries = pd.read_csv(REPO / "data" / "processed" / "country_sample_160.csv")
rank_to_iso = dict(zip(countries["final_sample_rank"].astype(int), countries["country_iso3"]))
iso_by_rank = np.array([rank_to_iso.get(r, "") for r in range(161)], dtype=object)
EU_CORE = sorted({
    "AUT", "BEL", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA",
    "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "SVK", "SVN", "ESP", "SWE", "BGR", "ROU",
})
core, hrv, gbr = np.isin(iso_by_rank, EU_CORE), iso_by_rank == "HRV", iso_by_rank == "GBR"
pair_index = raw["pair_hs2_fe_id"] // 100
er, ir = pair_index // 160 + 1, pair_index % 160 + 1
s = raw["year"] - 1


def member(r):
    return core[r] | (hrv[r] & (s >= 2013)) | (gbr[r] & (s <= 2020))


eu = (member(er) & member(ir)).astype(np.float64)
lookup = np.full(2100, np.nan)
for year, value in gpr_by_year("gpr_mean_z").items():
    lookup[year] = value
G = lookup[raw["year"]]
log(f"intra-EU share of the estimation sample: {eu.mean():.1%}")

sample = FESample("survival_main", [factorize(raw[c])[0] for c in SURVIVAL_FE], raw[PAIR_CLUSTER], raw["year"], log=log)
sample.demean({"g_eu": G * eu, "eu": eu})
eu_var = np.load(sample._path("eu")).var()
names = ["gf", "gd", "f", "d", "l", "g_eu"] + (["eu"] if eu_var > 1e-12 else [])
log(f"within-FE variance of the intra-EU level: {eu_var:.2e} ({'kept' if 'eu' in names else 'absorbed'})")
_, table, _ = fit_and_tabulate(sample, "y_survive", names, "Table 4 col 5 + GPR x intra-EU")
table.to_csv(TABLES / "17c3_eu_interaction.csv", index=False)
log(table.to_string(index=False, float_format=lambda v: f"{v:.6f}"))
log("done")

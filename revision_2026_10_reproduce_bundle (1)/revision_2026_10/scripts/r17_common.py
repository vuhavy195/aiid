"""Shared helpers for the 2026-10 revision analyses (AIID DTA-GPR project).

Estimation strategy: Frisch-Waugh-Lovell. Every variable is demeaned once on the
full fixed-effect set with pyfixest's alternating-projections demeaner; OLS on
the demeaned columns then reproduces the fixed-effects estimates. Demeaned
columns are cached on disk so that every specification sharing a sample and a
fixed-effect set reuses them.

Inference follows fixest's defaults (ssc: adj = TRUE, fixef.K = "nested",
cluster.adj = TRUE, cluster.df = "min", t.df = "min"):
  one-way:  V = (n-1)/(n-K) * G/(G-1) * B M B, t with G-1 df
  two-way:  V = (n-1)/(n-K) * Gmin/(Gmin-1) * B (M_a + M_b - M_ab) B,
            t with Gmin-1 df, negative eigenvalues set to zero if any.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pyfixest.estimation import demean as pf_demean
from scipy import stats

REPO = Path(__file__).resolve().parents[2]
REV = REPO / "revision_2026_10"
TABLES = REV / "tables"
FIGURES = REV / "figures"
LOGS = REV / "logs"
CACHE = REV / "cache"

SURVIVAL_FILE = REPO / "data" / "processed" / "estimation_hs2_trade_link_survival.parquet"
PPML_FILE = REPO / "data" / "processed" / "estimation_hs2_ppml_compact.parquet"
RECOVERY_FILE = REPO / "data" / "processed" / "estimation_hs2_post_exit_recovery.parquet"
GPR_FILE = REPO / "data" / "processed" / "gpr_annual_core_2007_2023.parquet"
DTA_PAIR_YEAR_FILE = REPO / "data" / "processed" / "dta_pair_year_core_160.parquet"

SURVIVAL_FE = [
    "pair_hs2_fe_id",
    "exporter_year_fe_id",
    "importer_year_fe_id",
    "hs2_year_fe_id",
]
PAIR_CLUSTER = "unordered_pair_cluster_id"

# Lagged-size groups, USD million thresholds: <10k, 10k-100k, 100k-1M, >=1M.
SIZE_BREAKS_MUSD = (0.01, 0.1, 1.0)
SIZE_LABELS = ("<10k", "10k-100k", "100k-1M", ">=1M")

DEMEAN_TOL = 1e-10
DEMEAN_MAXITER = 100_000


class Log:
    """Print and append to a log file."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")
        self.t0 = time.time()

    def __call__(self, *parts) -> None:
        line = " ".join(str(p) for p in parts)
        stamp = f"[{time.time() - self.t0:8.1f}s] "
        print(stamp + line, flush=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(stamp + line + "\n")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def read_columns(path: Path, columns: list[str]) -> dict[str, np.ndarray]:
    table = pq.read_table(path, columns=columns)
    return {name: table.column(name).to_numpy() for name in columns}


def gpr_by_year(column: str = "gpr_mean_z") -> dict[int, float]:
    frame = pq.read_table(GPR_FILE, columns=["year", column]).to_pandas()
    return dict(zip(frame["year"].astype(int), frame[column].astype(float)))


def factorize(values: np.ndarray) -> tuple[np.ndarray, int]:
    codes, uniques = pd.factorize(values, sort=False)
    return codes.astype(np.int64), len(uniques)


def singleton_keep(fe_codes: list[np.ndarray], iterative: bool = False) -> np.ndarray:
    """Rows to keep after dropping fixed-effect singletons.

    fixest removes singletons in a single pass (no recursion); iterative=True
    repeats until no singleton is left, for comparison.
    """
    keep = np.ones(fe_codes[0].shape[0], dtype=bool)
    while True:
        drop = np.zeros_like(keep)
        for codes in fe_codes:
            counts = np.bincount(codes[keep])
            drop[keep] |= counts[codes[keep]] == 1
        if not drop.any():
            return keep
        keep &= ~drop
        if not iterative:
            return keep


def size_group(trade_value_l1_musd: np.ndarray) -> np.ndarray:
    """0..3 for <10k, 10k-100k, 100k-1M, >=1M (USD)."""
    return np.digitize(trade_value_l1_musd, SIZE_BREAKS_MUSD).astype(np.int8)


# ---------------------------------------------------------------------------
# Fixed-effect sample with cached demeaned columns
# ---------------------------------------------------------------------------
class FESample:
    """A fixed estimation sample, its fixed effects and cluster identifiers.

    Columns are demeaned in batches and cached as .npy files under
    cache/<tag>/, so later scripts reuse them.
    """

    def __init__(
        self,
        tag: str,
        fe_codes: list[np.ndarray],
        pair: np.ndarray,
        year: np.ndarray,
        weights: np.ndarray | None = None,
        log: Log | None = None,
    ):
        self.tag = tag
        self.log = log or print
        self.n = fe_codes[0].shape[0]
        refactored = [factorize(codes) for codes in fe_codes]
        self.fe_levels = [levels for _, levels in refactored]
        self.flist = np.ascontiguousarray(
            np.column_stack([codes for codes, _ in refactored]).astype(np.uint64)
        )
        self.pair, self.n_pair = factorize(pair)
        self.year, self.n_year = factorize(year)
        self.pairyear, self.n_pairyear = factorize(self.pair * 1000 + self.year)
        self.weights = (
            np.ones(self.n, dtype=np.float64)
            if weights is None
            else np.ascontiguousarray(weights, dtype=np.float64)
        )
        self.weighted = weights is not None
        self.dir = CACHE / tag
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.dir / f"{name}.npy"

    def demean(self, columns: dict[str, np.ndarray], batch: int = 6) -> None:
        """Demean and cache any column not yet cached."""
        todo = [name for name in columns if not self._path(name).exists()]
        for start in range(0, len(todo), batch):
            names = todo[start : start + batch]
            block = np.ascontiguousarray(
                np.column_stack([columns[name] for name in names]).astype(np.float64)
            )
            t0 = time.time()
            result, converged = pf_demean(
                block, self.flist, self.weights, tol=DEMEAN_TOL, maxiter=DEMEAN_MAXITER
            )
            if not converged:
                raise RuntimeError(f"Demeaning did not converge for {names}")
            for j, name in enumerate(names):
                np.save(self._path(name), np.ascontiguousarray(result[:, j]))
            self.log(f"  demeaned {names} in {time.time() - t0:.1f}s ({self.tag})")
            del block, result

    def load(self, names: list[str]) -> np.ndarray:
        return np.column_stack([np.load(self._path(name)) for name in names])


# ---------------------------------------------------------------------------
# Estimation and inference
# ---------------------------------------------------------------------------
def ols_fit(sample: FESample, y_name: str, x_names: list[str]) -> dict:
    y = np.load(sample._path(y_name))
    X = sample.load(x_names)
    w = sample.weights
    Xw = X * w[:, None] if sample.weighted else X
    xtx = Xw.T @ X
    xty = Xw.T @ y
    beta = np.linalg.solve(xtx, xty)
    resid = y - X @ beta
    bread = np.linalg.inv(xtx)
    return {
        "names": list(x_names),
        "beta": beta,
        "resid": resid,
        "bread": bread,
        "X": X,
        "n": sample.n,
        "k": len(x_names),
        "sample": sample,
    }


def _meat(X: np.ndarray, score_weight: np.ndarray, codes: np.ndarray, n_groups: int) -> np.ndarray:
    k = X.shape[1]
    sums = np.empty((n_groups, k))
    for j in range(k):
        sums[:, j] = np.bincount(codes, weights=X[:, j] * score_weight, minlength=n_groups)
    return sums.T @ sums


def _k_fixed_effects_not_nested(sample: FESample, nested_dims: list[int]) -> int:
    levels = [lv for d, lv in enumerate(sample.fe_levels) if d not in nested_dims]
    if not levels:
        return 0
    return int(sum(levels) - (len(levels) - 1))


def cluster_vcov(fit: dict, scheme: str) -> tuple[np.ndarray, int, dict]:
    """scheme: 'pair' or 'pair_year'. Returns (V, t-df, info)."""
    sample: FESample = fit["sample"]
    X, bread, n, k = fit["X"], fit["bread"], fit["n"], fit["k"]
    score_weight = fit["resid"] * sample.weights
    info: dict = {}
    if scheme == "pair":
        # pair-HS2 effects are nested in pair clusters; the others are not.
        k_fe = _k_fixed_effects_not_nested(sample, nested_dims=[0])
        adj = (n - 1) / (n - k - k_fe)
        groups = sample.n_pair
        meat = _meat(X, score_weight, sample.pair, groups)
        V = adj * groups / (groups - 1) * bread @ meat @ bread
        df = groups - 1
    elif scheme == "pair_year":
        # every fixed effect is nested in pair or in year clusters.
        adj = (n - 1) / (n - k)
        g_min = min(sample.n_pair, sample.n_year)
        meat = (
            _meat(X, score_weight, sample.pair, sample.n_pair)
            + _meat(X, score_weight, sample.year, sample.n_year)
            - _meat(X, score_weight, sample.pairyear, sample.n_pairyear)
        )
        V = adj * g_min / (g_min - 1) * bread @ meat @ bread
        eigval, eigvec = np.linalg.eigh(V)
        if eigval.min() < 0:
            info["eigen_fix"] = float(eigval.min())
            V = eigvec @ np.diag(np.clip(eigval, 0, None)) @ eigvec.T
        df = g_min - 1
    else:
        raise ValueError(scheme)
    return V, df, info


def coef_table(fit: dict, V: np.ndarray, df: int, scheme: str, model: str) -> pd.DataFrame:
    se = np.sqrt(np.diag(V))
    t = fit["beta"] / se
    p = 2 * stats.t.sf(np.abs(t), df)
    crit = stats.t.ppf(0.975, df)
    return pd.DataFrame(
        {
            "model": model,
            "inference": scheme,
            "term": fit["names"],
            "estimate": fit["beta"],
            "std_error": se,
            "t_value": t,
            "p_value": p,
            "ci_low": fit["beta"] - crit * se,
            "ci_high": fit["beta"] + crit * se,
            "df": df,
            "nobs": fit["n"],
        }
    )


def lincom(beta: np.ndarray, V: np.ndarray, c: np.ndarray, df: int) -> dict:
    est = float(c @ beta)
    se = float(np.sqrt(c @ V @ c))
    t = est / se if se > 0 else np.nan
    return {
        "estimate": est,
        "std_error": se,
        "t_value": t,
        "p_value": float(2 * stats.t.sf(abs(t), df)),
        "ci_low": est - stats.t.ppf(0.975, df) * se,
        "ci_high": est + stats.t.ppf(0.975, df) * se,
    }


def wald(beta: np.ndarray, V: np.ndarray, R: np.ndarray, df_denom: int, r: np.ndarray | None = None) -> dict:
    R = np.atleast_2d(R)
    r = np.zeros(R.shape[0]) if r is None else r
    diff = R @ beta - r
    q = R.shape[0]
    stat = float(diff @ np.linalg.pinv(R @ V @ R.T) @ diff)
    f_stat = stat / q
    return {"F": f_stat, "df1": q, "df2": df_denom, "p_value": float(stats.f.sf(f_stat, q, df_denom))}


def fit_and_tabulate(sample: FESample, y_name: str, x_names: list[str], model: str) -> tuple[dict, pd.DataFrame, dict]:
    fit = ols_fit(sample, y_name, x_names)
    tables, vcovs = [], {}
    for scheme in ("pair", "pair_year"):
        V, df, info = cluster_vcov(fit, scheme)
        vcovs[scheme] = (V, df, info)
        tables.append(coef_table(fit, V, df, scheme, model))
    # keep memory low: the design matrix is reloaded from cache when needed
    fit.pop("X")
    fit.pop("resid")
    return fit, pd.concat(tables, ignore_index=True), vcovs

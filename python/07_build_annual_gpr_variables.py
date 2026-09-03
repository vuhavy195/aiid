from __future__ import annotations

from pathlib import Path
import os
import sys
import traceback

import numpy as np
import pandas as pd


# ============================================================
# PROJECT SETTINGS
# ============================================================
PROJECT_ROOT = Path(
    os.environ.get(
        "AIID_PROJECT_ROOT",
        r"H:\AIID_DTA_GPR",
    )
)

GPR_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "gpr"
    / "GPR_monthly_downloaded_2026-07-26.xls"
)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
INTERIM_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

REFERENCE_START = 1985
REFERENCE_END = 2019

OUTPUT_START = 2007
OUTPUT_END = 2023
LAG_BASE_YEAR = OUTPUT_START - 1

GLOBAL_OUTPUT_PARQUET = (
    PROCESSED_DIR
    / "gpr_annual_core_2007_2023.parquet"
)

GLOBAL_OUTPUT_CSV = (
    PROCESSED_DIR
    / "gpr_annual_core_2007_2023.csv"
)

FULL_ANNUAL_OUTPUT = (
    INTERIM_DIR
    / "gpr_annual_1985_2023.csv"
)

COUNTRY_OUTPUT = (
    INTERIM_DIR
    / "gpr_country_annual_1985_2023.parquet"
)

REPORT_FILE = (
    AUDIT_DIR
    / "step7_gpr_annual_audit.txt"
)


# ============================================================
# HELPERS
# ============================================================
def zscore_with_reference(
    series: pd.Series,
    reference_mask: pd.Series,
) -> tuple[pd.Series, float, float]:
    """Standardize using the fixed 1985–2019 reference period."""
    reference = series.loc[reference_mask].dropna()

    mean = float(reference.mean())
    sd = float(reference.std(ddof=1))

    if not np.isfinite(sd) or sd <= 0:
        raise ValueError(
            "Reference-period standard deviation is invalid."
        )

    standardized = (series - mean) / sd

    return standardized, mean, sd


def validate_monthly_sequence(
    monthly: pd.DataFrame,
) -> None:
    """Check uniqueness and complete monthly coverage."""
    if monthly["month"].duplicated().any():
        duplicates = monthly.loc[
            monthly["month"].duplicated(keep=False),
            ["month", "GPR", "GPRT", "GPRA"],
        ]

        raise ValueError(
            "Duplicate monthly dates detected:\n"
            f"{duplicates.to_string(index=False)}"
        )

    expected_months = pd.date_range(
        start=f"{REFERENCE_START}-01-01",
        end=f"{OUTPUT_END}-12-01",
        freq="MS",
    )

    actual_months = pd.DatetimeIndex(
        monthly.loc[
            monthly["month"].between(
                expected_months.min(),
                expected_months.max(),
                inclusive="both",
            ),
            "month",
        ]
    )

    missing_months = expected_months.difference(actual_months)

    if len(missing_months) > 0:
        raise ValueError(
            "Missing monthly observations from "
            f"{REFERENCE_START}–{OUTPUT_END}: "
            f"{missing_months.strftime('%Y-%m').tolist()}"
        )


def read_monthly_gpr() -> pd.DataFrame:
    if not GPR_FILE.exists():
        raise FileNotFoundError(
            f"GPR file not found: {GPR_FILE}"
        )

    # xlrd is required for the old .xls workbook.
    data = pd.read_excel(
        GPR_FILE,
        sheet_name="Sheet1",
        engine="xlrd",
    )

    required_columns = {
        "month",
        "GPR",
        "GPRT",
        "GPRA",
    }

    missing_columns = required_columns - set(data.columns)

    if missing_columns:
        raise ValueError(
            "The GPR workbook is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    data["month"] = pd.to_datetime(
        data["month"],
        errors="coerce",
    )

    for column in ["GPR", "GPRT", "GPRA"]:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    # Recent GPR begins in 1985. Historical GPRH rows before
    # 1985 are intentionally excluded from this paper.
    monthly = data.loc[
        data["month"].notna()
        & data["month"].dt.year.between(
            REFERENCE_START,
            OUTPUT_END,
            inclusive="both",
        ),
    ].copy()

    monthly["year"] = monthly["month"].dt.year
    monthly["calendar_month"] = monthly["month"].dt.month

    if monthly[
        ["GPR", "GPRT", "GPRA"]
    ].isna().any().any():
        missing = monthly.loc[
            monthly[
                ["GPR", "GPRT", "GPRA"]
            ].isna().any(axis=1),
            ["month", "GPR", "GPRT", "GPRA"],
        ]

        raise ValueError(
            "Missing recent GPR values between "
            f"{REFERENCE_START} and {OUTPUT_END}:\n"
            f"{missing.to_string(index=False)}"
        )

    validate_monthly_sequence(monthly)

    country_columns = [
        column
        for column in data.columns
        if isinstance(column, str)
        and column.startswith("GPRC_")
    ]

    if len(country_columns) != 44:
        raise ValueError(
            "Expected 44 country-specific GPR series, "
            f"found {len(country_columns)}."
        )

    country_data = data.loc[
        data["month"].notna()
        & data["month"].dt.year.between(
            REFERENCE_START,
            OUTPUT_END,
            inclusive="both",
        ),
        ["month"] + country_columns,
    ].copy()

    for column in country_columns:
        country_data[column] = pd.to_numeric(
            country_data[column],
            errors="coerce",
        )

    if country_data[country_columns].isna().any().any():
        missing_counts = (
            country_data[country_columns]
            .isna()
            .sum()
        )

        problematic = missing_counts[
            missing_counts > 0
        ]

        raise ValueError(
            "Country-specific GPR series contain missing values:\n"
            f"{problematic.to_string()}"
        )

    monthly.attrs["country_data"] = country_data
    monthly.attrs["country_columns"] = country_columns

    return monthly


def build_global_annual(
    monthly: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float]]:
    reference_monthly = monthly.loc[
        monthly["year"].between(
            REFERENCE_START,
            REFERENCE_END,
            inclusive="both",
        )
    ]

    monthly_p75 = float(
        reference_monthly["GPR"].quantile(0.75)
    )

    monthly_p90 = float(
        reference_monthly["GPR"].quantile(0.90)
    )

    monthly = monthly.copy()

    monthly["gpr_above_monthly_p75"] = (
        monthly["GPR"] > monthly_p75
    ).astype("int8")

    monthly["gpr_above_monthly_p90"] = (
        monthly["GPR"] > monthly_p90
    ).astype("int8")

    annual = (
        monthly.groupby(
            "year",
            as_index=False,
        )
        .agg(
            months_available=("month", "count"),
            gpr_mean=("GPR", "mean"),
            gpr_median=("GPR", "median"),
            gpr_max=("GPR", "max"),
            gpr_min=("GPR", "min"),
            gpr_sd_monthly=("GPR", "std"),
            gpr_threat_mean=("GPRT", "mean"),
            gpr_threat_max=("GPRT", "max"),
            gpr_act_mean=("GPRA", "mean"),
            gpr_act_max=("GPRA", "max"),
            gpr_months_above_p75=(
                "gpr_above_monthly_p75",
                "sum",
            ),
            gpr_months_above_p90=(
                "gpr_above_monthly_p90",
                "sum",
            ),
        )
    )

    if not annual["months_available"].eq(12).all():
        bad_years = annual.loc[
            ~annual["months_available"].eq(12),
            ["year", "months_available"],
        ]

        raise ValueError(
            "At least one year does not contain 12 months:\n"
            f"{bad_years.to_string(index=False)}"
        )

    annual["log_gpr_mean"] = np.log1p(
        annual["gpr_mean"]
    )

    annual["gpr_change"] = annual[
        "gpr_mean"
    ].diff()

    annual["gpr_pct_change"] = annual[
        "gpr_mean"
    ].pct_change()

    reference_mask = annual["year"].between(
        REFERENCE_START,
        REFERENCE_END,
        inclusive="both",
    )

    standardization_specs = [
        ("gpr_mean", "gpr_mean_z"),
        ("log_gpr_mean", "log_gpr_mean_z"),
        ("gpr_threat_mean", "gpr_threat_mean_z"),
        ("gpr_act_mean", "gpr_act_mean_z"),
        ("gpr_max", "gpr_max_z"),
    ]

    reference_stats: dict[str, float] = {
        "monthly_p75": monthly_p75,
        "monthly_p90": monthly_p90,
    }

    for source, target in standardization_specs:
        (
            annual[target],
            mean,
            sd,
        ) = zscore_with_reference(
            annual[source],
            reference_mask,
        )

        reference_stats[f"{source}_mean"] = mean
        reference_stats[f"{source}_sd"] = sd

    # Standardize annual changes using reference-period changes.
    (
        annual["gpr_change_z"],
        change_mean,
        change_sd,
    ) = zscore_with_reference(
        annual["gpr_change"],
        reference_mask
        & annual["gpr_change"].notna(),
    )

    reference_stats["gpr_change_mean"] = change_mean
    reference_stats["gpr_change_sd"] = change_sd

    annual_p75 = float(
        annual.loc[
            reference_mask,
            "gpr_mean",
        ].quantile(0.75)
    )

    annual_p90 = float(
        annual.loc[
            reference_mask,
            "gpr_mean",
        ].quantile(0.90)
    )

    reference_stats["annual_p75"] = annual_p75
    reference_stats["annual_p90"] = annual_p90

    annual["high_gpr_annual_p75"] = (
        annual["gpr_mean"] > annual_p75
    ).astype("int8")

    annual["high_gpr_annual_p90"] = (
        annual["gpr_mean"] > annual_p90
    ).astype("int8")

    annual["any_month_above_p75"] = (
        annual["gpr_months_above_p75"] > 0
    ).astype("int8")

    annual["any_month_above_p90"] = (
        annual["gpr_months_above_p90"] > 0
    ).astype("int8")

    lag_columns = [
        "gpr_mean",
        "gpr_mean_z",
        "log_gpr_mean_z",
        "gpr_threat_mean_z",
        "gpr_act_mean_z",
        "gpr_max_z",
        "gpr_change_z",
        "high_gpr_annual_p75",
        "high_gpr_annual_p90",
        "gpr_months_above_p75",
        "gpr_months_above_p90",
    ]

    for column in lag_columns:
        annual[f"{column}_l1"] = annual[
            column
        ].shift(1)

    return annual, reference_stats


def build_country_annual(
    monthly: pd.DataFrame,
) -> pd.DataFrame:
    country_data = monthly.attrs[
        "country_data"
    ].copy()

    country_columns = monthly.attrs[
        "country_columns"
    ]

    long = country_data.melt(
        id_vars="month",
        value_vars=country_columns,
        var_name="series",
        value_name="gpr_country",
    )

    long["iso3"] = (
        long["series"]
        .str.replace("GPRC_", "", regex=False)
    )

    long["year"] = long["month"].dt.year

    annual = (
        long.groupby(
            ["iso3", "year"],
            as_index=False,
        )
        .agg(
            months_available=(
                "month",
                "count",
            ),
            gpr_country_mean=(
                "gpr_country",
                "mean",
            ),
            gpr_country_max=(
                "gpr_country",
                "max",
            ),
            gpr_country_sd_monthly=(
                "gpr_country",
                "std",
            ),
        )
    )

    if not annual["months_available"].eq(12).all():
        raise ValueError(
            "Country-specific annual GPR coverage is incomplete."
        )

    annual["log_gpr_country_mean"] = np.log1p(
        annual["gpr_country_mean"]
    )

    annual["gpr_country_mean_z"] = np.nan
    annual["log_gpr_country_mean_z"] = np.nan

    for iso3, indices in annual.groupby(
        "iso3"
    ).groups.items():
        indices = list(indices)

        group = annual.loc[indices]

        reference_mask = group["year"].between(
            REFERENCE_START,
            REFERENCE_END,
            inclusive="both",
        )

        (
            raw_z,
            _,
            _,
        ) = zscore_with_reference(
            group["gpr_country_mean"],
            reference_mask,
        )

        (
            log_z,
            _,
            _,
        ) = zscore_with_reference(
            group["log_gpr_country_mean"],
            reference_mask,
        )

        annual.loc[
            indices,
            "gpr_country_mean_z",
        ] = raw_z.to_numpy()

        annual.loc[
            indices,
            "log_gpr_country_mean_z",
        ] = log_z.to_numpy()

    annual = annual.sort_values(
        ["iso3", "year"]
    ).reset_index(drop=True)

    return annual


def export_outputs(
    annual: pd.DataFrame,
    country_annual: pd.DataFrame,
    reference_stats: dict[str, float],
) -> None:
    full_annual = annual.loc[
        annual["year"].between(
            REFERENCE_START,
            OUTPUT_END,
            inclusive="both",
        )
    ].copy()

    core = annual.loc[
        annual["year"].between(
            OUTPUT_START,
            OUTPUT_END,
            inclusive="both",
        )
    ].copy()

    if len(core) != (
        OUTPUT_END - OUTPUT_START + 1
    ):
        raise ValueError(
            "Core GPR output does not contain exactly "
            f"{OUTPUT_END - OUTPUT_START + 1} years."
        )

    if core["year"].duplicated().any():
        raise ValueError(
            "Duplicate years in the GPR core output."
        )

    required_core_columns = [
        "gpr_mean",
        "gpr_mean_z",
        "log_gpr_mean_z",
        "gpr_threat_mean_z",
        "gpr_act_mean_z",
        "gpr_max_z",
        "gpr_change_z",
        "high_gpr_annual_p75",
        "high_gpr_annual_p90",
        "gpr_months_above_p75",
        "gpr_months_above_p90",
    ]

    if core[required_core_columns].isna().any().any():
        raise ValueError(
            "Missing values detected in required GPR core variables."
        )

    full_annual.to_csv(
        FULL_ANNUAL_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    core.to_csv(
        GLOBAL_OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    core.to_parquet(
        GLOBAL_OUTPUT_PARQUET,
        index=False,
        compression="zstd",
    )

    country_annual.to_parquet(
        COUNTRY_OUTPUT,
        index=False,
        compression="zstd",
    )

    reference_table = pd.DataFrame(
        {
            "statistic": list(
                reference_stats.keys()
            ),
            "value": list(
                reference_stats.values()
            ),
        }
    )

    reference_table.to_csv(
        AUDIT_DIR
        / "step7_gpr_reference_statistics.csv",
        index=False,
        encoding="utf-8-sig",
    )

    core[
        [
            "year",
            "gpr_mean",
            "gpr_mean_z",
            "gpr_threat_mean",
            "gpr_act_mean",
            "gpr_max",
            "gpr_months_above_p75",
            "gpr_months_above_p90",
            "high_gpr_annual_p75",
            "high_gpr_annual_p90",
        ]
    ].to_csv(
        AUDIT_DIR
        / "step7_gpr_annual_preview.csv",
        index=False,
        encoding="utf-8-sig",
    )

    country_summary = (
        country_annual.groupby(
            "iso3",
            as_index=False,
        )
        .agg(
            years_available=("year", "count"),
            minimum_year=("year", "min"),
            maximum_year=("year", "max"),
            missing_mean=(
                "gpr_country_mean",
                lambda values: int(
                    values.isna().sum()
                ),
            ),
        )
    )

    country_summary.to_csv(
        AUDIT_DIR
        / "step7_country_gpr_coverage.csv",
        index=False,
        encoding="utf-8-sig",
    )

    p75_years = core.loc[
        core["high_gpr_annual_p75"].eq(1),
        "year",
    ].astype(int).tolist()

    p90_years = core.loc[
        core["high_gpr_annual_p90"].eq(1),
        "year",
    ].astype(int).tolist()

    monthly_p90_years = core.loc[
        core["gpr_months_above_p90"].gt(0),
        [
            "year",
            "gpr_months_above_p90",
        ],
    ]

    correlations = core[
        [
            "gpr_mean",
            "gpr_threat_mean",
            "gpr_act_mean",
        ]
    ].corr()

    report_lines = [
        "=" * 92,
        "AIID DTA–GPR PROJECT — STEP 7 GPR ANNUAL PANEL",
        "=" * 92,
        f"Project root: {PROJECT_ROOT}",
        "",
        "A. SOURCE AND COVERAGE",
        "-" * 92,
        (
            "Recent global GPR reference period: "
            f"{REFERENCE_START}–{REFERENCE_END}"
        ),
        (
            "Trade-period annual output: "
            f"{OUTPUT_START}–{OUTPUT_END}"
        ),
        (
            "Monthly observations in reference through "
            f"trade period: {len(full_annual) * 12:,}"
        ),
        (
            "All annual observations contain 12 monthly "
            "values: True"
        ),
        (
            "Country-specific recent GPR series: "
            f"{country_annual['iso3'].nunique():,}"
        ),
        (
            "Country-specific annual rows: "
            f"{len(country_annual):,}"
        ),
        "",
        "B. BASELINE VARIABLES",
        "-" * 92,
        (
            "Main shock variable: gpr_mean_z "
            "(annual mean, standardized using 1985–2019)"
        ),
        (
            "Main nonlinear robustness: log_gpr_mean_z"
        ),
        (
            "Components: gpr_threat_mean_z and "
            "gpr_act_mean_z"
        ),
        (
            "Peak-risk robustness: gpr_max_z"
        ),
        (
            "Dynamic innovation measure: gpr_change_z"
        ),
        "",
        "C. REFERENCE THRESHOLDS",
        "-" * 92,
        (
            "Monthly GPR 75th-percentile threshold: "
            f"{reference_stats['monthly_p75']:.6f}"
        ),
        (
            "Monthly GPR 90th-percentile threshold: "
            f"{reference_stats['monthly_p90']:.6f}"
        ),
        (
            "Annual-mean GPR 75th-percentile threshold: "
            f"{reference_stats['annual_p75']:.6f}"
        ),
        (
            "Annual-mean GPR 90th-percentile threshold: "
            f"{reference_stats['annual_p90']:.6f}"
        ),
        (
            "Trade-period years above annual p75: "
            f"{p75_years}"
        ),
        (
            "Trade-period years above annual p90: "
            f"{p90_years}"
        ),
        (
            "Trade-period years with at least one month "
            "above monthly p90:"
        ),
    ]

    for _, row in monthly_p90_years.iterrows():
        report_lines.append(
            f"  {int(row['year'])}: "
            f"{int(row['gpr_months_above_p90'])} month(s)"
        )

    report_lines.extend(
        [
            "",
            "D. CORRELATIONS, 2007–2023",
            "-" * 92,
            (
                "Corr(GPR mean, GPR threats mean): "
                f"{correlations.loc[
                    'gpr_mean',
                    'gpr_threat_mean'
                ]:.6f}"
            ),
            (
                "Corr(GPR mean, GPR acts mean): "
                f"{correlations.loc[
                    'gpr_mean',
                    'gpr_act_mean'
                ]:.6f}"
            ),
            "",
            "E. MODEL NOTE",
            "-" * 92,
            (
                "Global GPR varies only by year. Its standalone "
                "coefficient is absorbed by year fixed effects."
            ),
            (
                "The main estimand is therefore the interaction "
                "between GPR and lagged bilateral DTA depth."
            ),
            (
                "Use continuous gpr_mean_z in the baseline. "
                "Annual p90 identifies only very few trade-period "
                "years and should not be the primary treatment."
            ),
            "",
            "F. OUTPUT FILES",
            "-" * 92,
            "data/processed/gpr_annual_core_2007_2023.parquet",
            "data/processed/gpr_annual_core_2007_2023.csv",
            "data/interim/gpr_annual_1985_2023.csv",
            "data/interim/gpr_country_annual_1985_2023.parquet",
            "outputs/audit/step7_gpr_annual_audit.txt",
            "outputs/audit/step7_gpr_reference_statistics.csv",
            "outputs/audit/step7_gpr_annual_preview.csv",
            "outputs/audit/step7_country_gpr_coverage.csv",
            "",
            "G. NEXT ACTION",
            "-" * 92,
            (
                "Send the audit report, annual preview, "
                "reference-statistics file and country-coverage "
                "file to ChatGPT."
            ),
            (
                "Do not run PPML yet. The next step merges trade, "
                "DTA and GPR and constructs the estimation panels."
            ),
        ]
    )

    REPORT_FILE.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    print("\n".join(report_lines))
    print("")
    print(f"Report saved to: {REPORT_FILE}")


def main() -> None:
    print("=" * 92)
    print("STEP 7 — BUILD ANNUAL GPR VARIABLES")
    print("=" * 92)
    print(f"Project root: {PROJECT_ROOT}")
    print("Reading monthly GPR workbook ...")

    monthly = read_monthly_gpr()

    print("Aggregating global monthly GPR to annual data ...")

    annual, reference_stats = build_global_annual(
        monthly
    )

    print(
        "Aggregating 44 country-specific GPR series ..."
    )

    country_annual = build_country_annual(
        monthly
    )

    print("Writing data and audit outputs ...")

    export_outputs(
        annual,
        country_annual,
        reference_stats,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        failure_lines = [
            "=" * 92,
            "STEP 7 FAILED",
            "=" * 92,
            f"{type(error).__name__}: {error}",
            "",
            traceback.format_exc(),
        ]

        REPORT_FILE.write_text(
            "\n".join(failure_lines),
            encoding="utf-8",
        )

        print(
            "\n".join(failure_lines),
            flush=True,
        )

        sys.exit(1)

from __future__ import annotations

from itertools import combinations
from pathlib import Path
import os
import re
import sys
import traceback

import numpy as np
import pandas as pd


# ============================================================
# PROJECT SETTINGS
# ============================================================
# The environment-variable override is optional. On your computer,
# the default path below will be used automatically.
PROJECT_ROOT = Path(
    os.environ.get(
        "AIID_PROJECT_ROOT",
        r"H:\AIID_DTA_GPR",
    )
)

START_TRADE_YEAR = 2007
END_TRADE_YEAR = 2023
LAG_BASE_YEAR = START_TRADE_YEAR - 1

COUNTRY_SAMPLE_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "country_sample_160.csv"
)

DTA_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "dta_world_bank"
    / "DTA_1_Horizontal_Content_v2.xlsx"
)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
INTERIM_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

CORE_OUTPUT = (
    PROCESSED_DIR
    / "dta_pair_year_core_160.parquet"
)

ACTIVE_PROVISIONS_OUTPUT = (
    INTERIM_DIR
    / "dta_active_pair_year_le_provisions_160.parquet"
)

ACTIVE_AGREEMENTS_OUTPUT = (
    INTERIM_DIR
    / "dta_active_agreement_records_160.parquet"
)

REPORT_FILE = (
    AUDIT_DIR
    / "step6_dta_panel_audit.txt"
)

SELECTED_MECHANISMS = [
    "Customs",
    "SPS",
    "TBT",
    "PublicProcurement",
    "TRIMs",
    "GATS",
    "TRIPs",
    "CompetitionPolicy",
    "EnvironmentalLaws",
    "IPR",
    "Investment",
    "DataProtection",
    "InformationSociety",
    "ResearchandTechnology",
    "InnovationPolicies",
    "MovementofCapital",
]

KEY_VIETNAM_AGREEMENTS = {
    281: "CPTPP",
    288: "EVFTA",
    395: "RCEP",
}


def normalize_rta_id(value: object) -> str | None:
    """Normalize WTO RTA IDs, including alphanumeric IDs."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return text or None


def validate_required_files() -> None:
    missing = [
        path
        for path in [
            COUNTRY_SAMPLE_FILE,
            DTA_FILE,
        ]
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing required file(s):\n"
            + "\n".join(str(path) for path in missing)
        )


def read_country_sample() -> pd.DataFrame:
    sample = pd.read_csv(
        COUNTRY_SAMPLE_FILE,
        dtype={
            "analysis_iso3": "string",
            "analysis_name": "string",
        },
    )

    required_columns = {
        "country_code",
        "analysis_iso3",
        "analysis_name",
        "final_sample_rank",
    }

    missing_columns = required_columns - set(sample.columns)

    if missing_columns:
        raise ValueError(
            "country_sample_160.csv is missing columns: "
            f"{sorted(missing_columns)}"
        )

    if len(sample) != 160:
        raise ValueError(
            f"Expected 160 economies, found {len(sample)}."
        )

    if sample["country_code"].duplicated().any():
        raise ValueError(
            "Duplicate country_code values in the country sample."
        )

    if sample["analysis_iso3"].duplicated().any():
        raise ValueError(
            "Duplicate analysis_iso3 values in the country sample."
        )

    sample["analysis_iso3"] = (
        sample["analysis_iso3"]
        .astype("string")
        .str.strip()
    )

    return sample


def read_dta_sheets() -> dict[str, pd.DataFrame]:
    sheet_names = [
        "WTO+ AC",
        "WTO-X AC",
        "WTO+ LE",
        "WTO-X LE",
        "Agreements",
        "Bilateral Information",
    ]

    # Read all required sheets in a single workbook pass. This is
    # materially faster than reopening the 10 MB workbook six times.
    sheets = pd.read_excel(
        DTA_FILE,
        sheet_name=sheet_names,
        engine="openpyxl",
    )

    return sheets


def prepare_content_matrix(
    sheets: dict[str, pd.DataFrame],
) -> tuple[
    pd.DataFrame,
    list[str],
    list[str],
]:
    agreements = sheets["Agreements"].copy()

    agreements["RTAID_norm"] = (
        agreements["RTA ID"].map(normalize_rta_id)
    )

    if agreements["RTAID_norm"].duplicated().any():
        duplicate_rows = agreements.loc[
            agreements["RTAID_norm"].duplicated(
                keep=False
            ),
            [
                "Agreement",
                "WB ID",
                "RTA ID",
                "RTAID_norm",
            ],
        ]

        raise ValueError(
            "RTA IDs are not unique in Agreements:\n"
            f"{duplicate_rows.to_string(index=False)}"
        )

    content = agreements[
        [
            "WB ID",
            "RTAID_norm",
            "Agreement",
            "Status",
        ]
    ].rename(
        columns={
            "WB ID": "WBID",
            "Agreement": "agreement_name",
        }
    )

    all_le_columns: list[str] = []
    all_ac_columns: list[str] = []

    sheet_specs = [
        ("WTO+ LE", "le_"),
        ("WTO-X LE", "le_"),
        ("WTO+ AC", "ac_"),
        ("WTO-X AC", "ac_"),
    ]

    for sheet_name, prefix in sheet_specs:
        frame = sheets[sheet_name].copy()

        frame["RTAID_norm"] = (
            frame["RTAID"].map(normalize_rta_id)
        )

        if frame["RTAID_norm"].duplicated().any():
            raise ValueError(
                f"Duplicate RTAID values in {sheet_name}."
            )

        identifier_columns = {
            "RTAID",
            "WBID",
            "Agreement",
            "RTAID_norm",
        }

        provision_columns = [
            column
            for column in frame.columns
            if column not in identifier_columns
        ]

        for column in provision_columns:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="coerce",
            )

        renamed_columns = {
            column: f"{prefix}{column}"
            for column in provision_columns
        }

        temporary = frame[
            ["RTAID_norm"] + provision_columns
        ].rename(columns=renamed_columns)

        content = content.merge(
            temporary,
            on="RTAID_norm",
            how="left",
            validate="one_to_one",
        )

        prefixed = list(renamed_columns.values())

        if prefix == "le_":
            all_le_columns.extend(prefixed)
        else:
            all_ac_columns.extend(prefixed)

    if len(all_le_columns) != 52:
        raise ValueError(
            "Expected 52 legally enforceable policy areas, "
            f"found {len(all_le_columns)}."
        )

    if len(all_ac_columns) != 52:
        raise ValueError(
            "Expected 52 agreement-coverage policy areas, "
            f"found {len(all_ac_columns)}."
        )

    content["has_content"] = (
        content[all_le_columns].notna().any(axis=1)
    )

    content["agreement_depth_strict"] = (
        content[all_le_columns]
        .eq(2)
        .sum(axis=1)
        .where(content["has_content"])
    )

    content["agreement_depth_broad"] = (
        content[all_le_columns]
        .isin([1, 2])
        .sum(axis=1)
        .where(content["has_content"])
    )

    content["agreement_coverage"] = (
        content[all_ac_columns]
        .eq(1)
        .sum(axis=1)
        .where(content["has_content"])
    )

    if int(content["has_content"].sum()) != 391:
        raise ValueError(
            "Expected 391 agreements with content coding, "
            f"found {int(content['has_content'].sum())}."
        )

    return content, all_le_columns, all_ac_columns


def prepare_active_agreement_records(
    bilateral: pd.DataFrame,
    content: pd.DataFrame,
    sample_iso3: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    active = bilateral.loc[
        bilateral["year"].between(
            LAG_BASE_YEAR,
            END_TRADE_YEAR,
            inclusive="both",
        )
        & bilateral["iso1"].isin(sample_iso3)
        & bilateral["iso2"].isin(sample_iso3)
        & bilateral["iso1"].ne(
            bilateral["iso2"]
        )
    ].copy()

    active["year"] = (
        pd.to_numeric(
            active["year"],
            errors="raise",
        )
        .astype(int)
    )

    active["iso_lo"] = active[
        ["iso1", "iso2"]
    ].min(axis=1)

    active["iso_hi"] = active[
        ["iso1", "iso2"]
    ].max(axis=1)

    # RTA content is symmetric. Collapse the predominantly directed
    # bilateral table to one unordered pair–agreement–year record.
    active = active[
        [
            "iso_lo",
            "iso_hi",
            "year",
            "WBID",
            "rta_name",
            "type",
            "entry",
        ]
    ].drop_duplicates(
        subset=[
            "iso_lo",
            "iso_hi",
            "year",
            "WBID",
        ]
    )

    active = active.merge(
        content,
        on="WBID",
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    unmatched_wbid = active.loc[
        active["_merge"].ne("both"),
        "WBID",
    ].drop_duplicates()

    if not unmatched_wbid.empty:
        raise ValueError(
            "Active WBIDs not found in Agreements: "
            f"{unmatched_wbid.tolist()}"
        )

    active = active.drop(columns="_merge")

    # First active year is calculated from the full bilateral history,
    # not only 2006–2023.
    history = bilateral.loc[
        bilateral["year"].notna()
        & bilateral["iso1"].isin(sample_iso3)
        & bilateral["iso2"].isin(sample_iso3)
        & bilateral["iso1"].ne(
            bilateral["iso2"]
        )
    ].copy()

    history["year"] = (
        pd.to_numeric(
            history["year"],
            errors="raise",
        )
        .astype(int)
    )

    history["iso_lo"] = history[
        ["iso1", "iso2"]
    ].min(axis=1)

    history["iso_hi"] = history[
        ["iso1", "iso2"]
    ].max(axis=1)

    first_fta_year = (
        history.groupby(
            ["iso_lo", "iso_hi"],
            as_index=False,
        )["year"]
        .min()
        .rename(
            columns={
                "year": "first_fta_year",
            }
        )
    )

    return active, first_fta_year


def aggregate_pair_year_treatment(
    active: pd.DataFrame,
    le_columns: list[str],
    ac_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metadata = (
        active.groupby(
            ["iso_lo", "iso_hi", "year"],
            as_index=False,
            sort=False,
        )
        .agg(
            active_agreement_count=(
                "WBID",
                "nunique",
            ),
            coded_agreement_count=(
                "has_content",
                lambda values: int(
                    values.fillna(False).sum()
                ),
            ),
            missing_content_agreement_count=(
                "has_content",
                lambda values: int(
                    (~values.fillna(False)).sum()
                ),
            ),
        )
    )

    coded = active.loc[
        active["has_content"].fillna(False)
    ].copy()

    provision_max = (
        coded.groupby(
            ["iso_lo", "iso_hi", "year"],
            as_index=False,
            sort=False,
        )[le_columns + ac_columns]
        .max()
    )

    provision_max["depth_strict_observed"] = (
        provision_max[le_columns]
        .eq(2)
        .sum(axis=1)
    )

    provision_max["depth_broad_observed"] = (
        provision_max[le_columns]
        .isin([1, 2])
        .sum(axis=1)
    )

    provision_max["depth_coverage_observed"] = (
        provision_max[ac_columns]
        .eq(1)
        .sum(axis=1)
    )

    for mechanism in SELECTED_MECHANISMS:
        source_column = f"le_{mechanism}"

        if source_column not in provision_max.columns:
            raise ValueError(
                f"Mechanism column not found: {source_column}"
            )

        provision_max[
            f"strict_{mechanism}"
        ] = (
            provision_max[source_column]
            .eq(2)
            .astype("int8")
        )

    selected_columns = [
        "iso_lo",
        "iso_hi",
        "year",
        "depth_strict_observed",
        "depth_broad_observed",
        "depth_coverage_observed",
    ] + [
        f"strict_{mechanism}"
        for mechanism in SELECTED_MECHANISMS
    ]

    treatment = metadata.merge(
        provision_max[selected_columns],
        on=["iso_lo", "iso_hi", "year"],
        how="left",
        validate="one_to_one",
    )

    treatment["fta_active"] = 1

    treatment["depth_data_complete"] = (
        treatment[
            "missing_content_agreement_count"
        ].eq(0)
    )

    treatment["depth_strict"] = (
        treatment["depth_strict_observed"]
        .where(
            treatment["depth_data_complete"]
        )
    )

    treatment["depth_broad"] = (
        treatment["depth_broad_observed"]
        .where(
            treatment["depth_data_complete"]
        )
    )

    treatment["depth_coverage"] = (
        treatment["depth_coverage_observed"]
        .where(
            treatment["depth_data_complete"]
        )
    )

    for mechanism in SELECTED_MECHANISMS:
        column = f"strict_{mechanism}"

        treatment[column] = (
            treatment[column]
            .where(
                treatment["depth_data_complete"]
            )
        )

    # Save the full 52-area legally enforceable maxima for active
    # unordered pair–years. These are not expanded to all zeros yet.
    active_provisions = provision_max[
        [
            "iso_lo",
            "iso_hi",
            "year",
        ]
        + le_columns
        + [
            "depth_strict_observed",
            "depth_broad_observed",
            "depth_coverage_observed",
        ]
    ].merge(
        metadata,
        on=["iso_lo", "iso_hi", "year"],
        how="left",
        validate="one_to_one",
    )

    active_provisions["depth_data_complete"] = (
        active_provisions[
            "missing_content_agreement_count"
        ].eq(0)
    )

    return treatment, active_provisions


def build_unordered_core_panel(
    treatment: pd.DataFrame,
    first_fta_year: pd.DataFrame,
    iso3_values: list[str],
) -> pd.DataFrame:
    pair_table = pd.DataFrame(
        list(combinations(iso3_values, 2)),
        columns=["iso_lo", "iso_hi"],
    )

    year_table = pd.DataFrame(
        {
            "year": np.arange(
                LAG_BASE_YEAR,
                END_TRADE_YEAR + 1,
                dtype=np.int16,
            )
        }
    )

    pair_table["_merge_key"] = 1
    year_table["_merge_key"] = 1

    grid = (
        pair_table.merge(
            year_table,
            on="_merge_key",
            how="inner",
        )
        .drop(columns="_merge_key")
    )

    panel = grid.merge(
        treatment,
        on=["iso_lo", "iso_hi", "year"],
        how="left",
        validate="one_to_one",
    )

    no_agreement = panel["fta_active"].isna()

    panel["fta_active"] = (
        panel["fta_active"]
        .fillna(0)
        .astype("int8")
    )

    count_columns = [
        "active_agreement_count",
        "coded_agreement_count",
        "missing_content_agreement_count",
    ]

    for column in count_columns:
        panel[column] = (
            panel[column]
            .fillna(0)
            .astype("int16")
        )

    panel["depth_data_complete"] = (
        panel["depth_data_complete"]
        .astype("boolean")
        .fillna(True)
        .astype(bool)
    )

    zero_when_no_agreement = [
        "depth_strict_observed",
        "depth_broad_observed",
        "depth_coverage_observed",
        "depth_strict",
        "depth_broad",
        "depth_coverage",
    ] + [
        f"strict_{mechanism}"
        for mechanism in SELECTED_MECHANISMS
    ]

    for column in zero_when_no_agreement:
        panel.loc[
            no_agreement,
            column,
        ] = 0

    panel = panel.merge(
        first_fta_year,
        on=["iso_lo", "iso_hi"],
        how="left",
        validate="many_to_one",
    )

    panel["agreement_age"] = np.where(
        panel["fta_active"].eq(1),
        panel["year"]
        - panel["first_fta_year"]
        + 1,
        0,
    )

    return panel


def add_lags_and_changes(
    unordered_panel: pd.DataFrame,
) -> pd.DataFrame:
    lag_columns = [
        "fta_active",
        "depth_data_complete",
        "active_agreement_count",
        "depth_strict",
        "depth_broad",
        "depth_coverage",
    ] + [
        f"strict_{mechanism}"
        for mechanism in SELECTED_MECHANISMS
    ]

    lag_frame = unordered_panel[
        [
            "iso_lo",
            "iso_hi",
            "year",
        ]
        + lag_columns
    ].copy()

    lag_frame["year"] = lag_frame["year"] + 1

    lag_frame = lag_frame.rename(
        columns={
            column: f"{column}_l1"
            for column in lag_columns
        }
    )

    current = unordered_panel.loc[
        unordered_panel["year"].between(
            START_TRADE_YEAR,
            END_TRADE_YEAR,
            inclusive="both",
        )
    ].copy()

    current = current.merge(
        lag_frame,
        on=["iso_lo", "iso_hi", "year"],
        how="left",
        validate="one_to_one",
    )

    if current[
        [
            f"{column}_l1"
            for column in lag_columns
        ]
    ].isna().all(axis=1).any():
        raise ValueError(
            "At least one 2007–2023 pair-year has no lag row."
        )

    current["new_fta_entry"] = (
        current["fta_active"].eq(1)
        & current["fta_active_l1"].eq(0)
    ).astype("int8")

    current["depth_change_strict"] = (
        current["depth_strict"]
        - current["depth_strict_l1"]
    )

    current["depth_upgrade"] = np.where(
        current["depth_change_strict"].notna(),
        (
            current["depth_change_strict"] > 0
        ).astype("int8"),
        np.nan,
    )

    current["depth_downgrade"] = np.where(
        current["depth_change_strict"].notna(),
        (
            current["depth_change_strict"] < 0
        ).astype("int8"),
        np.nan,
    )

    return current


def expand_to_directed_panel(
    unordered_panel: pd.DataFrame,
    country_sample: pd.DataFrame,
) -> pd.DataFrame:
    forward = unordered_panel.rename(
        columns={
            "iso_lo": "exporter_iso3",
            "iso_hi": "importer_iso3",
        }
    ).copy()

    reverse = unordered_panel.rename(
        columns={
            "iso_lo": "importer_iso3",
            "iso_hi": "exporter_iso3",
        }
    ).copy()

    directed = pd.concat(
        [forward, reverse],
        ignore_index=True,
    )

    exporter_lookup = country_sample[
        [
            "analysis_iso3",
            "country_code",
            "analysis_name",
            "final_sample_rank",
        ]
    ].rename(
        columns={
            "analysis_iso3": "exporter_iso3",
            "country_code": "exporter_code",
            "analysis_name": "exporter_name",
            "final_sample_rank": "exporter_rank",
        }
    )

    importer_lookup = country_sample[
        [
            "analysis_iso3",
            "country_code",
            "analysis_name",
            "final_sample_rank",
        ]
    ].rename(
        columns={
            "analysis_iso3": "importer_iso3",
            "country_code": "importer_code",
            "analysis_name": "importer_name",
            "final_sample_rank": "importer_rank",
        }
    )

    directed = directed.merge(
        exporter_lookup,
        on="exporter_iso3",
        how="left",
        validate="many_to_one",
    )

    directed = directed.merge(
        importer_lookup,
        on="importer_iso3",
        how="left",
        validate="many_to_one",
    )

    directed["directed_pair_id"] = (
        directed["exporter_iso3"]
        + "_"
        + directed["importer_iso3"]
    )

    directed["unordered_pair_id"] = (
        directed[
            ["exporter_iso3", "importer_iso3"]
        ]
        .min(axis=1)
        + "_"
        + directed[
            ["exporter_iso3", "importer_iso3"]
        ]
        .max(axis=1)
    )

    expected_rows = (
        160
        * 159
        * (
            END_TRADE_YEAR
            - START_TRADE_YEAR
            + 1
        )
    )

    if len(directed) != expected_rows:
        raise ValueError(
            f"Expected {expected_rows:,} directed rows, "
            f"found {len(directed):,}."
        )

    key_columns = [
        "exporter_iso3",
        "importer_iso3",
        "year",
    ]

    if directed.duplicated(key_columns).any():
        raise ValueError(
            "Duplicate exporter–importer–year keys."
        )

    # Verify that treatment is symmetric in both directions.
    symmetry_columns = [
        "fta_active",
        "depth_data_complete",
        "depth_strict",
        "depth_broad",
        "depth_coverage",
    ]

    reverse_check = directed[
        key_columns + symmetry_columns
    ].rename(
        columns={
            "exporter_iso3": "importer_iso3",
            "importer_iso3": "exporter_iso3",
            **{
                column: f"{column}_reverse"
                for column in symmetry_columns
            },
        }
    )

    check = directed[
        key_columns + symmetry_columns
    ].merge(
        reverse_check,
        on=key_columns,
        how="left",
        validate="one_to_one",
    )

    mismatch = (
        check["fta_active"]
        .ne(check["fta_active_reverse"])
        | check["depth_data_complete"]
        .ne(
            check[
                "depth_data_complete_reverse"
            ]
        )
        | ~np.isclose(
            check["depth_strict"],
            check["depth_strict_reverse"],
            equal_nan=True,
        )
        | ~np.isclose(
            check["depth_broad"],
            check["depth_broad_reverse"],
            equal_nan=True,
        )
        | ~np.isclose(
            check["depth_coverage"],
            check["depth_coverage_reverse"],
            equal_nan=True,
        )
    )

    if mismatch.any():
        raise ValueError(
            f"Symmetry check failed for "
            f"{int(mismatch.sum())} directed rows."
        )

    return directed


def export_audit_outputs(
    directed: pd.DataFrame,
    active: pd.DataFrame,
    active_provisions: pd.DataFrame,
) -> None:
    # Full estimation-ready DTA treatment panel.
    directed.to_parquet(
        CORE_OUTPUT,
        index=False,
        compression="zstd",
    )

    active_provisions.loc[
        active_provisions["year"].between(
            START_TRADE_YEAR,
            END_TRADE_YEAR,
            inclusive="both",
        )
    ].to_parquet(
        ACTIVE_PROVISIONS_OUTPUT,
        index=False,
        compression="zstd",
    )

    active_output_columns = [
        "iso_lo",
        "iso_hi",
        "year",
        "WBID",
        "RTAID_norm",
        "rta_name",
        "agreement_name",
        "type",
        "entry",
        "has_content",
        "agreement_depth_strict",
        "agreement_depth_broad",
        "agreement_coverage",
    ]

    active.loc[
        active["year"].between(
            START_TRADE_YEAR,
            END_TRADE_YEAR,
            inclusive="both",
        ),
        active_output_columns,
    ].to_parquet(
        ACTIVE_AGREEMENTS_OUTPUT,
        index=False,
        compression="zstd",
    )

    depth_distribution = (
        directed.loc[
            directed["depth_data_complete"]
            & directed["fta_active"].eq(1)
        ]
        .groupby(
            ["year", "depth_strict"],
            dropna=False,
        )
        .size()
        .reset_index(
            name="directed_pair_year_rows"
        )
    )

    depth_distribution.to_csv(
        AUDIT_DIR
        / "step6_dta_depth_distribution.csv",
        index=False,
        encoding="utf-8-sig",
    )

    missing_content = directed.loc[
        ~directed["depth_data_complete"],
        [
            "exporter_iso3",
            "importer_iso3",
            "year",
            "active_agreement_count",
            "coded_agreement_count",
            "missing_content_agreement_count",
            "depth_strict_observed",
            "depth_broad_observed",
        ],
    ].copy()

    missing_content.to_csv(
        AUDIT_DIR
        / "step6_dta_missing_content_pair_years.csv",
        index=False,
        encoding="utf-8-sig",
    )

    changes = directed.loc[
        directed["exporter_iso3"].lt(
            directed["importer_iso3"]
        )
        & (
            directed["new_fta_entry"].eq(1)
            | directed[
                "depth_change_strict"
            ].fillna(0).ne(0)
            | ~directed[
                "depth_data_complete"
            ]
        ),
        [
            "exporter_iso3",
            "importer_iso3",
            "year",
            "fta_active",
            "fta_active_l1",
            "new_fta_entry",
            "depth_strict",
            "depth_strict_l1",
            "depth_change_strict",
            "depth_upgrade",
            "depth_downgrade",
            "active_agreement_count",
            "missing_content_agreement_count",
        ],
    ].copy()

    changes.to_csv(
        AUDIT_DIR / "step6_dta_changes.csv",
        index=False,
        encoding="utf-8-sig",
    )

    vietnam_changes = directed.loc[
        directed["exporter_iso3"].eq("VNM")
        & (
            directed["new_fta_entry"].eq(1)
            | directed[
                "depth_change_strict"
            ].fillna(0).ne(0)
            | ~directed[
                "depth_data_complete"
            ]
        ),
        [
            "importer_iso3",
            "importer_name",
            "year",
            "fta_active",
            "fta_active_l1",
            "new_fta_entry",
            "depth_strict",
            "depth_strict_l1",
            "depth_change_strict",
            "active_agreement_count",
            "missing_content_agreement_count",
        ],
    ].sort_values(
        ["year", "importer_iso3"]
    )

    vietnam_changes.to_csv(
        AUDIT_DIR / "step6_vietnam_dta_changes.csv",
        index=False,
        encoding="utf-8-sig",
    )

    key_checks: list[pd.DataFrame] = []

    for wbid, short_name in KEY_VIETNAM_AGREEMENTS.items():
        subset = active.loc[
            active["WBID"].eq(wbid)
            & (
                active["iso_lo"].eq("VNM")
                | active["iso_hi"].eq("VNM")
            )
            & active["year"].between(
                START_TRADE_YEAR,
                END_TRADE_YEAR,
                inclusive="both",
            )
        ].copy()

        if subset.empty:
            raise ValueError(
                f"No Vietnam records found for {short_name} "
                f"(WBID={wbid})."
            )

        subset["partner_iso3"] = np.where(
            subset["iso_lo"].eq("VNM"),
            subset["iso_hi"],
            subset["iso_lo"],
        )

        check = (
            subset.groupby(
                "partner_iso3",
                as_index=False,
            )
            .agg(
                first_active_year=("year", "min"),
                last_active_year=("year", "max"),
                has_content=("has_content", "all"),
            )
        )

        check["agreement_short_name"] = short_name
        check["WBID"] = wbid

        key_checks.append(check)

    key_check = pd.concat(
        key_checks,
        ignore_index=True,
    )

    key_check.to_csv(
        AUDIT_DIR
        / "step6_vietnam_key_agreement_check.csv",
        index=False,
        encoding="utf-8-sig",
    )

    yearly_summary = (
        directed.groupby(
            "year",
            as_index=False,
        )
        .agg(
            directed_pair_rows=(
                "directed_pair_id",
                "size",
            ),
            fta_active_rows=(
                "fta_active",
                "sum",
            ),
            complete_depth_rows=(
                "depth_data_complete",
                "sum",
            ),
            incomplete_depth_rows=(
                "depth_data_complete",
                lambda values: int(
                    (~values).sum()
                ),
            ),
            mean_depth_all_complete=(
                "depth_strict",
                "mean",
            ),
            new_fta_entry_rows=(
                "new_fta_entry",
                "sum",
            ),
            depth_upgrade_rows=(
                "depth_upgrade",
                "sum",
            ),
            depth_downgrade_rows=(
                "depth_downgrade",
                "sum",
            ),
        )
    )

    yearly_summary.to_csv(
        AUDIT_DIR / "step6_dta_yearly_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    core_preview_columns = [
        "exporter_iso3",
        "importer_iso3",
        "year",
        "fta_active",
        "depth_data_complete",
        "depth_strict",
        "depth_broad",
        "depth_coverage",
        "depth_strict_l1",
        "new_fta_entry",
        "depth_change_strict",
        "active_agreement_count",
    ]

    directed.loc[
        directed["exporter_iso3"].isin(
            ["VNM", "USA", "CHN"]
        )
        & directed["year"].isin(
            [2007, 2019, 2020, 2022, 2023]
        ),
        core_preview_columns,
    ].head(500).to_csv(
        AUDIT_DIR / "step6_dta_core_preview.csv",
        index=False,
        encoding="utf-8-sig",
    )

    number_of_rows = len(directed)
    fta_rows = int(
        directed["fta_active"].sum()
    )
    incomplete_rows = int(
        (~directed["depth_data_complete"]).sum()
    )
    lag_incomplete_rows = int(
        (
            ~directed[
                "depth_data_complete_l1"
            ].astype(bool)
        ).sum()
    )
    ever_fta_pairs = int(
        directed.groupby(
            "unordered_pair_id"
        )["fta_active"].max().sum()
    )
    total_unordered_pairs = int(
        directed[
            "unordered_pair_id"
        ].nunique()
    )
    new_entries = int(
        directed["new_fta_entry"].sum()
    )
    upgrades = int(
        directed["depth_upgrade"].sum(
            skipna=True
        )
    )
    downgrades = int(
        directed["depth_downgrade"].sum(
            skipna=True
        )
    )

    complete_active = directed.loc[
        directed["fta_active"].eq(1)
        & directed["depth_data_complete"]
    ]

    report_lines = [
        "=" * 92,
        "AIID DTA–GPR PROJECT — STEP 6 DTA PAIR-YEAR PANEL",
        "=" * 92,
        f"Project root: {PROJECT_ROOT}",
        (
            f"Trade-period output: "
            f"{START_TRADE_YEAR}–{END_TRADE_YEAR}"
        ),
        (
            f"Lag base year included internally: "
            f"{LAG_BASE_YEAR}"
        ),
        "",
        "A. PANEL STRUCTURE",
        "-" * 92,
        f"Directed pair-year rows: {number_of_rows:,}",
        (
            f"Unique unordered pairs: "
            f"{total_unordered_pairs:,}"
        ),
        (
            "Pairs with an active agreement at least once: "
            f"{ever_fta_pairs:,}"
        ),
        (
            "Directed pair-years with FTA active: "
            f"{fta_rows:,} "
            f"({fta_rows / number_of_rows:.6%})"
        ),
        "",
        "B. CONTENT COMPLETENESS",
        "-" * 92,
        (
            "Directed pair-years with incomplete current "
            f"depth coding: {incomplete_rows:,}"
        ),
        (
            "Directed pair-years with incomplete lagged "
            f"depth coding: {lag_incomplete_rows:,}"
        ),
        (
            "Baseline rule: keep FTA status, but set depth "
            "to missing whenever any active agreement lacks "
            "content coding."
        ),
        "",
        "C. DEPTH DISTRIBUTION",
        "-" * 92,
        (
            "Mean strict depth among active, complete "
            f"pair-years: "
            f"{complete_active['depth_strict'].mean():.4f}"
        ),
        (
            "Median strict depth among active, complete "
            f"pair-years: "
            f"{complete_active['depth_strict'].median():.4f}"
        ),
        (
            "Maximum strict depth among active, complete "
            f"pair-years: "
            f"{complete_active['depth_strict'].max():.0f}"
        ),
        "",
        "D. TREATMENT CHANGES",
        "-" * 92,
        (
            "Directed new-FTA-entry rows: "
            f"{new_entries:,}"
        ),
        (
            "Directed positive depth-change rows: "
            f"{upgrades:,}"
        ),
        (
            "Directed negative depth-change rows: "
            f"{downgrades:,}"
        ),
        "",
        "E. CONSTRUCTION RULES",
        "-" * 92,
        (
            "1. The DTA bilateral table is collapsed to "
            "unordered pairs because agreement content is "
            "symmetric."
        ),
        (
            "2. Overlapping agreements are combined using "
            "the provision-level maximum, not by adding "
            "agreement depth scores."
        ),
        (
            "3. Strict depth counts policy areas coded 2; "
            "broad depth counts policy areas coded 1 or 2."
        ),
        (
            "4. No-FTA pair-years receive depth 0 and "
            "complete-data status."
        ),
        (
            "5. Pair-years involving any uncoded active "
            "agreement keep observed lower-bound depth but "
            "receive missing complete depth."
        ),
        (
            "6. Lagged variables use the previous calendar "
            "year, including 2006 for the 2007 trade outcome."
        ),
        "",
        "F. OUTPUT FILES",
        "-" * 92,
        "data/processed/dta_pair_year_core_160.parquet",
        (
            "data/interim/"
            "dta_active_pair_year_le_provisions_160.parquet"
        ),
        (
            "data/interim/"
            "dta_active_agreement_records_160.parquet"
        ),
        "outputs/audit/step6_dta_panel_audit.txt",
        "outputs/audit/step6_dta_yearly_summary.csv",
        "outputs/audit/step6_dta_depth_distribution.csv",
        (
            "outputs/audit/"
            "step6_dta_missing_content_pair_years.csv"
        ),
        "outputs/audit/step6_dta_changes.csv",
        "outputs/audit/step6_vietnam_dta_changes.csv",
        (
            "outputs/audit/"
            "step6_vietnam_key_agreement_check.csv"
        ),
        "",
        "G. NEXT ACTION",
        "-" * 92,
        (
            "Send the audit report, yearly summary, missing-"
            "content file and Vietnam key-agreement check "
            "to ChatGPT."
        ),
        (
            "Do not standardize depth or run PPML yet. "
            "The annual GPR variables must be built and "
            "audited next."
        ),
    ]

    REPORT_FILE.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    print("\n".join(report_lines))
    print("")
    print(f"Report saved to: {REPORT_FILE}")


def main() -> None:
    validate_required_files()

    print("=" * 92)
    print("STEP 6 — BUILD DTA PAIR-YEAR TREATMENT PANEL")
    print("=" * 92)
    print(f"Project root: {PROJECT_ROOT}")
    print("Reading the DTA workbook ...")

    country_sample = read_country_sample()
    sample_iso3 = set(
        country_sample["analysis_iso3"]
        .dropna()
        .astype(str)
    )
    iso3_values = sorted(sample_iso3)

    sheets = read_dta_sheets()

    print("Constructing agreement-level content coding ...")

    (
        content,
        le_columns,
        ac_columns,
    ) = prepare_content_matrix(sheets)

    print(
        "Symmetrizing active agreements and "
        "checking first-entry years ..."
    )

    (
        active,
        first_fta_year,
    ) = prepare_active_agreement_records(
        sheets["Bilateral Information"],
        content,
        sample_iso3,
    )

    print(
        "Combining overlapping agreements at "
        "the provision level ..."
    )

    (
        treatment,
        active_provisions,
    ) = aggregate_pair_year_treatment(
        active,
        le_columns,
        ac_columns,
    )

    print("Creating the complete unordered pair-year grid ...")

    unordered_core = build_unordered_core_panel(
        treatment,
        first_fta_year,
        iso3_values,
    )

    print("Creating one-year lags and treatment changes ...")

    unordered_core = add_lags_and_changes(
        unordered_core
    )

    print("Expanding to directed exporter–importer rows ...")

    directed = expand_to_directed_panel(
        unordered_core,
        country_sample,
    )

    print("Writing Parquet data and audit outputs ...")

    export_audit_outputs(
        directed,
        active,
        active_provisions,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        failure_lines = [
            "=" * 92,
            "STEP 6 FAILED",
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

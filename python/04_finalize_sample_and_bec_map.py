from __future__ import annotations

from pathlib import Path
import re
import sys
import traceback

import pandas as pd


# ============================================================
# PROJECT SETTINGS
# ============================================================
PROJECT_ROOT = Path(r"H:\AIID_DTA_GPR")

AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

AUDIT_DIR.mkdir(parents=True, exist_ok=True)
INTERIM_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

COUNTRY_CANDIDATES_FILE = (
    AUDIT_DIR / "step3_country_sample_candidates.csv"
)

PRODUCT_COVERAGE_FILE = (
    AUDIT_DIR / "step3_product_coverage.csv"
)

DTA_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "dta_world_bank"
    / "DTA_1_Horizontal_Content_v2.xlsx"
)

BEC_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "bec"
    / "HS2007_to_BEC4_correspondence.xls"
)

REPORT_FILE = AUDIT_DIR / "step4_sample_and_bec_audit.txt"

TARGET_SAMPLE_SIZE = 160
START_YEAR = 2007
END_YEAR = 2023

ASEAN_ISO3 = {
    "BRN", "KHM", "IDN", "LAO", "MYS",
    "MMR", "PHL", "SGP", "THA", "VNM",
}

# BEC Rev.4 broad end-use groupings
INTERMEDIATE_BEC = {
    "111", "121", "21", "22",
    "31", "322", "42", "53",
}

CAPITAL_BEC = {
    "41", "521",
}

CONSUMPTION_BEC = {
    "112", "122", "522",
    "61", "62", "63",
}

# BEC categories that cannot be assigned cleanly to one
# SNA end-use class in the baseline.
UNALLOCATED_BEC = {
    "32",   # Processed fuels: includes motor spirit/other
    "321",  # Motor spirit
    "51",   # Passenger motor cars
    "7",    # Goods not elsewhere specified
}


def log(lines: list[str], text: str = "") -> None:
    lines.append(text)


def section(lines: list[str], title: str) -> None:
    log(lines, "")
    log(lines, "=" * 92)
    log(lines, title)
    log(lines, "=" * 92)


def normalize_hs6(value: object) -> str | None:
    """Convert values such as 0101.10 or 10110 into six-digit HS codes."""
    if pd.isna(value):
        return None

    text = str(value).strip()
    digits = re.sub(r"\D", "", text)

    if not digits:
        return None

    if len(digits) > 6:
        return None

    return digits.zfill(6)


def normalize_bec(value: object) -> str | None:
    """Normalize BEC codes while preserving 2- and 3-digit codes."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    text = re.sub(r"[^0-9]", "", text)

    return text or None


def classify_bec_code(code: str) -> str:
    if code in INTERMEDIATE_BEC:
        return "intermediate"

    if code in CAPITAL_BEC:
        return "capital"

    if code in CONSUMPTION_BEC:
        return "consumption"

    if code in UNALLOCATED_BEC:
        return "unallocated"

    return "unknown_bec_code"


def country_exclusion_reason(row: pd.Series) -> str:
    reasons: list[str] = []

    if not bool(row["full_coverage"]):
        reasons.append("incomplete_2007_2023_coverage")

    if bool(row["historical_entity"]):
        reasons.append("historical_entity")

    if (
        bool(row["special_nonstandard_code"])
        and int(row["country_code"]) != 490
    ):
        reasons.append("nonstandard_aggregate_code")

    if not bool(row["analysis_iso3_valid"]):
        reasons.append("invalid_analysis_iso3")

    if not bool(row["dta_iso_available"]):
        reasons.append("not_identified_in_dta_bilateral_universe")

    if bool(row["eligible_for_ranking"]) and not bool(row["selected_final"]):
        reasons.append("below_top_160_preperiod_trade_cutoff")

    return "|".join(reasons) if reasons else "selected"


def build_final_country_sample(
    report: list[str],
) -> pd.DataFrame:
    section(report, "A. FINAL COUNTRY/ECONOMY SAMPLE")

    countries = pd.read_csv(
        COUNTRY_CANDIDATES_FILE,
        dtype={
            "country_iso2": "string",
            "country_iso3": "string",
        },
    )

    bilateral = pd.read_excel(
        DTA_FILE,
        sheet_name="Bilateral Information",
        engine="openpyxl",
        usecols=["iso1", "iso2"],
        dtype="string",
    )

    dta_iso = set(
        bilateral["iso1"].dropna().str.strip()
    ) | set(
        bilateral["iso2"].dropna().str.strip()
    )

    countries["analysis_iso3"] = (
        countries["country_iso3"]
        .astype("string")
        .str.strip()
    )

    countries["analysis_name"] = countries["country_name"]
    countries["taiwan_proxy"] = False

    # CEPII documents BACI code 490 as a reliable Taiwan proxy.
    taiwan_mask = countries["country_code"].eq(490)

    countries.loc[
        taiwan_mask,
        "analysis_iso3",
    ] = "TWN"

    countries.loc[
        taiwan_mask,
        "analysis_name",
    ] = "Taiwan (BACI code 490 proxy)"

    countries.loc[
        taiwan_mask,
        "taiwan_proxy",
    ] = True

    countries["full_coverage"] = (
        countries["years_both_active"]
        .eq(END_YEAR - START_YEAR + 1)
    )

    countries["analysis_iso3_valid"] = (
        countries["analysis_iso3"]
        .fillna("")
        .str.fullmatch(r"[A-Z]{3}")
    )

    countries["dta_iso_available"] = (
        countries["analysis_iso3"].isin(dta_iso)
    )

    countries["eligible_for_ranking"] = (
        countries["full_coverage"]
        & ~countries["historical_entity"].fillna(False)
        & (
            ~countries["special_nonstandard_code"].fillna(False)
            | countries["country_code"].eq(490)
        )
        & countries["analysis_iso3_valid"]
        & countries["dta_iso_available"]
    )

    eligible = (
        countries.loc[
            countries["eligible_for_ranking"]
        ]
        .sort_values(
            [
                "avg_preperiod_trade_1000usd",
                "country_code",
            ],
            ascending=[False, True],
        )
        .copy()
    )

    eligible["final_sample_rank"] = range(
        1,
        len(eligible) + 1,
    )

    selected_codes = set(
        eligible.head(TARGET_SAMPLE_SIZE)["country_code"]
    )

    countries["selected_final"] = (
        countries["country_code"].isin(selected_codes)
    )

    rank_lookup = eligible[
        ["country_code", "final_sample_rank"]
    ]

    countries = countries.merge(
        rank_lookup,
        on="country_code",
        how="left",
        validate="one_to_one",
    )

    countries["exclusion_reason"] = countries.apply(
        country_exclusion_reason,
        axis=1,
    )

    final_sample = (
        countries.loc[
            countries["selected_final"]
        ]
        .sort_values("final_sample_rank")
        .copy()
    )

    if len(final_sample) != TARGET_SAMPLE_SIZE:
        raise ValueError(
            f"Expected {TARGET_SAMPLE_SIZE} economies, "
            f"but selected {len(final_sample)}."
        )

    if final_sample["analysis_iso3"].duplicated().any():
        duplicate_iso = final_sample.loc[
            final_sample["analysis_iso3"].duplicated(
                keep=False
            ),
            [
                "country_code",
                "country_name",
                "analysis_iso3",
            ],
        ]

        raise ValueError(
            "Duplicate analysis ISO3 codes in final sample:\n"
            f"{duplicate_iso.to_string(index=False)}"
        )

    missing_asean = sorted(
        ASEAN_ISO3
        - set(final_sample["analysis_iso3"])
    )

    if missing_asean:
        raise ValueError(
            f"ASEAN economies missing from final sample: "
            f"{missing_asean}"
        )

    coverage_share = final_sample[
        "global_export_share"
    ].sum()

    if coverage_share < 0.99:
        raise ValueError(
            "Final sample covers less than 99% of "
            "global BACI exports."
        )

    final_columns = [
        "final_sample_rank",
        "country_code",
        "country_name",
        "analysis_name",
        "country_iso2",
        "country_iso3",
        "analysis_iso3",
        "taiwan_proxy",
        "years_exporter_active",
        "years_importer_active",
        "years_both_active",
        "avg_preperiod_trade_1000usd",
        "total_exports_1000usd",
        "total_imports_1000usd",
        "global_export_share",
        "dta_iso_available",
    ]

    final_sample[final_columns].to_csv(
        PROCESSED_DIR / "country_sample_160.csv",
        index=False,
        encoding="utf-8-sig",
    )

    countries.to_csv(
        AUDIT_DIR / "step4_country_sample_all_codes.csv",
        index=False,
        encoding="utf-8-sig",
    )

    countries.loc[
        ~countries["selected_final"]
    ].to_csv(
        AUDIT_DIR / "step4_country_exclusions.csv",
        index=False,
        encoding="utf-8-sig",
    )

    log(
        report,
        f"Eligible economies before top-{TARGET_SAMPLE_SIZE} cutoff: "
        f"{len(eligible):,}"
    )
    log(
        report,
        f"Final sample size: {len(final_sample):,}"
    )
    log(
        report,
        "Share of global BACI exports, 2007–2023: "
        f"{coverage_share:.6%}"
    )
    log(
        report,
        "Taiwan proxy included: "
        f"{final_sample['taiwan_proxy'].any()}"
    )
    log(
        report,
        f"Taiwan proxy rank: "
        f"{int(final_sample.loc[
            final_sample['taiwan_proxy'],
            'final_sample_rank'
        ].iloc[0])}"
    )
    log(
        report,
        f"All 10 ASEAN economies included: "
        f"{not missing_asean}"
    )
    log(
        report,
        "Lowest-ranked included economy: "
        f"{final_sample.iloc[-1]['analysis_name']} "
        f"(rank {int(final_sample.iloc[-1]['final_sample_rank'])})"
    )

    return final_sample


def build_bec_map(
    report: list[str],
) -> pd.DataFrame:
    section(report, "B. HS2007 → BEC REV.4 CLEAN MAP")

    raw = pd.read_excel(
        BEC_FILE,
        sheet_name="HS2007-BEC",
        header=None,
        engine="xlrd",
    )

    mapping = raw.iloc[8:, [4, 5]].copy()
    mapping.columns = ["hs_raw", "bec_raw"]

    mapping["hs6"] = mapping["hs_raw"].map(
        normalize_hs6
    )

    mapping["bec4"] = mapping["bec_raw"].map(
        normalize_bec
    )

    mapping = mapping.dropna(
        subset=["hs6", "bec4"]
    )

    mapping = mapping[
        mapping["hs6"].str.fullmatch(r"\d{6}")
    ].copy()

    mapping = mapping.drop_duplicates(
        subset=["hs6", "bec4"]
    )

    mapping["broad_end_use"] = mapping[
        "bec4"
    ].map(classify_bec_code)

    grouped_rows: list[dict[str, object]] = []

    for hs6, group in mapping.groupby(
        "hs6",
        sort=True,
    ):
        bec_codes = sorted(set(group["bec4"]))
        end_uses = sorted(
            set(group["broad_end_use"])
        )

        if len(end_uses) == 1:
            only_group = end_uses[0]

            if only_group in {
                "intermediate",
                "capital",
                "consumption",
            }:
                final_end_use = only_group

                if len(bec_codes) == 1:
                    mapping_status = "unique_exact"
                else:
                    mapping_status = (
                        "multiple_bec_same_broad_end_use"
                    )
            else:
                final_end_use = "unallocated"
                mapping_status = "unallocated_bec_category"
        else:
            final_end_use = "ambiguous"
            mapping_status = "cross_end_use_ambiguity"

        grouped_rows.append(
            {
                "hs6": hs6,
                "bec_codes": "|".join(bec_codes),
                "number_of_bec_codes": len(bec_codes),
                "broad_end_uses": "|".join(end_uses),
                "number_of_broad_end_uses": len(end_uses),
                "final_end_use": final_end_use,
                "mapping_status": mapping_status,
            }
        )

    clean_map = pd.DataFrame(grouped_rows)

    product = pd.read_csv(
        PRODUCT_COVERAGE_FILE,
        dtype={"hs6": "string"},
    )

    product["hs6"] = (
        product["hs6"]
        .astype("string")
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(6)
    )

    observed = product.merge(
        clean_map,
        on="hs6",
        how="left",
        validate="one_to_one",
    )

    observed["mapping_status"] = (
        observed["mapping_status"]
        .fillna("not_in_official_correspondence")
    )

    observed["final_end_use"] = (
        observed["final_end_use"]
        .fillna("unmapped")
    )

    total_trade_value = observed[
        "total_trade_value_1000usd"
    ].sum()

    total_trade_rows = observed[
        "total_trade_rows"
    ].sum()

    summary = (
        observed.groupby(
            ["final_end_use", "mapping_status"],
            dropna=False,
        )
        .agg(
            number_of_hs6=("hs6", "nunique"),
            total_trade_rows=(
                "total_trade_rows",
                "sum",
            ),
            total_trade_value_1000usd=(
                "total_trade_value_1000usd",
                "sum",
            ),
        )
        .reset_index()
    )

    summary["share_of_trade_rows"] = (
        summary["total_trade_rows"]
        / total_trade_rows
    )

    summary["share_of_trade_value"] = (
        summary["total_trade_value_1000usd"]
        / total_trade_value
    )

    clean_map.to_csv(
        INTERIM_DIR / "hs07_bec4_clean_map.csv",
        index=False,
        encoding="utf-8-sig",
    )

    observed.to_csv(
        AUDIT_DIR / "step4_bec_observed_product_audit.csv",
        index=False,
        encoding="utf-8-sig",
    )

    summary.to_csv(
        AUDIT_DIR / "step4_bec_mapping_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    observed.loc[
        observed["mapping_status"].isin(
            [
                "cross_end_use_ambiguity",
                "not_in_official_correspondence",
                "unallocated_bec_category",
            ]
        )
    ].sort_values(
        "total_trade_value_1000usd",
        ascending=False,
    ).to_csv(
        AUDIT_DIR / "step4_bec_problem_codes.csv",
        index=False,
        encoding="utf-8-sig",
    )

    cross_ambiguous = observed[
        observed["mapping_status"].eq(
            "cross_end_use_ambiguity"
        )
    ]

    unmapped = observed[
        observed["mapping_status"].eq(
            "not_in_official_correspondence"
        )
    ]

    unallocated = observed[
        observed["mapping_status"].eq(
            "unallocated_bec_category"
        )
    ]

    log(
        report,
        f"Official mapping rows after cleaning: "
        f"{len(mapping):,}"
    )
    log(
        report,
        f"Unique official HS2007 codes: "
        f"{len(clean_map):,}"
    )
    log(
        report,
        "Cross-end-use ambiguous observed HS6 codes: "
        f"{len(cross_ambiguous):,}; "
        f"trade-value share="
        f"{cross_ambiguous[
            'total_trade_value_1000usd'
        ].sum() / total_trade_value:.6%}"
    )
    log(
        report,
        "Unallocated BEC-category observed HS6 codes: "
        f"{len(unallocated):,}; "
        f"trade-value share="
        f"{unallocated[
            'total_trade_value_1000usd'
        ].sum() / total_trade_value:.6%}"
    )
    log(
        report,
        "Observed HS6 codes absent from official correspondence: "
        f"{len(unmapped):,}; "
        f"trade-value share="
        f"{unmapped[
            'total_trade_value_1000usd'
        ].sum() / total_trade_value:.6%}"
    )

    if not unmapped.empty:
        log(report, "Unmapped observed codes:")

        for _, row in unmapped.sort_values(
            "total_trade_value_1000usd",
            ascending=False,
        ).iterrows():
            log(
                report,
                "  "
                f"{row['hs6']} | "
                f"{row['description']} | "
                f"trade-value share="
                f"{row['total_trade_value_1000usd'] / total_trade_value:.6%}"
            )

    return observed


def main() -> None:
    required_files = [
        COUNTRY_CANDIDATES_FILE,
        PRODUCT_COVERAGE_FILE,
        DTA_FILE,
        BEC_FILE,
    ]

    missing_files = [
        file for file in required_files
        if not file.exists()
    ]

    if missing_files:
        missing_text = "\n".join(
            str(file) for file in missing_files
        )
        raise FileNotFoundError(
            "Missing required files:\n"
            f"{missing_text}"
        )

    report: list[str] = [
        "=" * 92,
        "AIID DTA–GPR PROJECT — STEP 4 SAMPLE AND BEC AUDIT",
        "=" * 92,
        f"Project root: {PROJECT_ROOT}",
        (
            "This step creates the final 160-economy sample "
            "and a conservative HS2007–BEC Rev.4 map."
        ),
    ]

    build_final_country_sample(report)
    build_bec_map(report)

    section(report, "C. BASELINE CLASSIFICATION RULE")

    log(
        report,
        "Keep as intermediate goods only HS6 codes with "
        "final_end_use='intermediate'."
    )
    log(
        report,
        "Keep as final-consumption goods only HS6 codes with "
        "final_end_use='consumption'."
    )
    log(
        report,
        "Do not assign cross-end-use ambiguous, unallocated, "
        "or unmapped codes to either group in the baseline."
    )
    log(
        report,
        "Code 271000 is expected to remain unmapped because it "
        "aggregates several detailed HS2007 petroleum subheadings "
        "with different BEC treatment."
    )
    log(
        report,
        "A later robustness test will use HS2012 data for "
        "2012–2023 and/or exclude energy products."
    )

    section(report, "D. OUTPUT FILES")

    output_files = [
        "data/processed/country_sample_160.csv",
        "data/interim/hs07_bec4_clean_map.csv",
        "outputs/audit/step4_country_sample_all_codes.csv",
        "outputs/audit/step4_country_exclusions.csv",
        "outputs/audit/step4_bec_observed_product_audit.csv",
        "outputs/audit/step4_bec_mapping_summary.csv",
        "outputs/audit/step4_bec_problem_codes.csv",
        "outputs/audit/step4_sample_and_bec_audit.txt",
    ]

    for file in output_files:
        log(report, file)

    section(report, "E. NEXT ACTION")

    log(
        report,
        "Send step4_sample_and_bec_audit.txt, "
        "country_sample_160.csv, step4_bec_mapping_summary.csv, "
        "and step4_bec_problem_codes.csv to ChatGPT."
    )
    log(
        report,
        "Do not build the full intermediate-goods panel until "
        "these outputs have been reviewed."
    )

    REPORT_FILE.write_text(
        "\n".join(report),
        encoding="utf-8",
    )

    print("\n".join(report))
    print("")
    print(f"Report saved to: {REPORT_FILE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        error_lines = [
            "=" * 92,
            "STEP 4 FAILED",
            "=" * 92,
            f"{type(error).__name__}: {error}",
            "",
            traceback.format_exc(),
        ]

        REPORT_FILE.write_text(
            "\n".join(error_lines),
            encoding="utf-8",
        )

        print("\n".join(error_lines))
        sys.exit(1)

from __future__ import annotations

from pathlib import Path
import sys
import traceback

import pandas as pd


# ============================================================
# PROJECT PATH
# ============================================================
PROJECT_ROOT = Path(r"H:\AIID_DTA_GPR")

DTA_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "dta_world_bank"
    / "DTA_1_Horizontal_Content_v2.xlsx"
)

AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_FILE = AUDIT_DIR / "step2b_dta_audit.txt"


def normalize_rta_id(value: object) -> str | None:
    """Convert WTO RTA IDs to stable strings such as '129' or '999A3'."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return text or None


def add_line(report: list[str], text: str = "") -> None:
    report.append(text)


def add_section(report: list[str], title: str) -> None:
    add_line(report, "")
    add_line(report, "=" * 88)
    add_line(report, title)
    add_line(report, "=" * 88)


def main() -> None:
    report: list[str] = []

    add_line(report, "=" * 88)
    add_line(
        report,
        "AIID DTA–GPR PROJECT — STEP 2B CORRECTED DTA AUDIT"
    )
    add_line(report, "=" * 88)
    add_line(report, f"Project root: {PROJECT_ROOT}")
    add_line(
        report,
        "This script reads the raw DTA workbook only. "
        "It does not modify the original file."
    )

    if not DTA_FILE.exists():
        add_line(report, f"ERROR: File not found: {DTA_FILE}")
        REPORT_FILE.write_text(
            "\n".join(report),
            encoding="utf-8",
        )
        print("\n".join(report))
        sys.exit(1)

    # ========================================================
    # 1. Read sheets
    # ========================================================
    add_section(report, "A. READ DTA SHEETS")

    agreements = pd.read_excel(
        DTA_FILE,
        sheet_name="Agreements",
        engine="openpyxl",
    )

    wto_plus_le = pd.read_excel(
        DTA_FILE,
        sheet_name="WTO+ LE",
        engine="openpyxl",
    )

    wto_x_le = pd.read_excel(
        DTA_FILE,
        sheet_name="WTO-X LE",
        engine="openpyxl",
    )

    bilateral = pd.read_excel(
        DTA_FILE,
        sheet_name="Bilateral Information",
        engine="openpyxl",
    )

    add_line(
        report,
        f"Agreements: {len(agreements):,} rows"
    )
    add_line(
        report,
        f"WTO+ LE: {len(wto_plus_le):,} rows"
    )
    add_line(
        report,
        f"WTO-X LE: {len(wto_x_le):,} rows"
    )
    add_line(
        report,
        f"Bilateral Information: {len(bilateral):,} rows"
    )

    # ========================================================
    # 2. Normalize identifiers
    # ========================================================
    agreements["RTAID_norm"] = (
        agreements["RTA ID"].map(normalize_rta_id)
    )

    wto_plus_le["RTAID_norm"] = (
        wto_plus_le["RTAID"].map(normalize_rta_id)
    )

    wto_x_le["RTAID_norm"] = (
        wto_x_le["RTAID"].map(normalize_rta_id)
    )

    if agreements["RTAID_norm"].duplicated().any():
        raise ValueError(
            "RTA ID is not unique in the Agreements sheet."
        )

    if wto_plus_le["RTAID_norm"].duplicated().any():
        raise ValueError(
            "RTAID is not unique in the WTO+ LE sheet."
        )

    if wto_x_le["RTAID_norm"].duplicated().any():
        raise ValueError(
            "RTAID is not unique in the WTO-X LE sheet."
        )

    add_line(
        report,
        "RTA ID uniqueness check: PASS in all three sheets"
    )

    # ========================================================
    # 3. Compute agreement-level depth
    # ========================================================
    add_section(
        report,
        "B. CONSTRUCT LEGALLY ENFORCEABLE DEPTH"
    )

    plus_id_columns = {
        "RTAID",
        "WBID",
        "Agreement",
        "RTAID_norm",
    }

    x_id_columns = {
        "RTAID",
        "WBID",
        "Agreement",
        "RTAID_norm",
    }

    plus_provisions = [
        column
        for column in wto_plus_le.columns
        if column not in plus_id_columns
    ]

    x_provisions = [
        column
        for column in wto_x_le.columns
        if column not in x_id_columns
    ]

    add_line(
        report,
        f"WTO+ provision areas: {len(plus_provisions)}"
    )
    add_line(
        report,
        f"WTO-X provision areas: {len(x_provisions)}"
    )
    add_line(
        report,
        "Total policy areas: "
        f"{len(plus_provisions) + len(x_provisions)}"
    )

    allowed_values = {0, 1, 2}

    for label, frame, provisions in [
        ("WTO+ LE", wto_plus_le, plus_provisions),
        ("WTO-X LE", wto_x_le, x_provisions),
    ]:
        observed_values = {
            value
            for value in pd.unique(
                frame[provisions].to_numpy().ravel()
            )
            if pd.notna(value)
        }

        invalid_values = sorted(
            observed_values - allowed_values
        )

        add_line(
            report,
            f"{label} invalid coding values: {invalid_values}"
        )

        if invalid_values:
            raise ValueError(
                f"Unexpected coding values in {label}: "
                f"{invalid_values}"
            )

    plus_depth = wto_plus_le[
        [
            "RTAID_norm",
            "WBID",
            "Agreement",
        ]
    ].copy()

    plus_depth = plus_depth.rename(
        columns={
            "WBID": "content_WBID_plus",
            "Agreement": "content_name_plus",
        }
    )

    plus_depth["wto_plus_depth_strict"] = (
        wto_plus_le[plus_provisions]
        .eq(2)
        .sum(axis=1)
    )

    plus_depth["wto_plus_depth_broad"] = (
        wto_plus_le[plus_provisions]
        .isin([1, 2])
        .sum(axis=1)
    )

    x_depth = wto_x_le[
        [
            "RTAID_norm",
            "WBID",
            "Agreement",
        ]
    ].copy()

    x_depth = x_depth.rename(
        columns={
            "WBID": "content_WBID_x",
            "Agreement": "content_name_x",
        }
    )

    x_depth["wto_x_depth_strict"] = (
        wto_x_le[x_provisions]
        .eq(2)
        .sum(axis=1)
    )

    x_depth["wto_x_depth_broad"] = (
        wto_x_le[x_provisions]
        .isin([1, 2])
        .sum(axis=1)
    )

    content_depth = plus_depth.merge(
        x_depth,
        on="RTAID_norm",
        how="outer",
        validate="one_to_one",
    )

    content_depth["depth_strict"] = (
        content_depth[
            [
                "wto_plus_depth_strict",
                "wto_x_depth_strict",
            ]
        ]
        .fillna(0)
        .sum(axis=1)
        .astype(int)
    )

    content_depth["depth_broad"] = (
        content_depth[
            [
                "wto_plus_depth_broad",
                "wto_x_depth_broad",
            ]
        ]
        .fillna(0)
        .sum(axis=1)
        .astype(int)
    )

    # ========================================================
    # 4. Reconcile content IDs with the Agreements sheet
    # ========================================================
    add_section(
        report,
        "C. RECONCILE RTAID AND WBID"
    )

    agreement_lookup = agreements[
        [
            "RTAID_norm",
            "WB ID",
            "RTA ID",
            "Agreement",
            "Status",
            "Date of Entry into Force (G)",
            "Date of Entry into Force (S)",
            "Inactive Date",
        ]
    ].copy()

    agreement_lookup = agreement_lookup.rename(
        columns={
            "WB ID": "agreement_WBID",
            "RTA ID": "agreement_RTAID",
            "Agreement": "agreement_name",
        }
    )

    depth = agreement_lookup.merge(
        content_depth,
        on="RTAID_norm",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    depth["has_content"] = depth["_merge"].eq("both")

    depth["wbid_mismatch_plus"] = (
        depth["has_content"]
        & depth["content_WBID_plus"].notna()
        & (
            depth["agreement_WBID"]
            != depth["content_WBID_plus"]
        )
    )

    depth["wbid_mismatch_x"] = (
        depth["has_content"]
        & depth["content_WBID_x"].notna()
        & (
            depth["agreement_WBID"]
            != depth["content_WBID_x"]
        )
    )

    depth["name_mismatch_plus"] = (
        depth["has_content"]
        & depth["content_name_plus"].notna()
        & (
            depth["agreement_name"]
            != depth["content_name_plus"]
        )
    )

    depth["name_mismatch_x"] = (
        depth["has_content"]
        & depth["content_name_x"].notna()
        & (
            depth["agreement_name"]
            != depth["content_name_x"]
        )
    )

    mismatches = depth[
        depth[
            [
                "wbid_mismatch_plus",
                "wbid_mismatch_x",
                "name_mismatch_plus",
                "name_mismatch_x",
            ]
        ].any(axis=1)
    ].copy()

    missing_content = depth[
        ~depth["has_content"]
    ].copy()

    add_line(
        report,
        f"Agreements matched to content by RTAID: "
        f"{depth['has_content'].sum():,}"
    )

    add_line(
        report,
        f"Agreements without content coding: "
        f"{len(missing_content):,}"
    )

    add_line(
        report,
        f"Identifier/name mismatch rows: "
        f"{len(mismatches):,}"
    )

    if not mismatches.empty:
        add_line(
            report,
            "Mismatch details:"
        )

        for _, row in mismatches.iterrows():
            add_line(
                report,
                "  "
                f"RTAID={row['RTAID_norm']}; "
                f"agreement_WBID={row['agreement_WBID']}; "
                f"content_WBID_plus="
                f"{row['content_WBID_plus']}; "
                f"content_WBID_x="
                f"{row['content_WBID_x']}; "
                f"name={row['agreement_name']}"
            )

    # Final WBID must come from Agreements, because it links
    # correctly to Bilateral Information.
    output_columns = [
        "RTAID_norm",
        "agreement_RTAID",
        "agreement_WBID",
        "agreement_name",
        "Status",
        "Date of Entry into Force (G)",
        "Date of Entry into Force (S)",
        "Inactive Date",
        "has_content",
        "wto_plus_depth_strict",
        "wto_x_depth_strict",
        "depth_strict",
        "wto_plus_depth_broad",
        "wto_x_depth_broad",
        "depth_broad",
        "content_WBID_plus",
        "content_WBID_x",
        "wbid_mismatch_plus",
        "wbid_mismatch_x",
    ]

    depth[output_columns].to_csv(
        AUDIT_DIR
        / "step2b_dta_depth_summary_corrected.csv",
        index=False,
        encoding="utf-8-sig",
    )

    missing_content[output_columns].to_csv(
        AUDIT_DIR
        / "step2b_dta_agreements_missing_content.csv",
        index=False,
        encoding="utf-8-sig",
    )

    mismatches[output_columns].to_csv(
        AUDIT_DIR
        / "step2b_dta_identifier_mismatches.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # ========================================================
    # 5. Audit Bilateral Information
    # ========================================================
    add_section(
        report,
        "D. AUDIT BILATERAL INFORMATION"
    )

    add_line(
        report,
        f"Rows: {len(bilateral):,}"
    )
    add_line(
        report,
        f"Year range: "
        f"{bilateral['year'].min()} to "
        f"{bilateral['year'].max()}"
    )
    add_line(
        report,
        f"Rows with missing year: "
        f"{bilateral['year'].isna().sum():,}"
    )
    add_line(
        report,
        f"Exact duplicate rows: "
        f"{bilateral.duplicated().sum():,}"
    )

    key_columns = [
        "iso1",
        "iso2",
        "WBID",
        "year",
    ]

    add_line(
        report,
        "Duplicate iso1–iso2–WBID–year keys: "
        f"{bilateral.duplicated(key_columns).sum():,}"
    )

    bilateral_missing_year = bilateral[
        bilateral["year"].isna()
    ].copy()

    bilateral_missing_year.to_csv(
        AUDIT_DIR
        / "step2b_dta_bilateral_missing_year.csv",
        index=False,
        encoding="utf-8-sig",
    )

    sample = bilateral[
        bilateral["year"].between(
            2007,
            2023,
            inclusive="both",
        )
    ].copy()

    add_line(
        report,
        f"Rows in 2007–2023: {len(sample):,}"
    )
    add_line(
        report,
        "Unique agreements in 2007–2023: "
        f"{sample['WBID'].nunique():,}"
    )
    add_line(
        report,
        "Unique directed country pairs in 2007–2023: "
        f"{sample[['iso1', 'iso2']].drop_duplicates().shape[0]:,}"
    )

    missing_wbids = sorted(
        set(sample["WBID"].dropna().astype(int))
        - set(depth["agreement_WBID"].dropna().astype(int))
    )

    add_line(
        report,
        "WBIDs in Bilateral Information not found in "
        f"Agreements: {missing_wbids}"
    )

    content_status = depth[
        [
            "agreement_WBID",
            "has_content",
            "depth_strict",
            "depth_broad",
        ]
    ].copy()

    sample_check = sample.merge(
        content_status,
        left_on="WBID",
        right_on="agreement_WBID",
        how="left",
        validate="many_to_one",
    )

    add_line(
        report,
        "2007–2023 bilateral rows linked to an agreement: "
        f"{sample_check['agreement_WBID'].notna().sum():,} "
        f"of {len(sample_check):,}"
    )

    add_line(
        report,
        "2007–2023 bilateral rows whose active agreement "
        "has no content coding: "
        f"{(
            sample_check['agreement_WBID'].notna()
            & ~sample_check['has_content'].fillna(False)
        ).sum():,}"
    )

    # ========================================================
    # 6. Final
    # ========================================================
    add_section(report, "E. FINAL RESULT")

    add_line(
        report,
        "Corrected DTA audit completed successfully."
    )
    add_line(
        report,
        "The agreement-content merge is performed by WTO RTAID, "
        "not by WBID plus agreement name."
    )
    add_line(
        report,
        "The final WBID is taken from the Agreements sheet "
        "for later linkage to Bilateral Information."
    )

    add_line(
        report,
        "Files created:"
    )
    add_line(
        report,
        "  outputs/audit/"
        "step2b_dta_depth_summary_corrected.csv"
    )
    add_line(
        report,
        "  outputs/audit/"
        "step2b_dta_agreements_missing_content.csv"
    )
    add_line(
        report,
        "  outputs/audit/"
        "step2b_dta_identifier_mismatches.csv"
    )
    add_line(
        report,
        "  outputs/audit/"
        "step2b_dta_bilateral_missing_year.csv"
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
        error_report = [
            "=" * 88,
            "STEP 2B FAILED",
            "=" * 88,
            f"{type(error).__name__}: {error}",
            "",
            traceback.format_exc(),
        ]

        REPORT_FILE.write_text(
            "\n".join(error_report),
            encoding="utf-8",
        )

        print("\n".join(error_report))
        sys.exit(1)

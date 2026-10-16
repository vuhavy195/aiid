from __future__ import annotations

from pathlib import Path
import re
import sys
import traceback

import pandas as pd


# ============================================================
# PROJECT PATH — already set for your computer
# ============================================================
PROJECT_ROOT = Path(r"H:\AIID_DTA_GPR")

RAW_DIR = PROJECT_ROOT / "data" / "raw"
AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_FILE = AUDIT_DIR / "step2_reference_audit.txt"


# ============================================================
# INPUT FILES
# ============================================================
FILES = {
    "country": (
        RAW_DIR
        / "baci_hs07_v202601"
        / "country_codes_V202601.csv"
    ),
    "product": (
        RAW_DIR
        / "baci_hs07_v202601"
        / "product_codes_HS07_V202601.csv"
    ),
    "bec": (
        RAW_DIR
        / "bec"
        / "HS2007_to_BEC4_correspondence.xls"
    ),
    "dta": (
        RAW_DIR
        / "dta_world_bank"
        / "DTA_1_Horizontal_Content_v2.xlsx"
    ),
    "gpr": (
        RAW_DIR
        / "gpr"
        / "GPR_monthly_downloaded_2026-07-26.xls"
    ),
    "wto": (
        RAW_DIR
        / "wto_rta"
        / "WTO_all_RTAs.xlsx"
    ),
}


def line(report: list[str], text: str = "") -> None:
    report.append(text)


def section(report: list[str], title: str) -> None:
    line(report, "")
    line(report, "=" * 88)
    line(report, title)
    line(report, "=" * 88)


def clean_filename(value: object) -> str:
    text = str(value)
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", text)
    return text.strip("_")[:80] or "sheet"


def readable_error(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"


def check_required_files(report: list[str]) -> bool:
    section(report, "A. REQUIRED FILE CHECK")

    all_found = True

    for name, path in FILES.items():
        exists = path.exists()
        size_mb = (
            path.stat().st_size / 1024 / 1024
            if exists
            else None
        )

        status = "FOUND" if exists else "MISSING"
        size_text = (
            f"{size_mb:,.2f} MB"
            if size_mb is not None
            else "N/A"
        )

        line(
            report,
            f"{name.upper():10s} | {status:7s} | "
            f"{size_text:>12s} | {path}"
        )

        if not exists:
            all_found = False

    return all_found


def audit_country_metadata(report: list[str]) -> None:
    section(report, "B. BACI COUNTRY METADATA")

    path = FILES["country"]

    df = pd.read_csv(
        path,
        dtype={
            "country_code": "string",
            "country_name": "string",
            "country_iso2": "string",
            "country_iso3": "string",
        },
        keep_default_na=False,
    )

    expected_columns = [
        "country_code",
        "country_name",
        "country_iso2",
        "country_iso3",
    ]

    line(report, f"Rows: {len(df):,}")
    line(report, f"Columns: {list(df.columns)}")
    line(
        report,
        "Expected columns present: "
        f"{set(expected_columns).issubset(df.columns)}"
    )

    duplicate_code = df[
        df["country_code"].duplicated(keep=False)
    ].copy()

    duplicate_iso3 = df[
        df["country_iso3"].duplicated(keep=False)
        & df["country_iso3"].ne("")
    ].copy()

    missing_iso2 = df[
        df["country_iso2"].eq("")
    ].copy()

    invalid_iso3 = df[
        ~df["country_iso3"].str.fullmatch(
            r"[A-Z]{3}",
            na=False,
        )
    ].copy()

    historical_names = df[
        df["country_name"].str.contains(
            r"\(\.\.\.",
            regex=True,
            na=False,
        )
    ].copy()

    line(
        report,
        f"Duplicate country_code rows: "
        f"{len(duplicate_code):,}"
    )
    line(
        report,
        f"Rows involved in duplicated ISO3 codes: "
        f"{len(duplicate_iso3):,}"
    )
    line(
        report,
        f"Rows with blank ISO2: {len(missing_iso2):,}"
    )
    line(
        report,
        f"Rows with non-standard ISO3 format: "
        f"{len(invalid_iso3):,}"
    )
    line(
        report,
        f"Historical entities identified by '(...)': "
        f"{len(historical_names):,}"
    )

    issues = pd.concat(
        [
            duplicate_code.assign(issue="duplicate_country_code"),
            duplicate_iso3.assign(issue="duplicate_iso3"),
            missing_iso2.assign(issue="blank_iso2"),
            invalid_iso3.assign(issue="nonstandard_iso3"),
            historical_names.assign(issue="historical_entity"),
        ],
        ignore_index=True,
    ).drop_duplicates()

    issues.to_csv(
        AUDIT_DIR / "step2_country_metadata_issues.csv",
        index=False,
        encoding="utf-8-sig",
    )

    line(
        report,
        "Saved: outputs/audit/"
        "step2_country_metadata_issues.csv"
    )


def audit_product_metadata(report: list[str]) -> None:
    section(report, "C. BACI HS2007 PRODUCT METADATA")

    path = FILES["product"]

    df = pd.read_csv(
        path,
        dtype={
            "code": "string",
            "description": "string",
        },
        keep_default_na=False,
    )

    line(report, f"Rows: {len(df):,}")
    line(report, f"Columns: {list(df.columns)}")

    duplicate_code = df[
        df["code"].duplicated(keep=False)
    ].copy()

    invalid_code = df[
        ~df["code"].str.fullmatch(
            r"\d{6}",
            na=False,
        )
    ].copy()

    missing_description = df[
        df["description"].eq("")
    ].copy()

    special_999999 = df[
        df["code"].eq("999999")
    ].copy()

    line(
        report,
        f"Duplicate HS6 rows: {len(duplicate_code):,}"
    )
    line(
        report,
        f"Invalid non-six-digit HS6 rows: "
        f"{len(invalid_code):,}"
    )
    line(
        report,
        f"Blank descriptions: {len(missing_description):,}"
    )
    line(
        report,
        f"Special code 999999 present: "
        f"{not special_999999.empty}"
    )
    line(
        report,
        "Leading-zero test: "
        f"{df['code'].str.startswith('0').any()}"
    )

    issues = pd.concat(
        [
            duplicate_code.assign(issue="duplicate_hs6"),
            invalid_code.assign(issue="invalid_hs6"),
            missing_description.assign(
                issue="blank_description"
            ),
            special_999999.assign(
                issue="special_unspecified_code"
            ),
        ],
        ignore_index=True,
    ).drop_duplicates()

    issues.to_csv(
        AUDIT_DIR / "step2_product_metadata_issues.csv",
        index=False,
        encoding="utf-8-sig",
    )

    line(
        report,
        "Saved: outputs/audit/"
        "step2_product_metadata_issues.csv"
    )


def read_excel_inventory(
    path: Path,
    engine: str,
    source_label: str,
    report: list[str],
    preview_rows: int = 20,
    preview_cols: int = 15,
) -> dict[str, pd.DataFrame]:
    excel = pd.ExcelFile(path, engine=engine)

    line(
        report,
        f"{source_label} sheet names: "
        f"{excel.sheet_names}"
    )

    sheets: dict[str, pd.DataFrame] = {}

    for sheet_name in excel.sheet_names:
        raw = pd.read_excel(
            path,
            sheet_name=sheet_name,
            header=None,
            engine=engine,
        )

        sheets[sheet_name] = raw

        nonempty_rows = int(
            raw.dropna(how="all").shape[0]
        )
        nonempty_cols = int(
            raw.dropna(how="all", axis=1).shape[1]
        )

        line(
            report,
            f"  {sheet_name!r}: "
            f"raw shape={raw.shape}, "
            f"nonempty rows={nonempty_rows:,}, "
            f"nonempty cols={nonempty_cols:,}"
        )

        preview = raw.iloc[
            :preview_rows,
            :preview_cols,
        ].copy()

        preview_name = clean_filename(
            f"step2_{source_label}_{sheet_name}_preview"
        )

        preview.to_csv(
            AUDIT_DIR / f"{preview_name}.csv",
            index=False,
            header=False,
            encoding="utf-8-sig",
        )

    return sheets


def audit_bec(report: list[str]) -> None:
    section(
        report,
        "D. HS2007 → BEC REV.4 CORRESPONDENCE"
    )

    path = FILES["bec"]

    try:
        sheets = read_excel_inventory(
            path=path,
            engine="xlrd",
            source_label="BEC",
            report=report,
            preview_rows=30,
            preview_cols=15,
        )

        for sheet_name, raw in sheets.items():
            text = raw.astype("string").fillna("")

            contains_hs = text.apply(
                lambda col: col.str.contains(
                    "HS",
                    case=False,
                    regex=False,
                ).any()
            ).any()

            contains_bec = text.apply(
                lambda col: col.str.contains(
                    "BEC",
                    case=False,
                    regex=False,
                ).any()
            ).any()

            line(
                report,
                f"  {sheet_name!r}: "
                f"contains 'HS'={contains_hs}; "
                f"contains 'BEC'={contains_bec}"
            )

        line(
            report,
            "BEC workbook opened successfully with xlrd."
        )

    except Exception as error:
        line(
            report,
            "BEC READ FAILED: "
            f"{readable_error(error)}"
        )
        line(
            report,
            "Install xlrd and run again: "
            "py -m pip install xlrd==2.0.1"
        )


def audit_gpr(report: list[str]) -> None:
    section(report, "E. GEOPOLITICAL RISK WORKBOOK")

    path = FILES["gpr"]

    try:
        sheets = read_excel_inventory(
            path=path,
            engine="xlrd",
            source_label="GPR",
            report=report,
            preview_rows=25,
            preview_cols=20,
        )

        keyword_pattern = re.compile(
            r"date|month|gpr|threat|act",
            flags=re.IGNORECASE,
        )

        for sheet_name, raw in sheets.items():
            preview_text = (
                raw.iloc[:40, :30]
                .astype("string")
                .fillna("")
            )

            matches: list[str] = []

            for value in preview_text.to_numpy().ravel():
                value_text = str(value)

                if keyword_pattern.search(value_text):
                    matches.append(value_text)

            unique_matches = list(
                dict.fromkeys(matches)
            )[:20]

            line(
                report,
                f"  {sheet_name!r} keyword matches: "
                f"{unique_matches}"
            )

        line(
            report,
            "GPR workbook opened successfully with xlrd."
        )

    except Exception as error:
        line(
            report,
            "GPR READ FAILED: "
            f"{readable_error(error)}"
        )
        line(
            report,
            "Install xlrd and run again: "
            "py -m pip install xlrd==2.0.1"
        )


def audit_dta(report: list[str]) -> None:
    section(
        report,
        "F. WORLD BANK DEEP TRADE AGREEMENTS"
    )

    path = FILES["dta"]
    excel = pd.ExcelFile(path, engine="openpyxl")

    line(report, f"Sheets: {excel.sheet_names}")

    expected_sheets = [
        "read me",
        "WTO+ AC",
        "WTO-X AC",
        "WTO+ LE",
        "WTO-X LE",
        "Agreements",
        "Bilateral Information",
    ]

    missing_sheets = [
        sheet
        for sheet in expected_sheets
        if sheet not in excel.sheet_names
    ]

    line(
        report,
        f"Missing expected sheets: {missing_sheets}"
    )

    sheet_shapes: dict[str, tuple[int, int]] = {}

    for sheet in expected_sheets:
        if sheet not in excel.sheet_names:
            continue

        df = pd.read_excel(
            path,
            sheet_name=sheet,
            engine="openpyxl",
        )

        sheet_shapes[sheet] = df.shape
        line(
            report,
            f"  {sheet!r}: {df.shape[0]:,} rows × "
            f"{df.shape[1]:,} columns"
        )

    agreements = pd.read_excel(
        path,
        sheet_name="Agreements",
        engine="openpyxl",
    )

    bilateral = pd.read_excel(
        path,
        sheet_name="Bilateral Information",
        engine="openpyxl",
    )

    wto_plus_le = pd.read_excel(
        path,
        sheet_name="WTO+ LE",
        engine="openpyxl",
    )

    wto_x_le = pd.read_excel(
        path,
        sheet_name="WTO-X LE",
        engine="openpyxl",
    )

    line(
        report,
        f"Agreements: {len(agreements):,}"
    )
    line(
        report,
        "Agreement status counts: "
        f"{agreements['Status'].value_counts(dropna=False).to_dict()}"
    )
    line(
        report,
        f"Unique WB IDs in Agreements: "
        f"{agreements['WB ID'].nunique(dropna=True):,}"
    )

    content_ids = set(
        wto_plus_le["WBID"]
        .dropna()
        .astype(int)
    )

    agreement_ids = set(
        agreements["WB ID"]
        .dropna()
        .astype(int)
    )

    missing_content_ids = sorted(
        agreement_ids - content_ids
    )

    missing_content = agreements[
        agreements["WB ID"].isin(
            missing_content_ids
        )
    ].copy()

    line(
        report,
        "Agreements without horizontal-content coding: "
        f"{len(missing_content):,}"
    )

    missing_content.to_csv(
        AUDIT_DIR
        / "step2_dta_agreements_missing_content.csv",
        index=False,
        encoding="utf-8-sig",
    )

    le_frames = []

    for source_name, source_df in [
        ("WTO_plus", wto_plus_le),
        ("WTO_X", wto_x_le),
    ]:
        id_columns = [
            col
            for col in ["RTAID", "WBID", "Agreement"]
            if col in source_df.columns
        ]

        provision_columns = [
            col
            for col in source_df.columns
            if col not in id_columns
        ]

        invalid_values = sorted({
            value
            for value in pd.unique(
                source_df[provision_columns]
                .to_numpy()
                .ravel()
            )
            if pd.notna(value)
            and value not in (0, 1, 2)
        })

        line(
            report,
            f"{source_name} LE provision columns: "
            f"{len(provision_columns):,}"
        )
        line(
            report,
            f"{source_name} invalid LE coding values: "
            f"{invalid_values}"
        )

        temp = source_df[
            ["WBID", "Agreement"]
        ].copy()

        temp[f"{source_name}_LE2_count"] = (
            source_df[provision_columns]
            .eq(2)
            .sum(axis=1)
        )

        temp[f"{source_name}_LE1or2_count"] = (
            source_df[provision_columns]
            .isin([1, 2])
            .sum(axis=1)
        )

        le_frames.append(temp)

    depth_summary = le_frames[0].merge(
        le_frames[1],
        on=["WBID", "Agreement"],
        how="outer",
        validate="one_to_one",
    )

    depth_summary["depth_strict_LE2"] = (
        depth_summary[
            [
                "WTO_plus_LE2_count",
                "WTO_X_LE2_count",
            ]
        ]
        .fillna(0)
        .sum(axis=1)
    )

    depth_summary["depth_broad_LE1or2"] = (
        depth_summary[
            [
                "WTO_plus_LE1or2_count",
                "WTO_X_LE1or2_count",
            ]
        ]
        .fillna(0)
        .sum(axis=1)
    )

    depth_summary.to_csv(
        AUDIT_DIR / "step2_dta_depth_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    line(
        report,
        f"Bilateral Information rows: "
        f"{len(bilateral):,}"
    )
    line(
        report,
        "Bilateral year range: "
        f"{bilateral['year'].min()} to "
        f"{bilateral['year'].max()}"
    )
    line(
        report,
        f"Bilateral rows with missing year: "
        f"{bilateral['year'].isna().sum():,}"
    )
    line(
        report,
        f"Exact duplicate bilateral rows: "
        f"{bilateral.duplicated().sum():,}"
    )

    key_columns = [
        "iso1",
        "iso2",
        "WBID",
        "year",
    ]

    line(
        report,
        "Duplicate iso1–iso2–WBID–year keys: "
        f"{bilateral.duplicated(key_columns).sum():,}"
    )

    bilateral_missing_year = bilateral[
        bilateral["year"].isna()
    ].copy()

    bilateral_missing_year.to_csv(
        AUDIT_DIR
        / "step2_dta_bilateral_missing_year.csv",
        index=False,
        encoding="utf-8-sig",
    )

    bilateral_sample = bilateral[
        bilateral["year"].between(
            2007,
            2023,
            inclusive="both",
        )
    ].copy()

    line(
        report,
        f"Bilateral rows within 2007–2023: "
        f"{len(bilateral_sample):,}"
    )
    line(
        report,
        "Unique agreements represented in "
        "2007–2023 bilateral rows: "
        f"{bilateral_sample['WBID'].nunique():,}"
    )

    line(
        report,
        "Saved: outputs/audit/"
        "step2_dta_agreements_missing_content.csv"
    )
    line(
        report,
        "Saved: outputs/audit/"
        "step2_dta_depth_summary.csv"
    )
    line(
        report,
        "Saved: outputs/audit/"
        "step2_dta_bilateral_missing_year.csv"
    )


def audit_wto(report: list[str]) -> None:
    section(
        report,
        "G. WTO REGIONAL TRADE AGREEMENTS"
    )

    path = FILES["wto"]
    excel = pd.ExcelFile(path, engine="openpyxl")

    line(report, f"Sheets: {excel.sheet_names}")

    all_rtas = pd.read_excel(
        path,
        sheet_name="AllRTAs",
        engine="openpyxl",
    )

    line(
        report,
        f"AllRTAs rows: {len(all_rtas):,}"
    )
    line(
        report,
        f"AllRTAs columns: {len(all_rtas.columns):,}"
    )
    line(
        report,
        "Status counts: "
        f"{all_rtas['Status'].value_counts(dropna=False).to_dict()}"
    )
    line(
        report,
        f"Unique RTA IDs: "
        f"{all_rtas['RTA ID'].nunique(dropna=True):,}"
    )
    line(
        report,
        f"Duplicate RTA IDs: "
        f"{all_rtas['RTA ID'].duplicated().sum():,}"
    )
    line(
        report,
        "Rows with Current signatories: "
        f"{all_rtas['Current signatories'].notna().sum():,}"
    )
    line(
        report,
        "Rows with Specific Entry/Exit dates: "
        f"{all_rtas['Specific Entry/Exit dates'].notna().sum():,}"
    )

    status_summary = (
        all_rtas["Status"]
        .value_counts(dropna=False)
        .rename_axis("status")
        .reset_index(name="number_of_rtas")
    )

    status_summary.to_csv(
        AUDIT_DIR / "step2_wto_status_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    line(
        report,
        "Saved: outputs/audit/"
        "step2_wto_status_summary.csv"
    )


def main() -> None:
    report: list[str] = []

    line(report, "=" * 88)
    line(
        report,
        "AIID DTA–GPR PROJECT — STEP 2 REFERENCE FILE AUDIT"
    )
    line(report, "=" * 88)
    line(report, f"Project root: {PROJECT_ROOT}")
    line(
        report,
        "This script reads raw files only. "
        "It does not modify them."
    )

    if not PROJECT_ROOT.exists():
        line(
            report,
            f"ERROR: Project root does not exist: "
            f"{PROJECT_ROOT}"
        )
        REPORT_FILE.write_text(
            "\n".join(report),
            encoding="utf-8",
        )
        print("\n".join(report))
        sys.exit(1)

    all_found = check_required_files(report)

    if not all_found:
        line(
            report,
            "STOP: At least one required file is missing."
        )
        REPORT_FILE.write_text(
            "\n".join(report),
            encoding="utf-8",
        )
        print("\n".join(report))
        sys.exit(1)

    audit_functions = [
        ("country metadata", audit_country_metadata),
        ("product metadata", audit_product_metadata),
        ("BEC correspondence", audit_bec),
        ("GPR workbook", audit_gpr),
        ("DTA workbook", audit_dta),
        ("WTO workbook", audit_wto),
    ]

    for label, function in audit_functions:
        try:
            function(report)
        except Exception as error:
            section(
                report,
                f"ERROR WHILE AUDITING {label.upper()}"
            )
            line(report, readable_error(error))
            line(report, traceback.format_exc())

    section(report, "H. FINAL STEP 2 SUMMARY")
    line(
        report,
        "Reference-file audit finished."
    )
    line(
        report,
        "Send step2_reference_audit.txt and all "
        "step2_*.csv files to ChatGPT for review."
    )
    line(
        report,
        "Do not begin the BACI full-data audit until "
        "these outputs have been checked."
    )

    REPORT_FILE.write_text(
        "\n".join(report),
        encoding="utf-8",
    )

    print("\n".join(report))
    print("")
    print(f"Report saved to: {REPORT_FILE}")


if __name__ == "__main__":
    main()

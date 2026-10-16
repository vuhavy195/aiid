from __future__ import annotations

from pathlib import Path
import re
import sys


# ============================================================
# SỬA ĐƯỜNG DẪN NÀY THÀNH ĐƯỜNG DẪN PROJECT TRÊN MÁY BẠN
# Ví dụ:
# PROJECT_ROOT = Path(r"D:\AIID_DTA_GPR")
# ============================================================

PROJECT_ROOT = Path(r"H:\AIID_DTA_GPR")


RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_FILE = OUTPUT_DIR / "step1_inventory.txt"


def format_size(size_bytes: int) -> str:
    """Convert byte size into KB, MB or GB."""
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)

    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:,.2f} {unit}"
        value /= 1024

    return f"{size_bytes} B"


def collect_files(folder: Path) -> list[Path]:
    """Return all files inside a folder and its subfolders."""
    if not folder.exists():
        return []

    return sorted(
        file for file in folder.rglob("*")
        if file.is_file()
    )


def extract_baci_year(filename: str) -> int | None:
    """Extract year from BACI annual filename."""
    match = re.search(
        r"BACI_HS07_Y(\d{4})",
        filename,
        flags=re.IGNORECASE
    )

    if match:
        return int(match.group(1))

    return None


def extract_baci_version(filename: str) -> str | None:
    """Extract six-digit BACI release version."""
    match = re.search(
        r"_V(\d{6})",
        filename,
        flags=re.IGNORECASE
    )

    if match:
        return match.group(1)

    return None


def find_matching_files(
    files: list[Path],
    keywords: list[str]
) -> list[Path]:
    """Find files containing any specified keyword."""
    matches = []

    for file in files:
        lower_name = file.name.lower()

        if any(keyword.lower() in lower_name for keyword in keywords):
            matches.append(file)

    return matches


def add_file_list(
    report_lines: list[str],
    title: str,
    files: list[Path]
) -> None:
    """Add a formatted file list to the report."""
    report_lines.append(title)

    if not files:
        report_lines.append("  NONE FOUND")
        return

    for file in files:
        relative_path = file.relative_to(PROJECT_ROOT)
        size = format_size(file.stat().st_size)

        report_lines.append(
            f"  {relative_path} | {size}"
        )


def main() -> None:
    if not PROJECT_ROOT.exists():
        print("")
        print("ERROR: PROJECT_ROOT does not exist.")
        print(f"Current path: {PROJECT_ROOT}")
        print("")
        print(
            "Open 01_inventory_raw.py and correct "
            "the PROJECT_ROOT line."
        )
        sys.exit(1)

    expected_folders = {
        "BACI HS2007": RAW_DIR / "baci_hs07_v202601",
        "BEC Rev.4": RAW_DIR / "bec",
        "World Bank DTA": RAW_DIR / "dta_world_bank",
        "WTO RTA": RAW_DIR / "wto_rta",
        "GPR": RAW_DIR / "gpr",
        "CEPII GeoDist": RAW_DIR / "geodist",
    }

    report_lines: list[str] = []

    report_lines.append("=" * 80)
    report_lines.append(
        "AIID PROJECT — STEP 1 RAW DATA INVENTORY"
    )
    report_lines.append("=" * 80)
    report_lines.append(f"Project root: {PROJECT_ROOT}")
    report_lines.append("")

    # ========================================================
    # 1. List files by source
    # ========================================================

    for source_name, folder in expected_folders.items():
        report_lines.append("-" * 80)
        report_lines.append(f"SOURCE: {source_name}")
        report_lines.append(f"Folder: {folder}")

        if not folder.exists():
            report_lines.append("STATUS: MISSING FOLDER")
            report_lines.append("")
            continue

        files = collect_files(folder)

        if not files:
            report_lines.append(
                "STATUS: FOLDER EXISTS BUT IS EMPTY"
            )
            report_lines.append("")
            continue

        report_lines.append(
            f"STATUS: FOUND {len(files)} FILE(S)"
        )

        for file in files:
            relative_path = file.relative_to(PROJECT_ROOT)
            size = format_size(file.stat().st_size)

            report_lines.append(
                f"  {relative_path} | {size}"
            )

        report_lines.append("")

    # ========================================================
    # 2. BACI validation
    # ========================================================

    baci_folder = expected_folders["BACI HS2007"]
    baci_files = collect_files(baci_folder)

    annual_baci_files = [
        file for file in baci_files
        if file.suffix.lower() == ".csv"
        and "BACI_HS07_Y" in file.name.upper()
    ]

    detected_years = sorted({
        year
        for file in annual_baci_files
        if (year := extract_baci_year(file.name)) is not None
    })

    detected_versions = sorted({
        version
        for file in annual_baci_files
        if (
            version := extract_baci_version(file.name)
        ) is not None
    })

    required_years = set(range(2007, 2024))
    detected_year_set = set(detected_years)

    missing_required_years = sorted(
        required_years - detected_year_set
    )

    country_metadata = find_matching_files(
        baci_files,
        ["country"]
    )

    product_metadata = [
        file for file in baci_files
        if any(
            keyword in file.name.lower()
            for keyword in ["product", "hs07"]
        )
        and "baci_hs07_y" not in file.name.lower()
    ]

    readme_files = find_matching_files(
        baci_files,
        ["readme", "documentation", "description"]
    )

    report_lines.append("=" * 80)
    report_lines.append("BACI HS2007 CHECK")
    report_lines.append("=" * 80)

    report_lines.append(
        f"Detected annual years: {detected_years}"
    )

    report_lines.append(
        f"Detected release versions: {detected_versions}"
    )

    report_lines.append(
        "Missing years from 2007–2023: "
        f"{missing_required_years}"
    )

    if not missing_required_years:
        report_lines.append(
            "BACI YEAR COVERAGE: PASS"
        )
    else:
        report_lines.append(
            "BACI YEAR COVERAGE: FAIL"
        )

    if detected_versions == ["202601"]:
        report_lines.append(
            "BACI VERSION: PASS — V202601 only"
        )
    else:
        report_lines.append(
            "BACI VERSION: REVIEW REQUIRED"
        )

    add_file_list(
        report_lines,
        "Possible country metadata files:",
        country_metadata
    )

    add_file_list(
        report_lines,
        "Possible HS2007 product metadata files:",
        product_metadata
    )

    add_file_list(
        report_lines,
        "Possible BACI documentation files:",
        readme_files
    )

    # ========================================================
    # 3. BEC Rev.4 validation
    # ========================================================

    bec_files = collect_files(
        expected_folders["BEC Rev.4"]
    )

    bec_correspondence = find_matching_files(
        bec_files,
        [
            "hs2007_to_bec4",
            "hs2007-bec4",
            "hs2007 bec4",
            "correlationtable"
        ]
    )

    bec_manual = find_matching_files(
        bec_files,
        ["bec_rev4_manual", "bec rev.4", "bec4"]
    )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("BEC REV.4 CHECK")
    report_lines.append("=" * 80)

    add_file_list(
        report_lines,
        "Possible HS2007 → BEC Rev.4 correspondence files:",
        bec_correspondence
    )

    add_file_list(
        report_lines,
        "Possible BEC Rev.4 manual or description files:",
        bec_manual
    )

    if bec_correspondence:
        report_lines.append(
            "BEC CORRESPONDENCE: FOUND"
        )
    else:
        report_lines.append(
            "BEC CORRESPONDENCE: MISSING OR FILE NAME NOT RECOGNIZED"
        )

    # ========================================================
    # 4. Other source checks
    # ========================================================

    dta_files = collect_files(
        expected_folders["World Bank DTA"]
    )

    wto_files = collect_files(
        expected_folders["WTO RTA"]
    )

    gpr_files = collect_files(
        expected_folders["GPR"]
    )

    geodist_files = collect_files(
        expected_folders["CEPII GeoDist"]
    )

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("OTHER DATA SOURCES")
    report_lines.append("=" * 80)

    add_file_list(
        report_lines,
        "World Bank DTA files:",
        dta_files
    )

    add_file_list(
        report_lines,
        "WTO RTA files:",
        wto_files
    )

    add_file_list(
        report_lines,
        "GPR files:",
        gpr_files
    )

    add_file_list(
        report_lines,
        "CEPII GeoDist files:",
        geodist_files
    )

    # ========================================================
    # 5. Final summary
    # ========================================================

    incomplete_sources = []

    for source_name, folder in expected_folders.items():
        if not folder.exists() or not collect_files(folder):
            incomplete_sources.append(source_name)

    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("FINAL STEP 1 SUMMARY")
    report_lines.append("=" * 80)

    if incomplete_sources:
        report_lines.append(
            "EMPTY OR MISSING SOURCES: "
            + ", ".join(incomplete_sources)
        )
    else:
        report_lines.append(
            "ALL EXPECTED SOURCE FOLDERS CONTAIN FILES"
        )

    if (
        not missing_required_years
        and detected_versions == ["202601"]
        and country_metadata
        and product_metadata
    ):
        report_lines.append(
            "BACI CORE INVENTORY: PASS"
        )
    else:
        report_lines.append(
            "BACI CORE INVENTORY: REVIEW REQUIRED"
        )

    if bec_correspondence:
        report_lines.append(
            "BEC REV.4 CORE INVENTORY: PASS"
        )
    else:
        report_lines.append(
            "BEC REV.4 CORE INVENTORY: REVIEW REQUIRED"
        )

    report_lines.append("")
    report_lines.append(
        "NOTE: This step only checks whether files exist."
    )
    report_lines.append(
        "File contents, columns, missing values and merge keys "
        "will be examined in Step 2."
    )

    REPORT_FILE.write_text(
        "\n".join(report_lines),
        encoding="utf-8"
    )

    print("\n".join(report_lines))
    print("")
    print(
        f"Inventory report saved to:\n{REPORT_FILE}"
    )


if __name__ == "__main__":
    main()
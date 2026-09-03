from __future__ import annotations

from pathlib import Path
from datetime import datetime
import sys
import traceback

import duckdb
import pandas as pd


# ============================================================
# PROJECT SETTINGS
# ============================================================
PROJECT_ROOT = Path(r"H:\AIID_DTA_GPR")

START_YEAR = 2007
END_YEAR = 2023

# If the script stops midway, run it again. Completed years
# will be skipped automatically.
FORCE_REPROCESS_COMPLETED_YEARS = False

RAW_BACI_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "baci_hs07_v202601"
)

COUNTRY_FILE = (
    RAW_BACI_DIR
    / "country_codes_V202601.csv"
)

PRODUCT_FILE = (
    RAW_BACI_DIR
    / "product_codes_HS07_V202601.csv"
)

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"
TEMP_DIR = INTERIM_DIR / "duckdb_temp"

INTERIM_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_FILE = INTERIM_DIR / "step3_baci_audit.duckdb"
REPORT_FILE = AUDIT_DIR / "step3_baci_audit.txt"


# These are not treated as standard current economies in the
# preliminary baseline sample. They remain in the audit outputs.
SPECIAL_NONSTANDARD_CODES = {
    490,  # Other Asia, nes — often used as a Taiwan proxy
    697,  # Europe EFTA, nes
    711,  # Historical Southern African Customs Union aggregate
    849,  # US Miscellaneous Pacific Islands
}


def sql_path(path: Path) -> str:
    """Return a path safe for use inside DuckDB SQL strings."""
    return path.resolve().as_posix().replace("'", "''")


def log(message: str = "") -> None:
    print(message, flush=True)


def create_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS annual_audit (
            year INTEGER,
            file_name VARCHAR,
            file_size_mb DOUBLE,
            raw_rows BIGINT,
            distinct_exporters BIGINT,
            distinct_importers BIGINT,
            distinct_products BIGINT,
            total_trade_value_1000usd DOUBLE,
            null_year_rows BIGINT,
            null_exporter_rows BIGINT,
            null_importer_rows BIGINT,
            null_hs6_rows BIGINT,
            null_trade_value_rows BIGINT,
            missing_quantity_rows BIGINT,
            year_mismatch_rows BIGINT,
            domestic_trade_rows BIGINT,
            nonpositive_trade_rows BIGINT,
            invalid_raw_hs6_rows BIGINT,
            unknown_exporter_rows BIGINT,
            unknown_importer_rows BIGINT,
            unknown_product_rows BIGINT,
            duplicate_key_groups BIGINT,
            duplicate_excess_rows BIGINT,
            audit_status VARCHAR,
            completed_at TIMESTAMP
        )
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS country_export_year (
            year INTEGER,
            country_code INTEGER,
            export_rows BIGINT,
            export_value_1000usd DOUBLE,
            number_of_import_partners BIGINT,
            number_of_exported_hs6 BIGINT
        )
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS country_import_year (
            year INTEGER,
            country_code INTEGER,
            import_rows BIGINT,
            import_value_1000usd DOUBLE,
            number_of_export_partners BIGINT,
            number_of_imported_hs6 BIGINT
        )
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS product_year (
            year INTEGER,
            hs6 VARCHAR,
            trade_rows BIGINT,
            trade_value_1000usd DOUBLE,
            number_of_exporters BIGINT,
            number_of_importers BIGINT
        )
        """
    )


def load_metadata(con: duckdb.DuckDBPyConnection) -> None:
    country_path = sql_path(COUNTRY_FILE)
    product_path = sql_path(PRODUCT_FILE)

    con.execute(
        f"""
        CREATE OR REPLACE TABLE country_meta AS
        SELECT
            TRY_CAST(country_code AS INTEGER) AS country_code,
            TRIM(country_name) AS country_name,
            NULLIF(TRIM(country_iso2), '') AS country_iso2,
            NULLIF(TRIM(country_iso3), '') AS country_iso3
        FROM read_csv(
            '{country_path}',
            header = true,
            all_varchar = true
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE product_meta AS
        SELECT
            LPAD(TRIM(code), 6, '0') AS hs6,
            description
        FROM read_csv(
            '{product_path}',
            header = true,
            all_varchar = true
        )
        """
    )

    country_duplicates = con.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT country_code
            FROM country_meta
            GROUP BY country_code
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    product_duplicates = con.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT hs6
            FROM product_meta
            GROUP BY hs6
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    if country_duplicates:
        raise ValueError(
            "country_meta contains duplicated country codes."
        )

    if product_duplicates:
        raise ValueError(
            "product_meta contains duplicated HS6 codes."
        )


def annual_file(year: int) -> Path:
    return (
        RAW_BACI_DIR
        / f"BACI_HS07_Y{year}_V202601.csv"
    )


def create_year_view(
    con: duckdb.DuckDBPyConnection,
    file_path: Path,
) -> None:
    path = sql_path(file_path)

    # Read all fields as text first. This lets us detect malformed
    # values instead of silently coercing them.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW year_data AS
        SELECT
            TRY_CAST(TRIM(t) AS INTEGER) AS year,
            TRY_CAST(TRIM(i) AS INTEGER) AS exporter_code,
            TRY_CAST(TRIM(j) AS INTEGER) AS importer_code,
            TRIM(k) AS raw_hs6,
            LPAD(TRIM(k), 6, '0') AS hs6,
            TRY_CAST(TRIM(v) AS DOUBLE) AS trade_value_1000usd,
            CASE
                WHEN q IS NULL
                  OR TRIM(q) = ''
                  OR UPPER(TRIM(q)) IN ('NA', 'N/A', 'NULL')
                THEN NULL
                ELSE TRY_CAST(TRIM(q) AS DOUBLE)
            END AS quantity_tons
        FROM read_csv(
            '{path}',
            header = true,
            all_varchar = true,
            ignore_errors = false
        )
        """
    )


def process_year(
    con: duckdb.DuckDBPyConnection,
    year: int,
) -> None:
    file_path = annual_file(year)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Missing BACI file: {file_path}"
        )

    already_completed = con.execute(
        """
        SELECT COUNT(*)
        FROM annual_audit
        WHERE year = ?
        """,
        [year],
    ).fetchone()[0]

    if (
        already_completed
        and not FORCE_REPROCESS_COMPLETED_YEARS
    ):
        log(
            f"[{year}] Already completed — skipping. "
            "Delete the DuckDB file to start over."
        )
        return

    log(f"[{year}] Reading {file_path.name} ...")
    create_year_view(con, file_path)

    # Remove any incomplete output left by an interrupted run.
    con.execute(
        "DELETE FROM annual_audit WHERE year = ?",
        [year],
    )
    con.execute(
        "DELETE FROM country_export_year WHERE year = ?",
        [year],
    )
    con.execute(
        "DELETE FROM country_import_year WHERE year = ?",
        [year],
    )
    con.execute(
        "DELETE FROM product_year WHERE year = ?",
        [year],
    )

    log(f"[{year}] Auditing rows and reference codes ...")

    basic = con.execute(
        """
        SELECT
            COUNT(*) AS raw_rows,
            COUNT(DISTINCT exporter_code)
                AS distinct_exporters,
            COUNT(DISTINCT importer_code)
                AS distinct_importers,
            COUNT(DISTINCT hs6)
                AS distinct_products,
            SUM(trade_value_1000usd)
                AS total_trade_value_1000usd,
            COUNT(*) FILTER (WHERE year IS NULL)
                AS null_year_rows,
            COUNT(*) FILTER (
                WHERE exporter_code IS NULL
            ) AS null_exporter_rows,
            COUNT(*) FILTER (
                WHERE importer_code IS NULL
            ) AS null_importer_rows,
            COUNT(*) FILTER (
                WHERE raw_hs6 IS NULL
                   OR raw_hs6 = ''
            ) AS null_hs6_rows,
            COUNT(*) FILTER (
                WHERE trade_value_1000usd IS NULL
            ) AS null_trade_value_rows,
            COUNT(*) FILTER (
                WHERE quantity_tons IS NULL
            ) AS missing_quantity_rows,
            COUNT(*) FILTER (
                WHERE year <> ?
            ) AS year_mismatch_rows,
            COUNT(*) FILTER (
                WHERE exporter_code = importer_code
            ) AS domestic_trade_rows,
            COUNT(*) FILTER (
                WHERE trade_value_1000usd <= 0
            ) AS nonpositive_trade_rows,
            COUNT(*) FILTER (
                WHERE NOT regexp_full_match(
                    raw_hs6,
                    '[0-9]{1,6}'
                )
            ) AS invalid_raw_hs6_rows
        FROM year_data
        """,
        [year],
    ).fetchdf().iloc[0].to_dict()

    unknown_exporters = con.execute(
        """
        SELECT COUNT(*)
        FROM year_data y
        LEFT JOIN country_meta c
          ON y.exporter_code = c.country_code
        WHERE c.country_code IS NULL
        """
    ).fetchone()[0]

    unknown_importers = con.execute(
        """
        SELECT COUNT(*)
        FROM year_data y
        LEFT JOIN country_meta c
          ON y.importer_code = c.country_code
        WHERE c.country_code IS NULL
        """
    ).fetchone()[0]

    unknown_products = con.execute(
        """
        SELECT COUNT(*)
        FROM year_data y
        LEFT JOIN product_meta p
          ON y.hs6 = p.hs6
        WHERE p.hs6 IS NULL
        """
    ).fetchone()[0]

    log(f"[{year}] Checking duplicate trade keys ...")

    duplicate_result = con.execute(
        """
        SELECT
            COUNT(*) AS duplicate_key_groups,
            COALESCE(SUM(number_of_rows - 1), 0)
                AS duplicate_excess_rows
        FROM (
            SELECT
                exporter_code,
                importer_code,
                hs6,
                COUNT(*) AS number_of_rows
            FROM year_data
            GROUP BY
                exporter_code,
                importer_code,
                hs6
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()

    duplicate_key_groups = int(
        duplicate_result[0] or 0
    )
    duplicate_excess_rows = int(
        duplicate_result[1] or 0
    )

    critical_values = [
        basic["null_year_rows"],
        basic["null_exporter_rows"],
        basic["null_importer_rows"],
        basic["null_hs6_rows"],
        basic["null_trade_value_rows"],
        basic["year_mismatch_rows"],
        basic["domestic_trade_rows"],
        basic["nonpositive_trade_rows"],
        basic["invalid_raw_hs6_rows"],
        unknown_exporters,
        unknown_importers,
        unknown_products,
        duplicate_excess_rows,
    ]

    audit_status = (
        "PASS"
        if all(int(value or 0) == 0
               for value in critical_values)
        else "REVIEW"
    )

    log(f"[{year}] Building country and product aggregates ...")

    con.execute(
        """
        INSERT INTO country_export_year
        SELECT
            year,
            exporter_code AS country_code,
            COUNT(*) AS export_rows,
            SUM(trade_value_1000usd)
                AS export_value_1000usd,
            COUNT(DISTINCT importer_code)
                AS number_of_import_partners,
            COUNT(DISTINCT hs6)
                AS number_of_exported_hs6
        FROM year_data
        GROUP BY year, exporter_code
        """
    )

    con.execute(
        """
        INSERT INTO country_import_year
        SELECT
            year,
            importer_code AS country_code,
            COUNT(*) AS import_rows,
            SUM(trade_value_1000usd)
                AS import_value_1000usd,
            COUNT(DISTINCT exporter_code)
                AS number_of_export_partners,
            COUNT(DISTINCT hs6)
                AS number_of_imported_hs6
        FROM year_data
        GROUP BY year, importer_code
        """
    )

    con.execute(
        """
        INSERT INTO product_year
        SELECT
            year,
            hs6,
            COUNT(*) AS trade_rows,
            SUM(trade_value_1000usd)
                AS trade_value_1000usd,
            COUNT(DISTINCT exporter_code)
                AS number_of_exporters,
            COUNT(DISTINCT importer_code)
                AS number_of_importers
        FROM year_data
        GROUP BY year, hs6
        """
    )

    file_size_mb = (
        file_path.stat().st_size
        / 1024
        / 1024
    )

    con.execute(
        """
        INSERT INTO annual_audit VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?,
            CURRENT_TIMESTAMP
        )
        """,
        [
            year,
            file_path.name,
            file_size_mb,
            int(basic["raw_rows"]),
            int(basic["distinct_exporters"]),
            int(basic["distinct_importers"]),
            int(basic["distinct_products"]),
            float(
                basic[
                    "total_trade_value_1000usd"
                ] or 0
            ),
            int(basic["null_year_rows"]),
            int(basic["null_exporter_rows"]),
            int(basic["null_importer_rows"]),
            int(basic["null_hs6_rows"]),
            int(basic["null_trade_value_rows"]),
            int(basic["missing_quantity_rows"]),
            int(basic["year_mismatch_rows"]),
            int(basic["domestic_trade_rows"]),
            int(basic["nonpositive_trade_rows"]),
            int(basic["invalid_raw_hs6_rows"]),
            int(unknown_exporters),
            int(unknown_importers),
            int(unknown_products),
            duplicate_key_groups,
            duplicate_excess_rows,
            audit_status,
        ],
    )

    con.execute("CHECKPOINT")

    log(
        f"[{year}] Finished — "
        f"{int(basic['raw_rows']):,} rows; "
        f"status={audit_status}"
    )


def build_final_outputs(
    con: duckdb.DuckDBPyConnection,
) -> None:
    log("Building country-year coverage table ...")

    con.execute(
        f"""
        CREATE OR REPLACE TABLE country_year_coverage AS
        WITH years AS (
            SELECT year
            FROM range(
                {START_YEAR},
                {END_YEAR + 1}
            ) AS t(year)
        ),
        grid AS (
            SELECT
                c.country_code,
                c.country_name,
                c.country_iso2,
                c.country_iso3,
                y.year
            FROM country_meta c
            CROSS JOIN years y
        )
        SELECT
            g.country_code,
            g.country_name,
            g.country_iso2,
            g.country_iso3,
            g.year,
            COALESCE(e.export_rows, 0)
                AS export_rows,
            COALESCE(e.export_value_1000usd, 0)
                AS export_value_1000usd,
            COALESCE(
                e.number_of_import_partners,
                0
            ) AS number_of_import_partners,
            COALESCE(
                e.number_of_exported_hs6,
                0
            ) AS number_of_exported_hs6,
            COALESCE(i.import_rows, 0)
                AS import_rows,
            COALESCE(i.import_value_1000usd, 0)
                AS import_value_1000usd,
            COALESCE(
                i.number_of_export_partners,
                0
            ) AS number_of_export_partners,
            COALESCE(
                i.number_of_imported_hs6,
                0
            ) AS number_of_imported_hs6,
            (
                COALESCE(e.export_rows, 0) > 0
            ) AS exporter_active,
            (
                COALESCE(i.import_rows, 0) > 0
            ) AS importer_active,
            (
                COALESCE(e.export_rows, 0) > 0
                AND
                COALESCE(i.import_rows, 0) > 0
            ) AS both_active
        FROM grid g
        LEFT JOIN country_export_year e
          ON g.country_code = e.country_code
         AND g.year = e.year
        LEFT JOIN country_import_year i
          ON g.country_code = i.country_code
         AND g.year = i.year
        """
    )

    country_year = con.execute(
        """
        SELECT *
        FROM country_year_coverage
        ORDER BY country_code, year
        """
    ).fetchdf()

    country_year.to_csv(
        AUDIT_DIR
        / "step3_country_year_coverage.csv",
        index=False,
        encoding="utf-8-sig",
    )

    country_summary = con.execute(
        f"""
        SELECT
            country_code,
            ANY_VALUE(country_name)
                AS country_name,
            ANY_VALUE(country_iso2)
                AS country_iso2,
            ANY_VALUE(country_iso3)
                AS country_iso3,
            SUM(exporter_active::INTEGER)
                AS years_exporter_active,
            SUM(importer_active::INTEGER)
                AS years_importer_active,
            SUM(both_active::INTEGER)
                AS years_both_active,
            MIN(year) FILTER (
                WHERE exporter_active
                   OR importer_active
            ) AS first_active_year,
            MAX(year) FILTER (
                WHERE exporter_active
                   OR importer_active
            ) AS last_active_year,
            SUM(export_value_1000usd)
                AS total_exports_1000usd,
            SUM(import_value_1000usd)
                AS total_imports_1000usd,
            AVG(
                export_value_1000usd
                + import_value_1000usd
            ) FILTER (
                WHERE year BETWEEN 2007 AND 2009
            ) AS avg_preperiod_trade_1000usd,
            AVG(export_value_1000usd) FILTER (
                WHERE year BETWEEN 2007 AND 2009
            ) AS avg_preperiod_exports_1000usd,
            AVG(import_value_1000usd) FILTER (
                WHERE year BETWEEN 2007 AND 2009
            ) AS avg_preperiod_imports_1000usd,
            AVG(
                number_of_import_partners
                + number_of_export_partners
            ) AS avg_partner_connections,
            AVG(
                number_of_exported_hs6
                + number_of_imported_hs6
            ) AS avg_product_connections
        FROM country_year_coverage
        GROUP BY country_code
        """
    ).fetchdf()

    global_exports = (
        country_summary[
            "total_exports_1000usd"
        ].sum()
    )

    country_summary["global_export_share"] = (
        country_summary[
            "total_exports_1000usd"
        ]
        / global_exports
    )

    country_summary["standard_iso3"] = (
        country_summary["country_iso3"]
        .fillna("")
        .str.fullmatch(r"[A-Z]{3}")
    )

    country_summary["historical_entity"] = (
        country_summary["country_name"]
        .fillna("")
        .str.contains(
            r"\(\.\.\.",
            regex=True,
        )
    )

    country_summary["special_nonstandard_code"] = (
        country_summary["country_code"]
        .isin(SPECIAL_NONSTANDARD_CODES)
    )

    country_summary["full_2007_2023_coverage"] = (
        country_summary["years_both_active"]
        == (END_YEAR - START_YEAR + 1)
    )

    country_summary["preliminary_eligible"] = (
        country_summary["standard_iso3"]
        & ~country_summary["historical_entity"]
        & ~country_summary[
            "special_nonstandard_code"
        ]
        & country_summary[
            "full_2007_2023_coverage"
        ]
    )

    country_summary[
        "preperiod_rank_among_eligible"
    ] = pd.Series(
        pd.NA,
        index=country_summary.index,
        dtype="Int64",
    )

    eligible_order = (
        country_summary.loc[
            country_summary[
                "preliminary_eligible"
            ]
        ]
        .sort_values(
            [
                "avg_preperiod_trade_1000usd",
                "country_code",
            ],
            ascending=[False, True],
        )
        .index
    )

    country_summary.loc[
        eligible_order,
        "preperiod_rank_among_eligible",
    ] = range(1, len(eligible_order) + 1)

    country_summary["target160_preview"] = (
        country_summary[
            "preperiod_rank_among_eligible"
        ]
        .le(160)
        .fillna(False)
    )

    target_order = country_summary.loc[
        country_summary["target160_preview"]
    ].sort_values(
        "preperiod_rank_among_eligible"
    )

    target_cumulative = (
        target_order["global_export_share"]
        .cumsum()
    )

    country_summary[
        "cumulative_global_export_share_in_target_order"
    ] = pd.NA

    country_summary.loc[
        target_order.index,
        "cumulative_global_export_share_in_target_order",
    ] = target_cumulative.values

    country_summary = country_summary.sort_values(
        [
            "preliminary_eligible",
            "preperiod_rank_among_eligible",
            "country_code",
        ],
        ascending=[False, True, True],
        na_position="last",
    )

    country_summary.to_csv(
        AUDIT_DIR
        / "step3_country_sample_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )

    country_summary.loc[
        country_summary["target160_preview"]
    ].sort_values(
        "preperiod_rank_among_eligible"
    ).to_csv(
        AUDIT_DIR
        / "step3_country_target160_preview.csv",
        index=False,
        encoding="utf-8-sig",
    )

    country_summary.loc[
        ~country_summary["preliminary_eligible"]
    ].to_csv(
        AUDIT_DIR
        / "step3_country_exclusion_review.csv",
        index=False,
        encoding="utf-8-sig",
    )

    annual_audit = con.execute(
        """
        SELECT *
        FROM annual_audit
        ORDER BY year
        """
    ).fetchdf()

    annual_audit.to_csv(
        AUDIT_DIR / "step3_annual_baci_audit.csv",
        index=False,
        encoding="utf-8-sig",
    )

    product_coverage = con.execute(
        """
        SELECT
            p.hs6,
            m.description,
            COUNT(*) AS years_present,
            SUM(p.trade_rows) AS total_trade_rows,
            SUM(p.trade_value_1000usd)
                AS total_trade_value_1000usd,
            AVG(p.number_of_exporters)
                AS avg_number_of_exporters,
            AVG(p.number_of_importers)
                AS avg_number_of_importers
        FROM product_year p
        LEFT JOIN product_meta m
          ON p.hs6 = m.hs6
        GROUP BY p.hs6, m.description
        ORDER BY total_trade_value_1000usd DESC
        """
    ).fetchdf()

    product_coverage.to_csv(
        AUDIT_DIR
        / "step3_product_coverage.csv",
        index=False,
        encoding="utf-8-sig",
    )

    passed_years = int(
        annual_audit[
            "audit_status"
        ].eq("PASS").sum()
    )

    eligible_count = int(
        country_summary[
            "preliminary_eligible"
        ].sum()
    )

    target_count = int(
        country_summary[
            "target160_preview"
        ].sum()
    )

    target_export_share = float(
        country_summary.loc[
            country_summary["target160_preview"],
            "global_export_share",
        ].sum()
    )

    special_999999 = product_coverage.loc[
        product_coverage["hs6"] == "999999",
        "total_trade_value_1000usd",
    ]

    special_999999_value = (
        float(special_999999.iloc[0])
        if not special_999999.empty
        else 0.0
    )

    total_product_trade = float(
        product_coverage[
            "total_trade_value_1000usd"
        ].sum()
    )

    special_999999_share = (
        special_999999_value
        / total_product_trade
        if total_product_trade > 0
        else 0.0
    )

    report_lines = [
        "=" * 88,
        "AIID DTA–GPR PROJECT — STEP 3 BACI AUDIT",
        "=" * 88,
        f"Project root: {PROJECT_ROOT}",
        f"Years audited: {START_YEAR}–{END_YEAR}",
        "",
        "A. ANNUAL BACI FILES",
        "-" * 88,
        (
            f"Years with PASS status: "
            f"{passed_years} of "
            f"{END_YEAR - START_YEAR + 1}"
        ),
        (
            f"Total raw rows: "
            f"{int(annual_audit['raw_rows'].sum()):,}"
        ),
        (
            "Total trade value (thousand current USD): "
            f"{annual_audit['total_trade_value_1000usd'].sum():,.2f}"
        ),
        (
            f"Duplicate excess rows: "
            f"{int(annual_audit['duplicate_excess_rows'].sum()):,}"
        ),
        (
            f"Unknown exporter rows: "
            f"{int(annual_audit['unknown_exporter_rows'].sum()):,}"
        ),
        (
            f"Unknown importer rows: "
            f"{int(annual_audit['unknown_importer_rows'].sum()):,}"
        ),
        (
            f"Unknown product rows: "
            f"{int(annual_audit['unknown_product_rows'].sum()):,}"
        ),
        "",
        "B. COUNTRY SAMPLE PREVIEW",
        "-" * 88,
        (
            f"Country metadata codes: "
            f"{len(country_summary):,}"
        ),
        (
            "Preliminary eligible economies with "
            f"full 2007–2023 exporter/importer coverage: "
            f"{eligible_count:,}"
        ),
        (
            f"Target-160 preview size: {target_count:,}"
        ),
        (
            "Target-160 share of global BACI exports "
            f"over 2007–2023: {target_export_share:.4%}"
        ),
        "",
        "C. PRODUCT CHECK",
        "-" * 88,
        (
            f"Products observed in trade data: "
            f"{len(product_coverage):,}"
        ),
        (
            "Trade-value share of special product "
            f"999999: {special_999999_share:.6%}"
        ),
        "",
        "D. OUTPUT FILES",
        "-" * 88,
        "outputs/audit/step3_baci_audit.txt",
        "outputs/audit/step3_annual_baci_audit.csv",
        "outputs/audit/step3_country_year_coverage.csv",
        "outputs/audit/step3_country_sample_candidates.csv",
        "outputs/audit/step3_country_target160_preview.csv",
        "outputs/audit/step3_country_exclusion_review.csv",
        "outputs/audit/step3_product_coverage.csv",
        "",
        "E. NEXT ACTION",
        "-" * 88,
        (
            "Send the report and country/sample CSV files "
            "to ChatGPT. Do not treat the target-160 list "
            "as final until it has been reviewed."
        ),
    ]

    REPORT_FILE.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    log("")
    log("\n".join(report_lines))


def main() -> None:
    if not PROJECT_ROOT.exists():
        raise FileNotFoundError(
            f"Project folder not found: {PROJECT_ROOT}"
        )

    required_files = [
        COUNTRY_FILE,
        PRODUCT_FILE,
    ] + [
        annual_file(year)
        for year in range(
            START_YEAR,
            END_YEAR + 1,
        )
    ]

    missing_files = [
        path
        for path in required_files
        if not path.exists()
    ]

    if missing_files:
        missing_text = "\n".join(
            str(path)
            for path in missing_files
        )
        raise FileNotFoundError(
            "Required files are missing:\n"
            f"{missing_text}"
        )

    log("=" * 88)
    log("STEP 3 — BACI FULL-DATA AUDIT")
    log("=" * 88)
    log(f"Database: {DATABASE_FILE}")
    log(
        "The script processes one annual file at a time. "
        "Do not open the BACI CSV files in Excel."
    )
    log("")

    con = duckdb.connect(str(DATABASE_FILE))

    con.execute(
        f"SET temp_directory = '{sql_path(TEMP_DIR)}'"
    )
    con.execute(
        "SET preserve_insertion_order = false"
    )

    create_tables(con)
    load_metadata(con)

    for year in range(
        START_YEAR,
        END_YEAR + 1,
    ):
        process_year(con, year)

    build_final_outputs(con)
    con.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        error_text = [
            "=" * 88,
            "STEP 3 FAILED",
            "=" * 88,
            f"{type(error).__name__}: {error}",
            "",
            traceback.format_exc(),
        ]

        REPORT_FILE.write_text(
            "\n".join(error_text),
            encoding="utf-8",
        )

        print(
            "\n".join(error_text),
            flush=True,
        )
        sys.exit(1)

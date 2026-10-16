from __future__ import annotations

from pathlib import Path
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

# Set to True only when you deliberately want to rebuild every year.
FORCE_REPROCESS_COMPLETED_YEARS = False

RAW_BACI_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "baci_hs07_v202601"
)

COUNTRY_SAMPLE_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "country_sample_160.csv"
)

BEC_MAP_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "hs07_bec4_clean_map.csv"
)

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"
TEMP_DIR = INTERIM_DIR / "duckdb_temp_step5"

INTERIM_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_FILE = INTERIM_DIR / "step5_trade_aggregates.duckdb"
REPORT_FILE = AUDIT_DIR / "step5_trade_aggregation_audit.txt"

OUTPUT_ALL_ENDUSES = (
    INTERIM_DIR
    / "trade_positive_pair_hs2_enduse_year.parquet"
)

OUTPUT_INTERMEDIATE_HS2 = (
    INTERIM_DIR
    / "trade_positive_pair_hs2_year_intermediate.parquet"
)

OUTPUT_INTERMEDIATE_PAIR_YEAR = (
    INTERIM_DIR
    / "trade_positive_pair_year_intermediate.parquet"
)

CLEAN_END_USES = (
    "intermediate",
    "consumption",
    "capital",
)


def sql_path(path: Path) -> str:
    """Return a path safe for DuckDB SQL strings."""
    return path.resolve().as_posix().replace("'", "''")


def log(message: str = "") -> None:
    print(message, flush=True)


def annual_baci_file(year: int) -> Path:
    return (
        RAW_BACI_DIR
        / f"BACI_HS07_Y{year}_V202601.csv"
    )


def verify_inputs() -> None:
    required = [
        COUNTRY_SAMPLE_FILE,
        BEC_MAP_FILE,
    ] + [
        annual_baci_file(year)
        for year in range(START_YEAR, END_YEAR + 1)
    ]

    missing = [
        path for path in required
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "The following required files are missing:\n"
            + "\n".join(str(path) for path in missing)
        )


def create_database_tables(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS annual_filter_audit (
            year INTEGER PRIMARY KEY,
            raw_rows BIGINT,
            raw_trade_value_1000usd DOUBLE,
            selected_country_rows BIGINT,
            selected_country_trade_value_1000usd DOUBLE,
            intermediate_rows BIGINT,
            intermediate_trade_value_1000usd DOUBLE,
            consumption_rows BIGINT,
            consumption_trade_value_1000usd DOUBLE,
            capital_rows BIGINT,
            capital_trade_value_1000usd DOUBLE,
            ambiguous_rows BIGINT,
            ambiguous_trade_value_1000usd DOUBLE,
            unallocated_rows BIGINT,
            unallocated_trade_value_1000usd DOUBLE,
            unmapped_rows BIGINT,
            unmapped_trade_value_1000usd DOUBLE,
            retained_clean_rows BIGINT,
            retained_clean_trade_value_1000usd DOUBLE,
            positive_aggregate_rows BIGINT,
            duplicate_aggregate_keys BIGINT,
            audit_status VARCHAR,
            completed_at TIMESTAMP
        )
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS positive_pair_hs2_enduse_year (
            year INTEGER,
            exporter_code INTEGER,
            importer_code INTEGER,
            exporter_iso3 VARCHAR,
            importer_iso3 VARCHAR,
            hs2 VARCHAR,
            end_use VARCHAR,
            trade_value_1000usd DOUBLE,
            positive_hs6_count INTEGER,
            underlying_positive_flow_rows BIGINT
        )
        """
    )


def load_reference_tables(
    con: duckdb.DuckDBPyConnection,
) -> None:
    country_path = sql_path(COUNTRY_SAMPLE_FILE)
    bec_path = sql_path(BEC_MAP_FILE)

    con.execute(
        f"""
        CREATE OR REPLACE TABLE sample_country AS
        SELECT
            TRY_CAST(country_code AS INTEGER)
                AS country_code,
            TRIM(analysis_iso3)
                AS analysis_iso3,
            TRIM(analysis_name)
                AS analysis_name,
            TRY_CAST(final_sample_rank AS INTEGER)
                AS final_sample_rank
        FROM read_csv(
            '{country_path}',
            header = true,
            all_varchar = true
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE bec_map AS
        SELECT
            LPAD(TRIM(hs6), 6, '0') AS hs6,
            TRIM(final_end_use) AS final_end_use,
            TRIM(mapping_status) AS mapping_status
        FROM read_csv(
            '{bec_path}',
            header = true,
            all_varchar = true
        )
        """
    )

    sample_checks = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT country_code)
                AS unique_country_codes,
            COUNT(DISTINCT analysis_iso3)
                AS unique_iso3
        FROM sample_country
        """
    ).fetchone()

    if sample_checks != (160, 160, 160):
        raise ValueError(
            "country_sample_160.csv does not contain "
            "160 unique country codes and ISO3 values. "
            f"Observed checks: {sample_checks}"
        )

    bec_duplicate_count = con.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT hs6
            FROM bec_map
            GROUP BY hs6
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    if bec_duplicate_count:
        raise ValueError(
            "hs07_bec4_clean_map.csv contains duplicated HS6 codes."
        )


def create_raw_year_table(
    con: duckdb.DuckDBPyConnection,
    year: int,
) -> None:
    file_path = sql_path(annual_baci_file(year))

    # Read as text first so that leading zeroes and malformed fields
    # are handled explicitly.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE raw_year AS
        SELECT
            TRY_CAST(TRIM(t) AS INTEGER) AS year,
            TRY_CAST(TRIM(i) AS INTEGER) AS exporter_code,
            TRY_CAST(TRIM(j) AS INTEGER) AS importer_code,
            LPAD(TRIM(k), 6, '0') AS hs6,
            TRY_CAST(TRIM(v) AS DOUBLE)
                AS trade_value_1000usd
        FROM read_csv(
            '{file_path}',
            header = true,
            all_varchar = true,
            ignore_errors = false
        )
        """
    )


def create_selected_year_table(
    con: duckdb.DuckDBPyConnection,
) -> None:
    # Left-join the BEC map so that ambiguous, unallocated and
    # unmapped products remain visible in the audit.
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE selected_year AS
        SELECT
            r.year,
            r.exporter_code,
            r.importer_code,
            e.analysis_iso3 AS exporter_iso3,
            d.analysis_iso3 AS importer_iso3,
            r.hs6,
            SUBSTR(r.hs6, 1, 2) AS hs2,
            r.trade_value_1000usd,
            b.final_end_use,
            b.mapping_status
        FROM raw_year r
        INNER JOIN sample_country e
            ON r.exporter_code = e.country_code
        INNER JOIN sample_country d
            ON r.importer_code = d.country_code
        LEFT JOIN bec_map b
            ON r.hs6 = b.hs6
        WHERE r.exporter_code <> r.importer_code
          AND r.trade_value_1000usd > 0
        """
    )


def fetch_scalar(
    con: duckdb.DuckDBPyConnection,
    query: str,
) -> int | float:
    value = con.execute(query).fetchone()[0]
    return 0 if value is None else value


def process_year(
    con: duckdb.DuckDBPyConnection,
    year: int,
) -> None:
    completed = con.execute(
        """
        SELECT COUNT(*)
        FROM annual_filter_audit
        WHERE year = ?
        """,
        [year],
    ).fetchone()[0]

    if completed and not FORCE_REPROCESS_COMPLETED_YEARS:
        log(f"[{year}] Already completed — skipping.")
        return

    log(f"[{year}] Reading BACI file ...")
    create_raw_year_table(con, year)

    raw_stats = con.execute(
        """
        SELECT
            COUNT(*) AS raw_rows,
            SUM(trade_value_1000usd)
                AS raw_trade_value_1000usd
        FROM raw_year
        """
    ).fetchone()

    log(f"[{year}] Filtering the final 160-economy sample ...")
    create_selected_year_table(con)

    # selected_year is materialized, so raw_year can now be dropped
    # to reduce temporary storage pressure.
    con.execute("DROP TABLE raw_year")

    selected_stats = con.execute(
        """
        SELECT
            COUNT(*) AS selected_rows,
            SUM(trade_value_1000usd)
                AS selected_trade_value_1000usd
        FROM selected_year
        """
    ).fetchone()

    category_stats = con.execute(
        """
        SELECT
            COALESCE(final_end_use, 'unmapped')
                AS final_end_use,
            COUNT(*) AS number_of_rows,
            SUM(trade_value_1000usd)
                AS trade_value_1000usd
        FROM selected_year
        GROUP BY 1
        """
    ).fetchdf()

    category_lookup = {
        row["final_end_use"]: (
            int(row["number_of_rows"]),
            float(row["trade_value_1000usd"]),
        )
        for _, row in category_stats.iterrows()
    }

    def category_value(
        category: str,
    ) -> tuple[int, float]:
        return category_lookup.get(category, (0, 0.0))

    intermediate_rows, intermediate_value = (
        category_value("intermediate")
    )
    consumption_rows, consumption_value = (
        category_value("consumption")
    )
    capital_rows, capital_value = (
        category_value("capital")
    )
    ambiguous_rows, ambiguous_value = (
        category_value("ambiguous")
    )
    unallocated_rows, unallocated_value = (
        category_value("unallocated")
    )
    unmapped_rows, unmapped_value = (
        category_value("unmapped")
    )

    retained_rows = (
        intermediate_rows
        + consumption_rows
        + capital_rows
    )
    retained_value = (
        intermediate_value
        + consumption_value
        + capital_value
    )

    log(f"[{year}] Aggregating HS6 flows to pair–HS2–end-use ...")

    con.execute("BEGIN TRANSACTION")

    try:
        con.execute(
            """
            DELETE FROM positive_pair_hs2_enduse_year
            WHERE year = ?
            """,
            [year],
        )

        con.execute(
            """
            DELETE FROM annual_filter_audit
            WHERE year = ?
            """,
            [year],
        )

        con.execute(
            """
            INSERT INTO positive_pair_hs2_enduse_year
            SELECT
                year,
                exporter_code,
                importer_code,
                exporter_iso3,
                importer_iso3,
                hs2,
                final_end_use AS end_use,
                SUM(trade_value_1000usd)
                    AS trade_value_1000usd,
                COUNT(DISTINCT hs6)
                    AS positive_hs6_count,
                COUNT(*)
                    AS underlying_positive_flow_rows
            FROM selected_year
            WHERE final_end_use IN (
                'intermediate',
                'consumption',
                'capital'
            )
            GROUP BY
                year,
                exporter_code,
                importer_code,
                exporter_iso3,
                importer_iso3,
                hs2,
                final_end_use
            """
        )

        aggregate_rows = fetch_scalar(
            con,
            f"""
            SELECT COUNT(*)
            FROM positive_pair_hs2_enduse_year
            WHERE year = {year}
            """,
        )

        duplicate_keys = fetch_scalar(
            con,
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT
                    year,
                    exporter_code,
                    importer_code,
                    hs2,
                    end_use
                FROM positive_pair_hs2_enduse_year
                WHERE year = {year}
                GROUP BY
                    year,
                    exporter_code,
                    importer_code,
                    hs2,
                    end_use
                HAVING COUNT(*) > 1
            )
            """,
        )

        aggregate_nonpositive = fetch_scalar(
            con,
            f"""
            SELECT COUNT(*)
            FROM positive_pair_hs2_enduse_year
            WHERE year = {year}
              AND (
                  trade_value_1000usd IS NULL
                  OR trade_value_1000usd <= 0
              )
            """,
        )

        audit_status = (
            "PASS"
            if duplicate_keys == 0
            and aggregate_nonpositive == 0
            and aggregate_rows > 0
            else "REVIEW"
        )

        con.execute(
            """
            INSERT INTO annual_filter_audit VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                CURRENT_TIMESTAMP
            )
            """,
            [
                year,
                int(raw_stats[0] or 0),
                float(raw_stats[1] or 0),
                int(selected_stats[0] or 0),
                float(selected_stats[1] or 0),
                intermediate_rows,
                intermediate_value,
                consumption_rows,
                consumption_value,
                capital_rows,
                capital_value,
                ambiguous_rows,
                ambiguous_value,
                unallocated_rows,
                unallocated_value,
                unmapped_rows,
                unmapped_value,
                retained_rows,
                retained_value,
                int(aggregate_rows),
                int(duplicate_keys),
                audit_status,
            ],
        )

        con.execute("COMMIT")

    except Exception:
        con.execute("ROLLBACK")
        raise

    con.execute("CHECKPOINT")

    log(
        f"[{year}] Finished — "
        f"{int(aggregate_rows):,} positive aggregate rows; "
        f"status={audit_status}"
    )


def export_outputs(
    con: duckdb.DuckDBPyConnection,
) -> None:
    log("Creating final positive-flow aggregate tables ...")

    con.execute(
        """
        CREATE OR REPLACE TABLE
        positive_pair_hs2_year_intermediate AS
        SELECT
            year,
            exporter_code,
            importer_code,
            exporter_iso3,
            importer_iso3,
            hs2,
            trade_value_1000usd,
            positive_hs6_count,
            underlying_positive_flow_rows
        FROM positive_pair_hs2_enduse_year
        WHERE end_use = 'intermediate'
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE
        positive_pair_year_intermediate AS
        SELECT
            year,
            exporter_code,
            importer_code,
            exporter_iso3,
            importer_iso3,
            SUM(trade_value_1000usd)
                AS trade_value_1000usd,
            COUNT(*) AS positive_hs2_cells,
            SUM(positive_hs6_count)
                AS positive_hs6_cells,
            SUM(underlying_positive_flow_rows)
                AS underlying_positive_flow_rows
        FROM positive_pair_hs2_year_intermediate
        GROUP BY
            year,
            exporter_code,
            importer_code,
            exporter_iso3,
            importer_iso3
        """
    )

    # Delete old exported files before overwriting.
    for output_file in (
        OUTPUT_ALL_ENDUSES,
        OUTPUT_INTERMEDIATE_HS2,
        OUTPUT_INTERMEDIATE_PAIR_YEAR,
    ):
        if output_file.exists():
            output_file.unlink()

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM positive_pair_hs2_enduse_year
        )
        TO '{sql_path(OUTPUT_ALL_ENDUSES)}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD
        )
        """
    )

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM positive_pair_hs2_year_intermediate
        )
        TO '{sql_path(OUTPUT_INTERMEDIATE_HS2)}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD
        )
        """
    )

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM positive_pair_year_intermediate
        )
        TO '{sql_path(OUTPUT_INTERMEDIATE_PAIR_YEAR)}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD
        )
        """
    )

    annual_audit = con.execute(
        """
        SELECT *
        FROM annual_filter_audit
        ORDER BY year
        """
    ).fetchdf()

    annual_audit.to_csv(
        AUDIT_DIR / "step5_annual_trade_filter_audit.csv",
        index=False,
        encoding="utf-8-sig",
    )

    universe = con.execute(
        """
        SELECT
            hs2,
            end_use,
            COUNT(*) AS positive_pair_year_cells,
            COUNT(DISTINCT year) AS years_present,
            COUNT(DISTINCT exporter_code)
                AS exporters_present,
            COUNT(DISTINCT importer_code)
                AS importers_present,
            SUM(trade_value_1000usd)
                AS trade_value_1000usd,
            SUM(positive_hs6_count)
                AS summed_positive_hs6_counts
        FROM positive_pair_hs2_enduse_year
        GROUP BY hs2, end_use
        ORDER BY end_use, hs2
        """
    ).fetchdf()

    universe.to_csv(
        AUDIT_DIR / "step5_hs2_enduse_universe.csv",
        index=False,
        encoding="utf-8-sig",
    )

    pair_year = con.execute(
        """
        WITH pair_grid AS (
            SELECT
                e.analysis_iso3 AS exporter_iso3,
                d.analysis_iso3 AS importer_iso3,
                y.year
            FROM sample_country e
            CROSS JOIN sample_country d
            CROSS JOIN (
                SELECT year
                FROM range(2007, 2024) t(year)
            ) y
            WHERE e.country_code <> d.country_code
        ),
        positive AS (
            SELECT
                exporter_iso3,
                importer_iso3,
                year,
                trade_value_1000usd,
                positive_hs2_cells,
                positive_hs6_cells
            FROM positive_pair_year_intermediate
        )
        SELECT
            g.exporter_iso3,
            g.importer_iso3,
            g.year,
            COALESCE(p.trade_value_1000usd, 0)
                AS intermediate_trade_value_1000usd,
            COALESCE(p.positive_hs2_cells, 0)
                AS positive_hs2_cells,
            COALESCE(p.positive_hs6_cells, 0)
                AS positive_hs6_cells,
            (
                p.trade_value_1000usd IS NOT NULL
            ) AS has_positive_intermediate_trade
        FROM pair_grid g
        LEFT JOIN positive p
          ON g.exporter_iso3 = p.exporter_iso3
         AND g.importer_iso3 = p.importer_iso3
         AND g.year = p.year
        ORDER BY
            g.year,
            g.exporter_iso3,
            g.importer_iso3
        """
    ).fetchdf()

    pair_year.to_csv(
        AUDIT_DIR / "step5_pair_year_intermediate_coverage.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # Final checks and report
    # --------------------------------------------------------
    total_raw_rows = int(
        annual_audit["raw_rows"].sum()
    )
    total_selected_rows = int(
        annual_audit["selected_country_rows"].sum()
    )
    total_raw_value = float(
        annual_audit["raw_trade_value_1000usd"].sum()
    )
    total_selected_value = float(
        annual_audit[
            "selected_country_trade_value_1000usd"
        ].sum()
    )
    total_retained_value = float(
        annual_audit[
            "retained_clean_trade_value_1000usd"
        ].sum()
    )
    total_intermediate_value = float(
        annual_audit[
            "intermediate_trade_value_1000usd"
        ].sum()
    )
    total_consumption_value = float(
        annual_audit[
            "consumption_trade_value_1000usd"
        ].sum()
    )
    total_capital_value = float(
        annual_audit[
            "capital_trade_value_1000usd"
        ].sum()
    )

    aggregate_counts = con.execute(
        """
        SELECT
            COUNT(*) AS all_enduse_rows,
            COUNT(*) FILTER (
                WHERE end_use = 'intermediate'
            ) AS intermediate_rows,
            COUNT(*) FILTER (
                WHERE end_use = 'consumption'
            ) AS consumption_rows,
            COUNT(*) FILTER (
                WHERE end_use = 'capital'
            ) AS capital_rows
        FROM positive_pair_hs2_enduse_year
        """
    ).fetchone()

    pair_year_rows = con.execute(
        """
        SELECT COUNT(*)
        FROM positive_pair_year_intermediate
        """
    ).fetchone()[0]

    expected_pair_year_rows = (
        160 * 159 * (END_YEAR - START_YEAR + 1)
    )

    positive_pair_year_share = (
        pair_year[
            "has_positive_intermediate_trade"
        ].mean()
    )

    pass_years = int(
        annual_audit["audit_status"].eq("PASS").sum()
    )

    duplicate_total = int(
        annual_audit[
            "duplicate_aggregate_keys"
        ].sum()
    )

    report_lines = [
        "=" * 92,
        "AIID DTA–GPR PROJECT — STEP 5 TRADE AGGREGATION AUDIT",
        "=" * 92,
        f"Project root: {PROJECT_ROOT}",
        f"Years processed: {START_YEAR}–{END_YEAR}",
        "",
        "A. ANNUAL PROCESSING",
        "-" * 92,
        (
            f"Years with PASS status: {pass_years} of "
            f"{END_YEAR - START_YEAR + 1}"
        ),
        f"Raw BACI rows: {total_raw_rows:,}",
        (
            "Rows with both partners in the final sample: "
            f"{total_selected_rows:,} "
            f"({total_selected_rows / total_raw_rows:.4%})"
        ),
        (
            "Trade-value share with both partners in the "
            f"final sample: {total_selected_value / total_raw_value:.6%}"
        ),
        (
            "Trade-value share retained in clean intermediate, "
            "consumption or capital classes: "
            f"{total_retained_value / total_selected_value:.6%}"
        ),
        f"Duplicate aggregate keys: {duplicate_total:,}",
        "",
        "B. CLEAN END-USE TRADE VALUES",
        "-" * 92,
        (
            "Intermediate share of selected-country trade: "
            f"{total_intermediate_value / total_selected_value:.6%}"
        ),
        (
            "Consumption share of selected-country trade: "
            f"{total_consumption_value / total_selected_value:.6%}"
        ),
        (
            "Capital share of selected-country trade: "
            f"{total_capital_value / total_selected_value:.6%}"
        ),
        "",
        "C. POSITIVE AGGREGATE TABLES",
        "-" * 92,
        (
            "Pair–HS2–end-use–year positive rows: "
            f"{int(aggregate_counts[0]):,}"
        ),
        (
            "Intermediate pair–HS2–year positive rows: "
            f"{int(aggregate_counts[1]):,}"
        ),
        (
            "Consumption pair–HS2–year positive rows: "
            f"{int(aggregate_counts[2]):,}"
        ),
        (
            "Capital pair–HS2–year positive rows: "
            f"{int(aggregate_counts[3]):,}"
        ),
        (
            "Positive intermediate pair–year rows: "
            f"{int(pair_year_rows):,}"
        ),
        (
            "Complete directed pair–year grid size: "
            f"{expected_pair_year_rows:,}"
        ),
        (
            "Share of directed pair–years with positive "
            "intermediate trade: "
            f"{positive_pair_year_share:.6%}"
        ),
        "",
        "D. OUTPUT FILES",
        "-" * 92,
        "data/interim/trade_positive_pair_hs2_enduse_year.parquet",
        "data/interim/trade_positive_pair_hs2_year_intermediate.parquet",
        "data/interim/trade_positive_pair_year_intermediate.parquet",
        "outputs/audit/step5_annual_trade_filter_audit.csv",
        "outputs/audit/step5_hs2_enduse_universe.csv",
        "outputs/audit/step5_pair_year_intermediate_coverage.csv",
        "outputs/audit/step5_trade_aggregation_audit.txt",
        "",
        "E. IMPORTANT",
        "-" * 92,
        (
            "These are positive-flow aggregates only. "
            "Do not run the final PPML yet."
        ),
        (
            "Structural zeros will be created later, after the "
            "DTA pair-year treatment and GPR series have been "
            "constructed and checked."
        ),
    ]

    REPORT_FILE.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    log("")
    log("\n".join(report_lines))


def main() -> None:
    verify_inputs()

    log("=" * 92)
    log("STEP 5 — BUILD POSITIVE TRADE AGGREGATES")
    log("=" * 92)
    log(f"Database: {DATABASE_FILE}")
    log(
        "This script reads one BACI annual file at a time "
        "and can resume after interruption."
    )
    log("")

    con = duckdb.connect(str(DATABASE_FILE))

    con.execute(
        f"SET temp_directory = '{sql_path(TEMP_DIR)}'"
    )
    con.execute("SET preserve_insertion_order = false")

    create_database_tables(con)
    load_reference_tables(con)

    for year in range(START_YEAR, END_YEAR + 1):
        process_year(con, year)

    export_outputs(con)
    con.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        failure_lines = [
            "=" * 92,
            "STEP 5 FAILED",
            "=" * 92,
            f"{type(error).__name__}: {error}",
            "",
            traceback.format_exc(),
        ]

        REPORT_FILE.write_text(
            "\n".join(failure_lines),
            encoding="utf-8",
        )

        print("\n".join(failure_lines), flush=True)
        sys.exit(1)

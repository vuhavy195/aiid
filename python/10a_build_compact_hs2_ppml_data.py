from __future__ import annotations

from pathlib import Path
import os
import sys
import traceback

import duckdb
import pandas as pd


# ============================================================
# AIID DTA–GPR PROJECT
# STEP 10A — BUILD COMPACT HS2 PPML DATA FOR R
# ============================================================
PROJECT_ROOT = Path(
    os.environ.get(
        "AIID_PROJECT_ROOT",
        r"H:\AIID_DTA_GPR",
    )
)

HS2_PANEL_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "estimation_pair_hs2_year_intermediate"
)

COUNTRY_SAMPLE_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "country_sample_160.csv"
)

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"
TEMP_DIR = INTERIM_DIR / "duckdb_temp_step10a"

INTERIM_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_FILE = INTERIM_DIR / "step10a_compact_hs2.duckdb"

COMPACT_OUTPUT = (
    PROCESSED_DIR
    / "estimation_hs2_ppml_compact.parquet"
)

REPORT_FILE = (
    AUDIT_DIR
    / "step10a_compact_hs2_audit.txt"
)

SUMMARY_FILE = (
    AUDIT_DIR
    / "step10a_compact_hs2_summary.csv"
)

EXPECTED_FULL_ROWS = 16_754_554
EXPECTED_BASELINE_MISSING_ROWS = 2_093
EXPECTED_BASELINE_ROWS = (
    EXPECTED_FULL_ROWS
    - EXPECTED_BASELINE_MISSING_ROWS
)


def sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def validate_inputs() -> None:
    if not HS2_PANEL_DIR.exists():
        raise FileNotFoundError(
            f"HS2 panel directory not found: {HS2_PANEL_DIR}"
        )

    parquet_files = list(
        HS2_PANEL_DIR.rglob("*.parquet")
    )

    if not parquet_files:
        raise FileNotFoundError(
            "No Parquet files were found inside the "
            "year-partitioned HS2 panel directory."
        )

    if not COUNTRY_SAMPLE_FILE.exists():
        raise FileNotFoundError(
            f"Country sample file not found: "
            f"{COUNTRY_SAMPLE_FILE}"
        )


def create_views(
    con: duckdb.DuckDBPyConnection,
) -> None:
    panel_glob = (
        HS2_PANEL_DIR
        / "**"
        / "*.parquet"
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW hs2_source AS
        SELECT *
        FROM read_parquet(
            '{sql_path(panel_glob)}',
            hive_partitioning = true,
            union_by_name = true
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE country_rank AS
        SELECT
            TRY_CAST(country_code AS INTEGER)
                AS country_code,
            TRY_CAST(final_sample_rank AS INTEGER)
                AS final_sample_rank,
            TRIM(analysis_iso3)
                AS analysis_iso3
        FROM read_csv(
            '{sql_path(COUNTRY_SAMPLE_FILE)}',
            header = true,
            all_varchar = true
        )
        """
    )

    rank_check = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT country_code)
                AS unique_country_codes,
            COUNT(DISTINCT final_sample_rank)
                AS unique_ranks,
            MIN(final_sample_rank)
                AS minimum_rank,
            MAX(final_sample_rank)
                AS maximum_rank
        FROM country_rank
        """
    ).fetchone()

    if rank_check != (160, 160, 160, 1, 160):
        raise ValueError(
            "country_sample_160.csv failed its rank audit. "
            f"Observed: {rank_check}"
        )


def audit_source(
    con: duckdb.DuckDBPyConnection,
) -> tuple[int, int]:
    source_stats = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(*) FILTER (
                WHERE NOT baseline_depth_available
            ) AS unavailable_rows,
            COUNT(*) FILTER (
                WHERE baseline_depth_available
            ) AS baseline_rows,
            COUNT(*) FILTER (
                WHERE gpr_mean_z IS NULL
            ) AS missing_gpr_rows,
            COUNT(*) FILTER (
                WHERE trade_value_1000usd IS NULL
                   OR trade_value_1000usd < 0
            ) AS invalid_trade_rows,
            COUNT(
                DISTINCT
                exporter_iso3
                || '|'
                || importer_iso3
                || '|'
                || hs2
            ) AS supported_pair_hs2_groups,
            COUNT(DISTINCT hs2)
                AS distinct_hs2
        FROM hs2_source
        """
    ).fetchone()

    (
        rows,
        unavailable_rows,
        baseline_rows,
        missing_gpr_rows,
        invalid_trade_rows,
        supported_groups,
        distinct_hs2,
    ) = source_stats

    if rows != EXPECTED_FULL_ROWS:
        raise ValueError(
            f"Expected {EXPECTED_FULL_ROWS:,} HS2 rows, "
            f"found {rows:,}."
        )

    if unavailable_rows != EXPECTED_BASELINE_MISSING_ROWS:
        raise ValueError(
            "Unexpected number of rows lacking lagged DTA depth: "
            f"{unavailable_rows:,}."
        )

    if baseline_rows != EXPECTED_BASELINE_ROWS:
        raise ValueError(
            f"Expected {EXPECTED_BASELINE_ROWS:,} baseline rows, "
            f"found {baseline_rows:,}."
        )

    if missing_gpr_rows != 0:
        raise ValueError(
            f"Missing GPR rows detected: {missing_gpr_rows:,}."
        )

    if invalid_trade_rows != 0:
        raise ValueError(
            f"Invalid trade rows detected: {invalid_trade_rows:,}."
        )

    if supported_groups != 985_562:
        raise ValueError(
            "Unexpected number of supported pair-HS2 groups: "
            f"{supported_groups:,}."
        )

    if distinct_hs2 != 88:
        raise ValueError(
            f"Expected 88 HS2 chapters, found {distinct_hs2}."
        )

    return rows, baseline_rows


def write_compact_file(
    con: duckdb.DuckDBPyConnection,
) -> None:
    if COMPACT_OUTPUT.exists():
        COMPACT_OUTPUT.unlink()

    # Numeric fixed-effect identifiers substantially reduce the
    # R memory burden compared with several repeated string IDs.
    #
    # pair_index is unique for each directed exporter-importer pair:
    #   (exporter_rank - 1) * 160 + (importer_rank - 1)
    #
    # pair_hs2_fe_id then combines pair_index and the two-digit HS2.
    con.execute(
        f"""
        COPY (
            SELECT
                CAST(
                    h.trade_value_1000usd / 1000.0
                    AS DOUBLE
                ) AS trade_value_musd,

                CAST(h.year AS SMALLINT)
                    AS year,

                CAST(h.hs2 AS SMALLINT)
                    AS hs2,

                CAST(h.structural_zero AS BOOLEAN)
                    AS structural_zero,

                CAST(h.fta_active_l1 AS TINYINT)
                    AS fta_active_l1,

                CAST(
                    h.depth_strict_l1_10
                    AS DOUBLE
                ) AS depth_strict_l1_10,

                CAST(
                    h.gpr_x_fta_l1
                    AS DOUBLE
                ) AS gpr_x_fta_l1,

                CAST(
                    h.gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS gpr_x_depth_strict_l1_10,

                CAST(
                    h.log_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS log_gpr_x_depth_strict_l1_10,

                CAST(
                    h.threat_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS threat_gpr_x_depth_strict_l1_10,

                CAST(
                    h.act_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS act_gpr_x_depth_strict_l1_10,

                CAST(
                    h.max_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS max_gpr_x_depth_strict_l1_10,

                CAST(
                    (
                        (er.final_sample_rank - 1) * 160
                        + (ir.final_sample_rank - 1)
                    ) * 100
                    + CAST(h.hs2 AS INTEGER)
                    AS BIGINT
                ) AS pair_hs2_fe_id,

                CAST(
                    (er.final_sample_rank - 1) * 100
                    + (h.year - 2000)
                    AS INTEGER
                ) AS exporter_year_fe_id,

                CAST(
                    (ir.final_sample_rank - 1) * 100
                    + (h.year - 2000)
                    AS INTEGER
                ) AS importer_year_fe_id,

                CAST(
                    CAST(h.hs2 AS INTEGER) * 100
                    + (h.year - 2000)
                    AS INTEGER
                ) AS hs2_year_fe_id,

                CAST(
                    (
                        LEAST(
                            er.final_sample_rank,
                            ir.final_sample_rank
                        ) - 1
                    ) * 160
                    + (
                        GREATEST(
                            er.final_sample_rank,
                            ir.final_sample_rank
                        ) - 1
                    )
                    AS INTEGER
                ) AS unordered_pair_cluster_id

            FROM hs2_source h

            INNER JOIN country_rank er
                ON h.exporter_code = er.country_code

            INNER JOIN country_rank ir
                ON h.importer_code = ir.country_code

            WHERE h.baseline_depth_available
        )
        TO '{sql_path(COMPACT_OUTPUT)}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD,
            ROW_GROUP_SIZE 250000
        )
        """
    )


def audit_compact_file(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    con.execute(
        f"""
        CREATE OR REPLACE VIEW compact_data AS
        SELECT *
        FROM read_parquet(
            '{sql_path(COMPACT_OUTPUT)}'
        )
        """
    )

    stats = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(*) FILTER (
                WHERE structural_zero
            ) AS structural_zero_rows,
            COUNT(*) FILTER (
                WHERE trade_value_musd IS NULL
                   OR trade_value_musd < 0
            ) AS invalid_trade_rows,
            COUNT(*) FILTER (
                WHERE depth_strict_l1_10 IS NULL
                   OR gpr_x_depth_strict_l1_10 IS NULL
            ) AS missing_main_treatment_rows,
            COUNT(DISTINCT pair_hs2_fe_id)
                AS pair_hs2_fe_groups,
            COUNT(DISTINCT exporter_year_fe_id)
                AS exporter_year_fe_groups,
            COUNT(DISTINCT importer_year_fe_id)
                AS importer_year_fe_groups,
            COUNT(DISTINCT hs2_year_fe_id)
                AS hs2_year_fe_groups,
            COUNT(DISTINCT unordered_pair_cluster_id)
                AS unordered_pair_clusters,
            COUNT(DISTINCT year)
                AS years,
            COUNT(DISTINCT hs2)
                AS hs2_chapters,
            SUM(trade_value_musd)
                AS total_trade_value_musd,
            MIN(year) AS minimum_year,
            MAX(year) AS maximum_year
        FROM compact_data
        """
    ).fetchdf()

    row = stats.iloc[0]

    if int(row["rows"]) != EXPECTED_BASELINE_ROWS:
        raise ValueError(
            "Compact file row count does not match "
            "the baseline source row count."
        )

    if int(row["invalid_trade_rows"]) != 0:
        raise ValueError(
            "Compact file contains invalid trade values."
        )

    if int(row["missing_main_treatment_rows"]) != 0:
        raise ValueError(
            "Compact file contains missing main treatment values."
        )

    if int(row["pair_hs2_fe_groups"]) != 985_562:
        raise ValueError(
            "Compact pair-HS2 fixed-effect count is incorrect."
        )

    if int(row["unordered_pair_clusters"]) != 12_720:
        raise ValueError(
            "Compact unordered-pair cluster count is incorrect."
        )

    if int(row["years"]) != 17:
        raise ValueError(
            "Compact data does not contain 17 years."
        )

    if int(row["hs2_chapters"]) != 88:
        raise ValueError(
            "Compact data does not contain 88 HS2 chapters."
        )

    stats.to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    return stats


def write_report(
    source_rows: int,
    baseline_rows: int,
    compact_stats: pd.DataFrame,
) -> None:
    row = compact_stats.iloc[0]

    file_size_gb = (
        COMPACT_OUTPUT.stat().st_size
        / 1024
        / 1024
        / 1024
    )

    zero_share = (
        int(row["structural_zero_rows"])
        / int(row["rows"])
    )

    report_lines = [
        "=" * 96,
        "AIID DTA–GPR PROJECT — STEP 10A COMPACT HS2 DATA",
        "=" * 96,
        f"Project root: {PROJECT_ROOT}",
        "",
        "A. SOURCE PANEL",
        "-" * 96,
        f"Full pair-HS2-year rows: {source_rows:,}",
        (
            "Rows unavailable for lagged-depth baseline: "
            f"{source_rows - baseline_rows:,}"
        ),
        f"Baseline rows retained: {baseline_rows:,}",
        "",
        "B. COMPACT OUTPUT",
        "-" * 96,
        f"Rows: {int(row['rows']):,}",
        (
            "Structural-zero rows: "
            f"{int(row['structural_zero_rows']):,} "
            f"({zero_share:.6%})"
        ),
        (
            "Pair-HS2 fixed-effect groups: "
            f"{int(row['pair_hs2_fe_groups']):,}"
        ),
        (
            "Exporter-year fixed-effect groups: "
            f"{int(row['exporter_year_fe_groups']):,}"
        ),
        (
            "Importer-year fixed-effect groups: "
            f"{int(row['importer_year_fe_groups']):,}"
        ),
        (
            "HS2-year fixed-effect groups: "
            f"{int(row['hs2_year_fe_groups']):,}"
        ),
        (
            "Unordered-pair clusters: "
            f"{int(row['unordered_pair_clusters']):,}"
        ),
        (
            "Total intermediate trade value "
            f"(million USD): "
            f"{float(row['total_trade_value_musd']):,.4f}"
        ),
        (
            f"Compact Parquet size: {file_size_gb:.3f} GB"
        ),
        "",
        "C. VARIABLES",
        "-" * 96,
        "trade_value_musd",
        "year",
        "hs2",
        "structural_zero",
        "fta_active_l1",
        "depth_strict_l1_10",
        "gpr_x_fta_l1",
        "gpr_x_depth_strict_l1_10",
        "log_gpr_x_depth_strict_l1_10",
        "threat_gpr_x_depth_strict_l1_10",
        "act_gpr_x_depth_strict_l1_10",
        "max_gpr_x_depth_strict_l1_10",
        "pair_hs2_fe_id",
        "exporter_year_fe_id",
        "importer_year_fe_id",
        "hs2_year_fe_id",
        "unordered_pair_cluster_id",
        "",
        "D. OUTPUT FILES",
        "-" * 96,
        "data/processed/estimation_hs2_ppml_compact.parquet",
        "outputs/audit/step10a_compact_hs2_audit.txt",
        "outputs/audit/step10a_compact_hs2_summary.csv",
        "",
        "E. NEXT ACTION",
        "-" * 96,
        (
            "Send the audit report and summary CSV to ChatGPT "
            "before running the full R PPML."
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
    print("=" * 96)
    print("STEP 10A — BUILD COMPACT HS2 PPML DATA")
    print("=" * 96)
    print(f"Project root: {PROJECT_ROOT}")

    validate_inputs()

    con = duckdb.connect(str(DATABASE_FILE))

    con.execute(
        f"SET temp_directory = '{sql_path(TEMP_DIR)}'"
    )
    con.execute(
        "SET preserve_insertion_order = false"
    )

    print("Opening the partitioned HS2 panel ...")
    create_views(con)

    print("Auditing source rows ...")
    source_rows, baseline_rows = audit_source(con)

    print(
        "Writing a compact numeric Parquet file for R ..."
    )
    write_compact_file(con)

    print("Auditing the compact output ...")
    compact_stats = audit_compact_file(con)

    con.execute("CHECKPOINT")
    con.close()

    write_report(
        source_rows,
        baseline_rows,
        compact_stats,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        failure_lines = [
            "=" * 96,
            "STEP 10A FAILED",
            "=" * 96,
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

from __future__ import annotations

from pathlib import Path
import os
import sys
import traceback

import duckdb
import pandas as pd


# ============================================================
# AIID DTA–GPR PROJECT
# STEP 13A — BUILD HS2 TRADE-LINK SURVIVAL PANEL
#
# A bilateral HS2 link is "at risk" in year t when it had
# positive intermediate-goods trade in t-1.
#
# Outcome:
#   survive_t = 1 if trade remains positive in t
#             = 0 if the link disappears in t
#
# This step only builds and audits the panel.
# It does not estimate regressions.
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

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"
TEMP_DIR = INTERIM_DIR / "duckdb_temp_step13a"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
INTERIM_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = (
    PROCESSED_DIR
    / "estimation_hs2_trade_link_survival.parquet"
)

DATABASE_FILE = (
    INTERIM_DIR
    / "step13a_hs2_survival.duckdb"
)

REPORT_FILE = (
    AUDIT_DIR
    / "step13a_hs2_survival_audit.txt"
)

SUMMARY_FILE = (
    AUDIT_DIR
    / "step13a_hs2_survival_summary.csv"
)

YEAR_SUMMARY_FILE = (
    AUDIT_DIR
    / "step13a_hs2_survival_by_year.csv"
)

SECTOR_SUMMARY_FILE = (
    AUDIT_DIR
    / "step13a_hs2_survival_by_sector.csv"
)

EXPECTED_SOURCE_ROWS = 16_754_554
EXPECTED_PAIR_HS2_GROUPS = 985_562
EXPECTED_SOURCE_YEARS = 17
EXPECTED_SURVIVAL_YEARS = 16


def sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def validate_inputs() -> None:
    if not HS2_PANEL_DIR.exists():
        raise FileNotFoundError(
            f"HS2 panel directory not found: {HS2_PANEL_DIR}"
        )

    if not list(HS2_PANEL_DIR.rglob("*.parquet")):
        raise FileNotFoundError(
            "No Parquet files found in the HS2 panel directory."
        )

    if not COUNTRY_SAMPLE_FILE.exists():
        raise FileNotFoundError(
            f"Country sample file not found: "
            f"{COUNTRY_SAMPLE_FILE}"
        )


def create_source_views(
    con: duckdb.DuckDBPyConnection,
) -> None:
    panel_glob = HS2_PANEL_DIR / "**" / "*.parquet"

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
                AS final_sample_rank
        FROM read_csv(
            '{sql_path(COUNTRY_SAMPLE_FILE)}',
            header = true,
            all_varchar = true
        )
        """
    )


def validate_source(
    con: duckdb.DuckDBPyConnection,
) -> None:
    source_columns = {
        row[0]
        for row in con.execute(
            "DESCRIBE hs2_source"
        ).fetchall()
    }

    required_columns = {
        "exporter_code",
        "importer_code",
        "year",
        "hs2",
        "trade_value_1000usd",
        "baseline_depth_available",
        "fta_active_l1",
        "depth_strict_l1_10",
        "gpr_x_fta_l1",
        "gpr_x_depth_strict_l1_10",
        "log_gpr_x_depth_strict_l1_10",
        "threat_gpr_x_depth_strict_l1_10",
        "act_gpr_x_depth_strict_l1_10",
        "max_gpr_x_depth_strict_l1_10",
    }

    missing = required_columns - source_columns

    if missing:
        raise ValueError(
            "HS2 source is missing required columns: "
            f"{sorted(missing)}"
        )

    stats = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(
                DISTINCT
                CAST(exporter_code AS VARCHAR)
                || '|'
                || CAST(importer_code AS VARCHAR)
                || '|'
                || CAST(hs2 AS VARCHAR)
            ) AS pair_hs2_groups,
            COUNT(DISTINCT year) AS years,
            MIN(year) AS min_year,
            MAX(year) AS max_year,
            COUNT(*) FILTER (
                WHERE trade_value_1000usd IS NULL
                   OR trade_value_1000usd < 0
            ) AS invalid_outcomes
        FROM hs2_source
        """
    ).fetchone()

    expected = (
        EXPECTED_SOURCE_ROWS,
        EXPECTED_PAIR_HS2_GROUPS,
        EXPECTED_SOURCE_YEARS,
        2007,
        2023,
        0,
    )

    if stats != expected:
        raise ValueError(
            "HS2 source failed its audit. "
            f"Observed: {stats}; expected: {expected}."
        )


def build_lagged_source(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute(
        """
        CREATE OR REPLACE TABLE hs2_with_lags AS
        SELECT
            s.*,

            CAST(
                trade_value_1000usd > 0
                AS TINYINT
            ) AS positive_trade_calc,

            CAST(
                LAG(
                    trade_value_1000usd > 0
                ) OVER (
                    PARTITION BY
                        exporter_code,
                        importer_code,
                        hs2
                    ORDER BY year
                )
                AS TINYINT
            ) AS positive_trade_l1_calc,

            CAST(
                LAG(
                    trade_value_1000usd / 1000.0
                ) OVER (
                    PARTITION BY
                        exporter_code,
                        importer_code,
                        hs2
                    ORDER BY year
                )
                AS DOUBLE
            ) AS trade_value_l1_musd,

            CAST(
                year
                - LAG(year) OVER (
                    PARTITION BY
                        exporter_code,
                        importer_code,
                        hs2
                    ORDER BY year
                )
                AS SMALLINT
            ) AS year_gap

        FROM hs2_source s
        """
    )

    gap_failures = con.execute(
        """
        SELECT COUNT(*)
        FROM hs2_with_lags
        WHERE year > 2007
          AND year_gap <> 1
        """
    ).fetchone()[0]

    if gap_failures:
        raise ValueError(
            f"Detected {gap_failures:,} non-consecutive "
            "pair-HS2 year transitions."
        )


def write_survival_panel(
    con: duckdb.DuckDBPyConnection,
) -> None:
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    con.execute(
        f"""
        COPY (
            SELECT
                CAST(
                    s.positive_trade_calc
                    AS TINYINT
                ) AS survive_t,

                CAST(
                    1 - s.positive_trade_calc
                    AS TINYINT
                ) AS exit_t,

                CAST(
                    s.trade_value_1000usd / 1000.0
                    AS DOUBLE
                ) AS trade_value_t_musd,

                CAST(
                    s.trade_value_l1_musd
                    AS DOUBLE
                ) AS trade_value_l1_musd,

                CAST(
                    LN(
                        1.0 + s.trade_value_l1_musd
                    )
                    AS DOUBLE
                ) AS log1p_trade_value_l1_musd,

                CAST(s.year AS SMALLINT)
                    AS year,

                CAST(s.hs2 AS SMALLINT)
                    AS hs2,

                CAST(s.fta_active_l1 AS TINYINT)
                    AS fta_active_l1,

                CAST(
                    s.depth_strict_l1_10
                    AS DOUBLE
                ) AS depth_strict_l1_10,

                CAST(
                    s.gpr_x_fta_l1
                    AS DOUBLE
                ) AS gpr_x_fta_l1,

                CAST(
                    s.gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS gpr_x_depth_strict_l1_10,

                CAST(
                    s.log_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS log_gpr_x_depth_strict_l1_10,

                CAST(
                    s.threat_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS threat_gpr_x_depth_strict_l1_10,

                CAST(
                    s.act_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS act_gpr_x_depth_strict_l1_10,

                CAST(
                    s.max_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS max_gpr_x_depth_strict_l1_10,

                CAST(
                    (
                        (er.final_sample_rank - 1) * 160
                        + (ir.final_sample_rank - 1)
                    ) * 100
                    + CAST(s.hs2 AS INTEGER)
                    AS BIGINT
                ) AS pair_hs2_fe_id,

                CAST(
                    (er.final_sample_rank - 1) * 100
                    + (s.year - 2000)
                    AS INTEGER
                ) AS exporter_year_fe_id,

                CAST(
                    (ir.final_sample_rank - 1) * 100
                    + (s.year - 2000)
                    AS INTEGER
                ) AS importer_year_fe_id,

                CAST(
                    CAST(s.hs2 AS INTEGER) * 100
                    + (s.year - 2000)
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

            FROM hs2_with_lags s

            INNER JOIN country_rank er
                ON s.exporter_code = er.country_code

            INNER JOIN country_rank ir
                ON s.importer_code = ir.country_code

            WHERE
                s.year BETWEEN 2008 AND 2023
                AND s.positive_trade_l1_calc = 1
                AND s.baseline_depth_available
        )
        TO '{sql_path(OUTPUT_FILE)}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD,
            ROW_GROUP_SIZE 250000
        )
        """
    )


def sector_case_sql() -> str:
    return """
        CASE
            WHEN hs2 BETWEEN 1 AND 24
                THEN 'Agro-food inputs'
            WHEN hs2 BETWEEN 25 AND 27
                THEN 'Minerals and fuels'
            WHEN hs2 BETWEEN 28 AND 38
                THEN 'Chemicals'
            WHEN hs2 BETWEEN 39 AND 43
                THEN 'Plastics, rubber and leather'
            WHEN hs2 BETWEEN 44 AND 49
                THEN 'Wood, pulp and paper'
            WHEN hs2 BETWEEN 50 AND 67
                THEN 'Textiles and footwear'
            WHEN hs2 BETWEEN 68 AND 83
                THEN 'Stone, glass and base metals'
            WHEN hs2 BETWEEN 84 AND 85
                THEN 'Machinery and electronics'
            WHEN hs2 BETWEEN 86 AND 89
                THEN 'Transport equipment'
            ELSE 'Precision and other manufactures'
        END
    """


def audit_output(
    con: duckdb.DuckDBPyConnection,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    con.execute(
        f"""
        CREATE OR REPLACE VIEW survival_panel AS
        SELECT *
        FROM read_parquet(
            '{sql_path(OUTPUT_FILE)}'
        )
        """
    )

    basic = con.execute(
        """
        SELECT
            COUNT(*) AS at_risk_rows,
            SUM(survive_t) AS surviving_rows,
            SUM(exit_t) AS exiting_rows,
            AVG(survive_t) AS survival_rate,
            AVG(exit_t) AS exit_rate,
            COUNT(DISTINCT pair_hs2_fe_id)
                AS at_risk_pair_hs2_groups,
            COUNT(DISTINCT unordered_pair_cluster_id)
                AS unordered_pair_clusters,
            COUNT(DISTINCT year) AS years,
            MIN(year) AS min_year,
            MAX(year) AS max_year,
            COUNT(*) FILTER (
                WHERE survive_t IS NULL
                   OR exit_t IS NULL
                   OR trade_value_l1_musd IS NULL
                   OR gpr_x_fta_l1 IS NULL
                   OR gpr_x_depth_strict_l1_10 IS NULL
            ) AS rows_with_missing_values,
            COUNT(*) FILTER (
                WHERE survive_t + exit_t <> 1
            ) AS invalid_binary_rows
        FROM survival_panel
        """
    ).fetchdf()

    row = basic.iloc[0]

    if int(row["at_risk_rows"]) <= 0:
        raise ValueError(
            "The survival panel is empty."
        )

    if int(row["years"]) != EXPECTED_SURVIVAL_YEARS:
        raise ValueError(
            "Unexpected survival-panel year coverage."
        )

    if (
        int(row["min_year"]) != 2008
        or int(row["max_year"]) != 2023
    ):
        raise ValueError(
            "Survival panel must span 2008–2023."
        )

    if int(row["rows_with_missing_values"]) != 0:
        raise ValueError(
            "Missing values detected in survival panel."
        )

    if int(row["invalid_binary_rows"]) != 0:
        raise ValueError(
            "Invalid survival/exit coding detected."
        )

    year_summary = con.execute(
        """
        SELECT
            year,
            COUNT(*) AS at_risk_links,
            SUM(survive_t) AS surviving_links,
            SUM(exit_t) AS exiting_links,
            AVG(survive_t) AS survival_rate,
            AVG(exit_t) AS exit_rate
        FROM survival_panel
        GROUP BY year
        ORDER BY year
        """
    ).fetchdf()

    sector_summary = con.execute(
        f"""
        SELECT
            {sector_case_sql()} AS sector,
            COUNT(*) AS at_risk_links,
            SUM(survive_t) AS surviving_links,
            SUM(exit_t) AS exiting_links,
            AVG(survive_t) AS survival_rate,
            AVG(exit_t) AS exit_rate
        FROM survival_panel
        GROUP BY sector
        ORDER BY sector
        """
    ).fetchdf()

    basic.to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    year_summary.to_csv(
        YEAR_SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    sector_summary.to_csv(
        SECTOR_SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    return basic, year_summary, sector_summary


def write_report(
    basic: pd.DataFrame,
    year_summary: pd.DataFrame,
    sector_summary: pd.DataFrame,
) -> None:
    row = basic.iloc[0]

    file_size_gb = (
        OUTPUT_FILE.stat().st_size
        / 1024
        / 1024
        / 1024
    )

    highest_exit_year = year_summary.loc[
        year_summary["exit_rate"].idxmax()
    ]

    lowest_survival_sector = sector_summary.loc[
        sector_summary["survival_rate"].idxmin()
    ]

    report_lines = [
        "=" * 100,
        "AIID DTA–GPR PROJECT — STEP 13A HS2 TRADE-LINK SURVIVAL PANEL",
        "=" * 100,
        f"Project root: {PROJECT_ROOT}",
        "",
        "A. OUTCOME DEFINITION",
        "-" * 100,
        (
            "A pair-HS2 link enters the risk set in year t "
            "when intermediate trade was positive in t-1."
        ),
        (
            "survive_t = 1 when the link remains positive in t; "
            "survive_t = 0 when it disappears."
        ),
        "",
        "B. PANEL AUDIT",
        "-" * 100,
        f"At-risk link-year rows: {int(row['at_risk_rows']):,}",
        f"Surviving rows: {int(row['surviving_rows']):,}",
        f"Exiting rows: {int(row['exiting_rows']):,}",
        f"Overall survival rate: {float(row['survival_rate']):.6%}",
        f"Overall exit rate: {float(row['exit_rate']):.6%}",
        (
            "At-risk pair-HS2 groups: "
            f"{int(row['at_risk_pair_hs2_groups']):,}"
        ),
        (
            "Unordered-pair clusters: "
            f"{int(row['unordered_pair_clusters']):,}"
        ),
        (
            f"Years: {int(row['min_year'])}–"
            f"{int(row['max_year'])}"
        ),
        (
            f"Output Parquet size: {file_size_gb:.3f} GB"
        ),
        "",
        "C. DESCRIPTIVE CHECKS",
        "-" * 100,
        (
            "Year with highest exit rate: "
            f"{int(highest_exit_year['year'])} "
            f"({float(highest_exit_year['exit_rate']):.6%})"
        ),
        (
            "Sector with lowest survival rate: "
            f"{lowest_survival_sector['sector']} "
            f"({float(lowest_survival_sector['survival_rate']):.6%})"
        ),
        "",
        "D. OUTPUT FILES",
        "-" * 100,
        "data/processed/estimation_hs2_trade_link_survival.parquet",
        "outputs/audit/step13a_hs2_survival_audit.txt",
        "outputs/audit/step13a_hs2_survival_summary.csv",
        "outputs/audit/step13a_hs2_survival_by_year.csv",
        "outputs/audit/step13a_hs2_survival_by_sector.csv",
        "",
        "E. NEXT ACTION",
        "-" * 100,
        (
            "Send the audit report and three summary CSVs "
            "to ChatGPT before estimating survival models."
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
    print("=" * 100)
    print("STEP 13A — BUILD HS2 TRADE-LINK SURVIVAL PANEL")
    print("=" * 100)
    print(f"Project root: {PROJECT_ROOT}")

    validate_inputs()

    con = duckdb.connect(str(DATABASE_FILE))

    con.execute(
        f"SET temp_directory = '{sql_path(TEMP_DIR)}'"
    )
    con.execute(
        "SET preserve_insertion_order = false"
    )

    print("Opening the full pair-HS2-year panel ...")
    create_source_views(con)

    print("Auditing source coverage ...")
    validate_source(con)

    print("Constructing lagged trade-link status ...")
    build_lagged_source(con)

    print("Writing the at-risk survival panel ...")
    write_survival_panel(con)

    print("Auditing survival outcomes ...")
    basic, year_summary, sector_summary = audit_output(con)

    con.execute("CHECKPOINT")
    con.close()

    write_report(
        basic,
        year_summary,
        sector_summary,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        failure_lines = [
            "=" * 100,
            "STEP 13A FAILED",
            "=" * 100,
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

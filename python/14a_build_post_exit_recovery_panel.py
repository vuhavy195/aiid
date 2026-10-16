from __future__ import annotations

from pathlib import Path
import os
import sys
import traceback

import duckdb
import pandas as pd


# ============================================================
# AIID DTA–GPR PROJECT
# STEP 14A — BUILD POST-EXIT RECOVERY PANEL
#
# Recovery event:
# - A pair-HS2 link traded positively in t-1.
# - The link disappears in t.
#
# Outcomes:
# - reenter_1y: positive trade returns in t+1.
# - reenter_within_2y: positive trade returns in t+1 or t+2.
# - full_recovery_1y: trade in t+1 reaches its pre-exit level.
# - full_recovery_within_2y: the maximum of t+1 and t+2
#   reaches the pre-exit level.
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
TEMP_DIR = INTERIM_DIR / "duckdb_temp_step14a"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
INTERIM_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = (
    PROCESSED_DIR
    / "estimation_hs2_post_exit_recovery.parquet"
)

DATABASE_FILE = (
    INTERIM_DIR
    / "step14a_hs2_recovery.duckdb"
)

REPORT_FILE = (
    AUDIT_DIR
    / "step14a_hs2_recovery_audit.txt"
)

SUMMARY_FILE = (
    AUDIT_DIR
    / "step14a_hs2_recovery_summary.csv"
)

YEAR_FILE = (
    AUDIT_DIR
    / "step14a_hs2_recovery_by_exit_year.csv"
)

SECTOR_FILE = (
    AUDIT_DIR
    / "step14a_hs2_recovery_by_sector.csv"
)

EXPECTED_SOURCE_ROWS = 16_754_554
EXPECTED_PAIR_HS2_GROUPS = 985_562
EXPECTED_EXIT_EVENTS = 1_237_520


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
            ) AS invalid_trade_rows
        FROM hs2_source
        """
    ).fetchone()

    expected = (
        EXPECTED_SOURCE_ROWS,
        EXPECTED_PAIR_HS2_GROUPS,
        17,
        2007,
        2023,
        0,
    )

    if stats != expected:
        raise ValueError(
            "HS2 source failed its audit. "
            f"Observed: {stats}; expected: {expected}."
        )


def build_dynamic_source(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute(
        """
        CREATE OR REPLACE TABLE hs2_dynamics AS
        SELECT
            s.*,

            CAST(
                CASE
                    WHEN trade_value_1000usd > 0
                    THEN 1
                    ELSE 0
                END
                AS TINYINT
            ) AS positive_calc,

            CAST(
                LAG(
                    CASE
                        WHEN trade_value_1000usd > 0
                        THEN 1
                        ELSE 0
                    END
                ) OVER (
                    PARTITION BY
                        exporter_code,
                        importer_code,
                        hs2
                    ORDER BY year
                )
                AS TINYINT
            ) AS positive_l1_calc,

            CAST(
                LEAD(
                    CASE
                        WHEN trade_value_1000usd > 0
                        THEN 1
                        ELSE 0
                    END,
                    1
                ) OVER (
                    PARTITION BY
                        exporter_code,
                        importer_code,
                        hs2
                    ORDER BY year
                )
                AS TINYINT
            ) AS positive_f1_calc,

            CAST(
                LEAD(
                    CASE
                        WHEN trade_value_1000usd > 0
                        THEN 1
                        ELSE 0
                    END,
                    2
                ) OVER (
                    PARTITION BY
                        exporter_code,
                        importer_code,
                        hs2
                    ORDER BY year
                )
                AS TINYINT
            ) AS positive_f2_calc,

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
            ) AS trade_l1_musd,

            CAST(
                LEAD(
                    trade_value_1000usd / 1000.0,
                    1
                ) OVER (
                    PARTITION BY
                        exporter_code,
                        importer_code,
                        hs2
                    ORDER BY year
                )
                AS DOUBLE
            ) AS trade_f1_musd,

            CAST(
                LEAD(
                    trade_value_1000usd / 1000.0,
                    2
                ) OVER (
                    PARTITION BY
                        exporter_code,
                        importer_code,
                        hs2
                    ORDER BY year
                )
                AS DOUBLE
            ) AS trade_f2_musd,

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
            ) AS lag_year_gap,

            CAST(
                LEAD(year, 1) OVER (
                    PARTITION BY
                        exporter_code,
                        importer_code,
                        hs2
                    ORDER BY year
                )
                - year
                AS SMALLINT
            ) AS lead1_year_gap,

            CAST(
                LEAD(year, 2) OVER (
                    PARTITION BY
                        exporter_code,
                        importer_code,
                        hs2
                    ORDER BY year
                )
                - year
                AS SMALLINT
            ) AS lead2_year_gap

        FROM hs2_source s
        """
    )

    gap_failures = con.execute(
        """
        SELECT COUNT(*)
        FROM hs2_dynamics
        WHERE
            (year > 2007 AND lag_year_gap <> 1)
            OR
            (year < 2023 AND lead1_year_gap <> 1)
            OR
            (year < 2022 AND lead2_year_gap <> 2)
        """
    ).fetchone()[0]

    if gap_failures:
        raise ValueError(
            f"Detected {gap_failures:,} non-consecutive "
            "pair-HS2 transitions."
        )


def write_recovery_panel(
    con: duckdb.DuckDBPyConnection,
) -> None:
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    con.execute(
        f"""
        COPY (
            SELECT
                CAST(d.year AS SMALLINT)
                    AS exit_year,

                CAST(d.hs2 AS SMALLINT)
                    AS hs2,

                CAST(
                    d.trade_l1_musd
                    AS DOUBLE
                ) AS pre_exit_trade_musd,

                CAST(
                    LN(1.0 + d.trade_l1_musd)
                    AS DOUBLE
                ) AS log1p_pre_exit_trade_musd,

                CAST(
                    CASE
                        WHEN d.year <= 2022
                        THEN 1
                        ELSE 0
                    END
                    AS TINYINT
                ) AS reentry_1y_available,

                CAST(
                    CASE
                        WHEN d.year <= 2022
                        THEN d.positive_f1_calc
                        ELSE NULL
                    END
                    AS TINYINT
                ) AS reenter_1y,

                CAST(
                    CASE
                        WHEN d.year <= 2021
                        THEN 1
                        ELSE 0
                    END
                    AS TINYINT
                ) AS reentry_2y_available,

                CAST(
                    CASE
                        WHEN d.year <= 2021
                        THEN GREATEST(
                            d.positive_f1_calc,
                            d.positive_f2_calc
                        )
                        ELSE NULL
                    END
                    AS TINYINT
                ) AS reenter_within_2y,

                CAST(
                    CASE
                        WHEN d.year <= 2022
                        THEN d.trade_f1_musd
                        ELSE NULL
                    END
                    AS DOUBLE
                ) AS trade_1y_after_exit_musd,

                CAST(
                    CASE
                        WHEN d.year <= 2021
                        THEN GREATEST(
                            d.trade_f1_musd,
                            d.trade_f2_musd
                        )
                        ELSE NULL
                    END
                    AS DOUBLE
                ) AS maximum_trade_within_2y_musd,

                CAST(
                    CASE
                        WHEN d.year <= 2022
                        THEN
                            CASE
                                WHEN d.trade_f1_musd
                                     >= d.trade_l1_musd
                                THEN 1
                                ELSE 0
                            END
                        ELSE NULL
                    END
                    AS TINYINT
                ) AS full_recovery_1y,

                CAST(
                    CASE
                        WHEN d.year <= 2021
                        THEN
                            CASE
                                WHEN GREATEST(
                                    d.trade_f1_musd,
                                    d.trade_f2_musd
                                ) >= d.trade_l1_musd
                                THEN 1
                                ELSE 0
                            END
                        ELSE NULL
                    END
                    AS TINYINT
                ) AS full_recovery_within_2y,

                CAST(
                    CASE
                        WHEN d.year <= 2022
                        THEN
                            LN(1.0 + d.trade_f1_musd)
                            - LN(1.0 + d.trade_l1_musd)
                        ELSE NULL
                    END
                    AS DOUBLE
                ) AS log_recovery_gap_1y,

                CAST(d.fta_active_l1 AS TINYINT)
                    AS fta_active_l1,

                CAST(
                    d.depth_strict_l1_10
                    AS DOUBLE
                ) AS depth_strict_l1_10,

                CAST(
                    d.gpr_x_fta_l1
                    AS DOUBLE
                ) AS gpr_x_fta_l1,

                CAST(
                    d.gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS gpr_x_depth_strict_l1_10,

                CAST(
                    d.log_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS log_gpr_x_depth_strict_l1_10,

                CAST(
                    d.threat_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS threat_gpr_x_depth_strict_l1_10,

                CAST(
                    d.act_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS act_gpr_x_depth_strict_l1_10,

                CAST(
                    d.max_gpr_x_depth_strict_l1_10
                    AS DOUBLE
                ) AS max_gpr_x_depth_strict_l1_10,

                CAST(
                    (
                        (er.final_sample_rank - 1) * 160
                        + (ir.final_sample_rank - 1)
                    ) * 100
                    + CAST(d.hs2 AS INTEGER)
                    AS BIGINT
                ) AS pair_hs2_fe_id,

                CAST(
                    (er.final_sample_rank - 1) * 100
                    + (d.year - 2000)
                    AS INTEGER
                ) AS exporter_exit_year_fe_id,

                CAST(
                    (ir.final_sample_rank - 1) * 100
                    + (d.year - 2000)
                    AS INTEGER
                ) AS importer_exit_year_fe_id,

                CAST(
                    CAST(d.hs2 AS INTEGER) * 100
                    + (d.year - 2000)
                    AS INTEGER
                ) AS hs2_exit_year_fe_id,

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

            FROM hs2_dynamics d

            INNER JOIN country_rank er
                ON d.exporter_code = er.country_code

            INNER JOIN country_rank ir
                ON d.importer_code = ir.country_code

            WHERE
                d.year BETWEEN 2008 AND 2023
                AND d.positive_l1_calc = 1
                AND d.positive_calc = 0
                AND d.baseline_depth_available
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
        CREATE OR REPLACE VIEW recovery_panel AS
        SELECT *
        FROM read_parquet(
            '{sql_path(OUTPUT_FILE)}'
        )
        """
    )

    basic = con.execute(
        """
        SELECT
            COUNT(*) AS exit_events,
            COUNT(*) FILTER (
                WHERE reentry_1y_available = 1
            ) AS one_year_available_events,
            COUNT(*) FILTER (
                WHERE reentry_2y_available = 1
            ) AS two_year_available_events,
            AVG(reenter_1y) FILTER (
                WHERE reentry_1y_available = 1
            ) AS reentry_rate_1y,
            AVG(reenter_within_2y) FILTER (
                WHERE reentry_2y_available = 1
            ) AS reentry_rate_within_2y,
            AVG(full_recovery_1y) FILTER (
                WHERE reentry_1y_available = 1
            ) AS full_recovery_rate_1y,
            AVG(full_recovery_within_2y) FILTER (
                WHERE reentry_2y_available = 1
            ) AS full_recovery_rate_within_2y,
            COUNT(DISTINCT pair_hs2_fe_id)
                AS pair_hs2_groups,
            COUNT(DISTINCT unordered_pair_cluster_id)
                AS unordered_pair_clusters,
            COUNT(DISTINCT exit_year)
                AS exit_years,
            MIN(exit_year) AS minimum_exit_year,
            MAX(exit_year) AS maximum_exit_year,
            COUNT(*) FILTER (
                WHERE pre_exit_trade_musd IS NULL
                   OR pre_exit_trade_musd <= 0
                   OR fta_active_l1 IS NULL
                   OR depth_strict_l1_10 IS NULL
                   OR gpr_x_fta_l1 IS NULL
                   OR gpr_x_depth_strict_l1_10 IS NULL
            ) AS invalid_core_rows,
            COUNT(*) FILTER (
                WHERE reentry_1y_available = 1
                  AND reenter_1y NOT IN (0, 1)
            ) AS invalid_one_year_rows,
            COUNT(*) FILTER (
                WHERE reentry_2y_available = 1
                  AND reenter_within_2y NOT IN (0, 1)
            ) AS invalid_two_year_rows
        FROM recovery_panel
        """
    ).fetchdf()

    row = basic.iloc[0]

    if int(row["exit_events"]) != EXPECTED_EXIT_EVENTS:
        raise ValueError(
            f"Expected {EXPECTED_EXIT_EVENTS:,} exit events, "
            f"found {int(row['exit_events']):,}."
        )

    if int(row["invalid_core_rows"]) != 0:
        raise ValueError(
            "Invalid core values detected in recovery panel."
        )

    if int(row["invalid_one_year_rows"]) != 0:
        raise ValueError(
            "Invalid one-year re-entry coding detected."
        )

    if int(row["invalid_two_year_rows"]) != 0:
        raise ValueError(
            "Invalid two-year re-entry coding detected."
        )

    year_summary = con.execute(
        """
        SELECT
            exit_year,
            COUNT(*) AS exit_events,
            AVG(reenter_1y) FILTER (
                WHERE reentry_1y_available = 1
            ) AS reentry_rate_1y,
            AVG(reenter_within_2y) FILTER (
                WHERE reentry_2y_available = 1
            ) AS reentry_rate_within_2y,
            AVG(full_recovery_1y) FILTER (
                WHERE reentry_1y_available = 1
            ) AS full_recovery_rate_1y,
            AVG(full_recovery_within_2y) FILTER (
                WHERE reentry_2y_available = 1
            ) AS full_recovery_rate_within_2y
        FROM recovery_panel
        GROUP BY exit_year
        ORDER BY exit_year
        """
    ).fetchdf()

    sector_summary = con.execute(
        f"""
        SELECT
            {sector_case_sql()} AS sector,
            COUNT(*) AS exit_events,
            AVG(reenter_1y) FILTER (
                WHERE reentry_1y_available = 1
            ) AS reentry_rate_1y,
            AVG(reenter_within_2y) FILTER (
                WHERE reentry_2y_available = 1
            ) AS reentry_rate_within_2y,
            AVG(full_recovery_1y) FILTER (
                WHERE reentry_1y_available = 1
            ) AS full_recovery_rate_1y,
            AVG(full_recovery_within_2y) FILTER (
                WHERE reentry_2y_available = 1
            ) AS full_recovery_rate_within_2y
        FROM recovery_panel
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
        YEAR_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    sector_summary.to_csv(
        SECTOR_FILE,
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

    output_size_gb = (
        OUTPUT_FILE.stat().st_size
        / 1024
        / 1024
        / 1024
    )

    report_lines = [
        "=" * 102,
        "AIID DTA–GPR PROJECT — STEP 14A POST-EXIT RECOVERY PANEL",
        "=" * 102,
        f"Project root: {PROJECT_ROOT}",
        "",
        "A. EVENT DEFINITION",
        "-" * 102,
        (
            "An exit event occurs when a pair-HS2 link traded "
            "positively in t-1 and records zero trade in t."
        ),
        "",
        "B. PANEL AUDIT",
        "-" * 102,
        f"Exit events: {int(row['exit_events']):,}",
        (
            "Events with one-year follow-up: "
            f"{int(row['one_year_available_events']):,}"
        ),
        (
            "Events with two-year follow-up: "
            f"{int(row['two_year_available_events']):,}"
        ),
        (
            "One-year re-entry rate: "
            f"{float(row['reentry_rate_1y']):.6%}"
        ),
        (
            "Re-entry rate within two years: "
            f"{float(row['reentry_rate_within_2y']):.6%}"
        ),
        (
            "Full recovery rate within one year: "
            f"{float(row['full_recovery_rate_1y']):.6%}"
        ),
        (
            "Full recovery rate within two years: "
            f"{float(row['full_recovery_rate_within_2y']):.6%}"
        ),
        (
            "Pair-HS2 groups with at least one exit: "
            f"{int(row['pair_hs2_groups']):,}"
        ),
        (
            "Unordered-pair clusters: "
            f"{int(row['unordered_pair_clusters']):,}"
        ),
        (
            f"Exit years: {int(row['minimum_exit_year'])}–"
            f"{int(row['maximum_exit_year'])}"
        ),
        f"Output Parquet size: {output_size_gb:.3f} GB",
        "",
        "C. OUTCOMES FOR THE NEXT ESTIMATION STEP",
        "-" * 102,
        "reenter_1y",
        "reenter_within_2y",
        "full_recovery_1y",
        "full_recovery_within_2y",
        "log_recovery_gap_1y",
        "",
        "D. OUTPUT FILES",
        "-" * 102,
        "data/processed/estimation_hs2_post_exit_recovery.parquet",
        "outputs/audit/step14a_hs2_recovery_audit.txt",
        "outputs/audit/step14a_hs2_recovery_summary.csv",
        "outputs/audit/step14a_hs2_recovery_by_exit_year.csv",
        "outputs/audit/step14a_hs2_recovery_by_sector.csv",
        "",
        "E. NEXT ACTION",
        "-" * 102,
        (
            "Send the audit report and three summary CSVs "
            "to ChatGPT before estimating recovery models."
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
    print("=" * 102)
    print("STEP 14A — BUILD POST-EXIT RECOVERY PANEL")
    print("=" * 102)
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

    print("Constructing exit and forward-recovery outcomes ...")
    build_dynamic_source(con)

    print("Writing post-exit recovery panel ...")
    write_recovery_panel(con)

    print("Auditing recovery outcomes ...")
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
            "=" * 102,
            "STEP 14A FAILED",
            "=" * 102,
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

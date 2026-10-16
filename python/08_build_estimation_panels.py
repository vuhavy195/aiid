from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys
import traceback

import duckdb
import pandas as pd


# ============================================================
# PROJECT SETTINGS
# ============================================================
PROJECT_ROOT = Path(
    os.environ.get(
        "AIID_PROJECT_ROOT",
        r"H:\AIID_DTA_GPR",
    )
)

START_YEAR = 2007
END_YEAR = 2023
COUNTRY_COUNT = 160

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"
TEMP_DIR = INTERIM_DIR / "duckdb_temp_step8"

INTERIM_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

POSITIVE_HS2_FILE = (
    INTERIM_DIR
    / "trade_positive_pair_hs2_year_intermediate.parquet"
)

POSITIVE_PAIR_FILE = (
    INTERIM_DIR
    / "trade_positive_pair_year_intermediate.parquet"
)

POSITIVE_ENDUSE_FILE = (
    INTERIM_DIR
    / "trade_positive_pair_hs2_enduse_year.parquet"
)

DTA_FILE = (
    PROCESSED_DIR
    / "dta_pair_year_core_160.parquet"
)

GPR_FILE = (
    PROCESSED_DIR
    / "gpr_annual_core_2007_2023.parquet"
)

COUNTRY_SAMPLE_FILE = (
    PROCESSED_DIR
    / "country_sample_160.csv"
)

DATABASE_FILE = (
    INTERIM_DIR
    / "step8_estimation_panels.duckdb"
)

# Large HS2 panel: written as a year-partitioned Parquet dataset.
HS2_PANEL_DIR = (
    PROCESSED_DIR
    / "estimation_pair_hs2_year_intermediate"
)

PAIR_YEAR_OUTPUT = (
    PROCESSED_DIR
    / "estimation_pair_year_intermediate.parquet"
)

DDD_OUTPUT = (
    PROCESSED_DIR
    / "estimation_pair_enduse_year_ddd.parquet"
)

REPORT_FILE = (
    AUDIT_DIR
    / "step8_estimation_panel_audit.txt"
)


# ============================================================
# HELPERS
# ============================================================
def sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def check_required_files() -> None:
    required = [
        POSITIVE_HS2_FILE,
        POSITIVE_PAIR_FILE,
        POSITIVE_ENDUSE_FILE,
        DTA_FILE,
        GPR_FILE,
        COUNTRY_SAMPLE_FILE,
    ]

    missing = [
        path for path in required
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing required file(s):\n"
            + "\n".join(str(path) for path in missing)
        )


def remove_old_outputs() -> None:
    if HS2_PANEL_DIR.exists():
        shutil.rmtree(HS2_PANEL_DIR)

    for path in [
        PAIR_YEAR_OUTPUT,
        DDD_OUTPUT,
    ]:
        if path.exists():
            path.unlink()


def create_source_views(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE VIEW positive_hs2 AS
        SELECT *
        FROM read_parquet(
            '{sql_path(POSITIVE_HS2_FILE)}'
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW positive_pair AS
        SELECT *
        FROM read_parquet(
            '{sql_path(POSITIVE_PAIR_FILE)}'
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW positive_enduse_hs2 AS
        SELECT *
        FROM read_parquet(
            '{sql_path(POSITIVE_ENDUSE_FILE)}'
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW dta_source AS
        SELECT *
        FROM read_parquet(
            '{sql_path(DTA_FILE)}'
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW gpr_source AS
        SELECT *
        FROM read_parquet(
            '{sql_path(GPR_FILE)}'
        )
        """
    )


def validate_sources(
    con: duckdb.DuckDBPyConnection,
) -> dict[str, int | float]:
    expected_pair_year_rows = (
        COUNTRY_COUNT
        * (COUNTRY_COUNT - 1)
        * (END_YEAR - START_YEAR + 1)
    )

    dta_stats = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(
                DISTINCT
                exporter_iso3
                || '|'
                || importer_iso3
                || '|'
                || CAST(year AS VARCHAR)
            ) AS unique_keys,
            COUNT(DISTINCT exporter_iso3)
                AS exporters,
            COUNT(DISTINCT importer_iso3)
                AS importers,
            MIN(year) AS min_year,
            MAX(year) AS max_year
        FROM dta_source
        """
    ).fetchone()

    if dta_stats[0] != expected_pair_year_rows:
        raise ValueError(
            "Unexpected DTA row count. "
            f"Expected {expected_pair_year_rows:,}, "
            f"found {dta_stats[0]:,}."
        )

    if dta_stats[1] != dta_stats[0]:
        raise ValueError(
            "Duplicate exporter–importer–year keys "
            "in the DTA panel."
        )

    if (
        dta_stats[2] != COUNTRY_COUNT
        or dta_stats[3] != COUNTRY_COUNT
        or dta_stats[4] != START_YEAR
        or dta_stats[5] != END_YEAR
    ):
        raise ValueError(
            "The DTA panel has unexpected country or year coverage."
        )

    gpr_stats = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT year) AS unique_years,
            MIN(year) AS min_year,
            MAX(year) AS max_year,
            COUNT(*) FILTER (
                WHERE gpr_mean_z IS NULL
            ) AS missing_main_gpr
        FROM gpr_source
        """
    ).fetchone()

    if gpr_stats != (
        END_YEAR - START_YEAR + 1,
        END_YEAR - START_YEAR + 1,
        START_YEAR,
        END_YEAR,
        0,
    ):
        raise ValueError(
            "The annual GPR panel failed its coverage check. "
            f"Observed values: {gpr_stats}"
        )

    positive_hs2_duplicates = con.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                exporter_iso3,
                importer_iso3,
                hs2,
                year
            FROM positive_hs2
            GROUP BY
                exporter_iso3,
                importer_iso3,
                hs2,
                year
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    if positive_hs2_duplicates:
        raise ValueError(
            "Duplicate positive pair–HS2–year trade keys."
        )

    positive_pair_duplicates = con.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                exporter_iso3,
                importer_iso3,
                year
            FROM positive_pair
            GROUP BY
                exporter_iso3,
                importer_iso3,
                year
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    if positive_pair_duplicates:
        raise ValueError(
            "Duplicate positive pair–year trade keys."
        )

    nonpositive_rows = con.execute(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM positive_hs2
                WHERE trade_value_1000usd <= 0
                   OR trade_value_1000usd IS NULL
            )
            +
            (
                SELECT COUNT(*)
                FROM positive_pair
                WHERE trade_value_1000usd <= 0
                   OR trade_value_1000usd IS NULL
            )
        """
    ).fetchone()[0]

    if nonpositive_rows:
        raise ValueError(
            "Positive-flow inputs contain nonpositive trade values."
        )

    return {
        "expected_pair_year_rows": expected_pair_year_rows,
        "positive_hs2_rows": con.execute(
            "SELECT COUNT(*) FROM positive_hs2"
        ).fetchone()[0],
        "positive_pair_rows": con.execute(
            "SELECT COUNT(*) FROM positive_pair"
        ).fetchone()[0],
        "positive_hs2_trade_value": con.execute(
            """
            SELECT SUM(trade_value_1000usd)
            FROM positive_hs2
            """
        ).fetchone()[0],
        "positive_pair_trade_value": con.execute(
            """
            SELECT SUM(trade_value_1000usd)
            FROM positive_pair
            """
        ).fetchone()[0],
    }


def build_pair_year_core(
    con: duckdb.DuckDBPyConnection,
) -> None:
    # Current global GPR is merged to lagged bilateral DTA depth.
    # GPR's standalone effect will later be absorbed by year-based FE.
    con.execute(
        """
        CREATE OR REPLACE TABLE pair_year_core AS
        SELECT
            d.exporter_code,
            d.importer_code,
            d.exporter_iso3,
            d.importer_iso3,
            d.exporter_name,
            d.importer_name,
            d.year,

            d.fta_active,
            d.depth_data_complete,
            d.active_agreement_count,
            d.coded_agreement_count,
            d.missing_content_agreement_count,
            d.depth_strict,
            d.depth_broad,
            d.depth_coverage,
            d.agreement_age,

            d.fta_active_l1,
            d.depth_data_complete_l1,
            d.active_agreement_count_l1,
            d.depth_strict_l1,
            d.depth_broad_l1,
            d.depth_coverage_l1,

            d.new_fta_entry,
            d.depth_change_strict,
            d.depth_upgrade,
            d.depth_downgrade,

            g.gpr_mean,
            g.gpr_mean_z,
            g.log_gpr_mean_z,
            g.gpr_threat_mean_z,
            g.gpr_act_mean_z,
            g.gpr_max_z,
            g.gpr_change_z,
            g.high_gpr_annual_p75,
            g.high_gpr_annual_p90,
            g.gpr_months_above_p75,
            g.gpr_months_above_p90,

            d.depth_strict_l1 / 10.0
                AS depth_strict_l1_10,
            d.depth_broad_l1 / 10.0
                AS depth_broad_l1_10,
            d.depth_coverage_l1 / 10.0
                AS depth_coverage_l1_10,

            (
                d.depth_data_complete_l1
                AND d.depth_strict_l1 IS NOT NULL
            ) AS baseline_depth_available,

            g.gpr_mean_z
                * (d.depth_strict_l1 / 10.0)
                AS gpr_x_depth_strict_l1_10,

            g.gpr_mean_z
                * d.fta_active_l1
                AS gpr_x_fta_l1,

            g.log_gpr_mean_z
                * (d.depth_strict_l1 / 10.0)
                AS log_gpr_x_depth_strict_l1_10,

            g.gpr_threat_mean_z
                * (d.depth_strict_l1 / 10.0)
                AS threat_gpr_x_depth_strict_l1_10,

            g.gpr_act_mean_z
                * (d.depth_strict_l1 / 10.0)
                AS act_gpr_x_depth_strict_l1_10,

            g.gpr_max_z
                * (d.depth_strict_l1 / 10.0)
                AS max_gpr_x_depth_strict_l1_10,

            g.gpr_change_z
                * (d.depth_strict_l1 / 10.0)
                AS change_gpr_x_depth_strict_l1_10,

            CAST(g.high_gpr_annual_p75 AS DOUBLE)
                * (d.depth_strict_l1 / 10.0)
                AS high75_x_depth_strict_l1_10,

            CAST(g.high_gpr_annual_p90 AS DOUBLE)
                * (d.depth_strict_l1 / 10.0)
                AS high90_x_depth_strict_l1_10,

            d.exporter_iso3
                || '_'
                || d.importer_iso3
                AS directed_pair_id,

            d.exporter_iso3
                || '_'
                || d.importer_iso3
                || '_'
                || CAST(d.year AS VARCHAR)
                AS directed_pair_year_id,

            d.exporter_iso3
                || '_'
                || CAST(d.year AS VARCHAR)
                AS exporter_year_id,

            d.importer_iso3
                || '_'
                || CAST(d.year AS VARCHAR)
                AS importer_year_id

        FROM dta_source d
        INNER JOIN gpr_source g
            USING (year)
        """
    )

    missing_gpr = con.execute(
        """
        SELECT COUNT(*)
        FROM pair_year_core
        WHERE gpr_mean_z IS NULL
        """
    ).fetchone()[0]

    if missing_gpr:
        raise ValueError(
            "GPR failed to merge to at least one pair-year."
        )


def build_pair_year_panel(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute(
        """
        CREATE OR REPLACE TABLE
        estimation_pair_year_intermediate AS
        SELECT
            c.*,
            COALESCE(
                p.trade_value_1000usd,
                0.0
            ) AS trade_value_1000usd,
            COALESCE(
                p.positive_hs2_cells,
                0
            ) AS positive_hs2_cells,
            COALESCE(
                p.positive_hs6_cells,
                0
            ) AS positive_hs6_cells,
            (
                p.trade_value_1000usd IS NOT NULL
            ) AS positive_trade,
            (
                p.trade_value_1000usd IS NULL
            ) AS structural_zero
        FROM pair_year_core c
        LEFT JOIN positive_pair p
            ON c.exporter_iso3 = p.exporter_iso3
           AND c.importer_iso3 = p.importer_iso3
           AND c.year = p.year
        """
    )


def build_hs2_support_panel(
    con: duckdb.DuckDBPyConnection,
) -> None:
    # With pair–HS2 fixed effects, groups that are zero in every
    # year are separated and contribute no identifying information.
    # We therefore keep every pair–HS2 group that is positive in at
    # least one year, then add all within-group zero years.
    con.execute(
        """
        CREATE OR REPLACE TABLE pair_hs2_support AS
        SELECT DISTINCT
            exporter_code,
            importer_code,
            exporter_iso3,
            importer_iso3,
            hs2
        FROM positive_hs2
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE
        estimation_pair_hs2_year_intermediate AS
        SELECT
            c.*,
            s.hs2,

            COALESCE(
                p.trade_value_1000usd,
                0.0
            ) AS trade_value_1000usd,

            COALESCE(
                p.positive_hs6_count,
                0
            ) AS positive_hs6_count,

            COALESCE(
                p.underlying_positive_flow_rows,
                0
            ) AS underlying_positive_flow_rows,

            (
                p.trade_value_1000usd IS NOT NULL
            ) AS positive_trade,

            (
                p.trade_value_1000usd IS NULL
            ) AS structural_zero,

            c.directed_pair_id
                || '_'
                || s.hs2
                AS pair_hs2_id,

            s.hs2
                || '_'
                || CAST(c.year AS VARCHAR)
                AS hs2_year_id

        FROM pair_hs2_support s
        INNER JOIN pair_year_core c
            ON s.exporter_iso3 = c.exporter_iso3
           AND s.importer_iso3 = c.importer_iso3
        LEFT JOIN positive_hs2 p
            ON s.exporter_iso3 = p.exporter_iso3
           AND s.importer_iso3 = p.importer_iso3
           AND s.hs2 = p.hs2
           AND c.year = p.year
        """
    )


def build_ddd_panel(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute(
        """
        CREATE OR REPLACE TABLE positive_pair_enduse AS
        SELECT
            exporter_iso3,
            importer_iso3,
            year,
            end_use,
            SUM(trade_value_1000usd)
                AS trade_value_1000usd,
            COUNT(DISTINCT hs2)
                AS positive_hs2_cells,
            SUM(positive_hs6_count)
                AS summed_positive_hs6_counts,
            SUM(underlying_positive_flow_rows)
                AS underlying_positive_flow_rows
        FROM positive_enduse_hs2
        WHERE end_use IN (
            'intermediate',
            'consumption'
        )
        GROUP BY
            exporter_iso3,
            importer_iso3,
            year,
            end_use
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE
        estimation_pair_enduse_year_ddd AS
        WITH end_uses AS (
            SELECT 'intermediate' AS end_use
            UNION ALL
            SELECT 'consumption' AS end_use
        )
        SELECT
            c.*,
            e.end_use,
            CASE
                WHEN e.end_use = 'intermediate'
                THEN 1
                ELSE 0
            END AS intermediate_good,

            COALESCE(
                p.trade_value_1000usd,
                0.0
            ) AS trade_value_1000usd,

            COALESCE(
                p.positive_hs2_cells,
                0
            ) AS positive_hs2_cells,

            COALESCE(
                p.summed_positive_hs6_counts,
                0
            ) AS summed_positive_hs6_counts,

            COALESCE(
                p.underlying_positive_flow_rows,
                0
            ) AS underlying_positive_flow_rows,

            (
                p.trade_value_1000usd IS NOT NULL
            ) AS positive_trade,

            (
                p.trade_value_1000usd IS NULL
            ) AS structural_zero,

            (
                c.gpr_x_depth_strict_l1_10
                * CASE
                    WHEN e.end_use = 'intermediate'
                    THEN 1
                    ELSE 0
                  END
            ) AS ddd_gpr_depth_intermediate,

            (
                c.gpr_x_fta_l1
                * CASE
                    WHEN e.end_use = 'intermediate'
                    THEN 1
                    ELSE 0
                  END
            ) AS ddd_gpr_fta_intermediate,

            (
                c.depth_strict_l1_10
                * CASE
                    WHEN e.end_use = 'intermediate'
                    THEN 1
                    ELSE 0
                  END
            ) AS depth_intermediate,

            c.directed_pair_id
                || '_'
                || e.end_use
                AS pair_enduse_id,

            e.end_use
                || '_'
                || CAST(c.year AS VARCHAR)
                AS enduse_year_id

        FROM pair_year_core c
        CROSS JOIN end_uses e
        LEFT JOIN positive_pair_enduse p
            ON c.exporter_iso3 = p.exporter_iso3
           AND c.importer_iso3 = p.importer_iso3
           AND c.year = p.year
           AND e.end_use = p.end_use
        """
    )


def validate_built_panels(
    con: duckdb.DuckDBPyConnection,
    source_stats: dict[str, int | float],
) -> dict[str, int | float]:
    expected_pair_year_rows = int(
        source_stats["expected_pair_year_rows"]
    )

    pair_year_rows = con.execute(
        """
        SELECT COUNT(*)
        FROM estimation_pair_year_intermediate
        """
    ).fetchone()[0]

    if pair_year_rows != expected_pair_year_rows:
        raise ValueError(
            "Unexpected pair-year panel row count."
        )

    pair_year_duplicates = con.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                exporter_iso3,
                importer_iso3,
                year
            FROM estimation_pair_year_intermediate
            GROUP BY
                exporter_iso3,
                importer_iso3,
                year
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    if pair_year_duplicates:
        raise ValueError(
            "Duplicate keys in pair-year estimation panel."
        )

    pair_year_trade_sum = con.execute(
        """
        SELECT SUM(trade_value_1000usd)
        FROM estimation_pair_year_intermediate
        """
    ).fetchone()[0]

    if not abs(
        pair_year_trade_sum
        - float(source_stats["positive_pair_trade_value"])
    ) <= max(
        1e-5,
        abs(float(source_stats["positive_pair_trade_value"]))
        * 1e-10,
    ):
        raise ValueError(
            "Pair-year trade values changed during zero filling."
        )

    support_groups = con.execute(
        """
        SELECT COUNT(*)
        FROM pair_hs2_support
        """
    ).fetchone()[0]

    hs2_panel_rows = con.execute(
        """
        SELECT COUNT(*)
        FROM estimation_pair_hs2_year_intermediate
        """
    ).fetchone()[0]

    expected_hs2_rows = (
        support_groups
        * (END_YEAR - START_YEAR + 1)
    )

    if hs2_panel_rows != expected_hs2_rows:
        raise ValueError(
            "Unexpected pair–HS2–year support-panel row count."
        )

    hs2_duplicates = con.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                exporter_iso3,
                importer_iso3,
                hs2,
                year
            FROM estimation_pair_hs2_year_intermediate
            GROUP BY
                exporter_iso3,
                importer_iso3,
                hs2,
                year
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    if hs2_duplicates:
        raise ValueError(
            "Duplicate keys in pair–HS2–year panel."
        )

    all_zero_support_groups = con.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                exporter_iso3,
                importer_iso3,
                hs2,
                SUM(positive_trade::INTEGER)
                    AS positive_years
            FROM estimation_pair_hs2_year_intermediate
            GROUP BY
                exporter_iso3,
                importer_iso3,
                hs2
            HAVING positive_years = 0
        )
        """
    ).fetchone()[0]

    if all_zero_support_groups:
        raise ValueError(
            "An all-zero pair–HS2 fixed-effect group "
            "entered the support panel."
        )

    hs2_trade_sum = con.execute(
        """
        SELECT SUM(trade_value_1000usd)
        FROM estimation_pair_hs2_year_intermediate
        """
    ).fetchone()[0]

    if not abs(
        hs2_trade_sum
        - float(source_stats["positive_hs2_trade_value"])
    ) <= max(
        1e-5,
        abs(float(source_stats["positive_hs2_trade_value"]))
        * 1e-10,
    ):
        raise ValueError(
            "HS2 trade values changed during zero filling."
        )

    ddd_rows = con.execute(
        """
        SELECT COUNT(*)
        FROM estimation_pair_enduse_year_ddd
        """
    ).fetchone()[0]

    if ddd_rows != expected_pair_year_rows * 2:
        raise ValueError(
            "Unexpected DDD panel row count."
        )

    missing_gpr_rows = con.execute(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM estimation_pair_year_intermediate
                WHERE gpr_mean_z IS NULL
            )
            +
            (
                SELECT COUNT(*)
                FROM estimation_pair_hs2_year_intermediate
                WHERE gpr_mean_z IS NULL
            )
            +
            (
                SELECT COUNT(*)
                FROM estimation_pair_enduse_year_ddd
                WHERE gpr_mean_z IS NULL
            )
        """
    ).fetchone()[0]

    if missing_gpr_rows:
        raise ValueError(
            "At least one estimation row has missing GPR."
        )

    return {
        "pair_year_rows": pair_year_rows,
        "pair_year_trade_sum": pair_year_trade_sum,
        "pair_year_zero_rows": con.execute(
            """
            SELECT COUNT(*)
            FROM estimation_pair_year_intermediate
            WHERE structural_zero
            """
        ).fetchone()[0],
        "support_groups": support_groups,
        "hs2_panel_rows": hs2_panel_rows,
        "hs2_zero_rows": con.execute(
            """
            SELECT COUNT(*)
            FROM estimation_pair_hs2_year_intermediate
            WHERE structural_zero
            """
        ).fetchone()[0],
        "hs2_count": con.execute(
            """
            SELECT COUNT(DISTINCT hs2)
            FROM pair_hs2_support
            """
        ).fetchone()[0],
        "ddd_rows": ddd_rows,
        "ddd_zero_rows": con.execute(
            """
            SELECT COUNT(*)
            FROM estimation_pair_enduse_year_ddd
            WHERE structural_zero
            """
        ).fetchone()[0],
        "baseline_missing_pair_years": con.execute(
            """
            SELECT COUNT(*)
            FROM estimation_pair_year_intermediate
            WHERE NOT baseline_depth_available
            """
        ).fetchone()[0],
        "baseline_missing_hs2_rows": con.execute(
            """
            SELECT COUNT(*)
            FROM estimation_pair_hs2_year_intermediate
            WHERE NOT baseline_depth_available
            """
        ).fetchone()[0],
    }


def export_panels(
    con: duckdb.DuckDBPyConnection,
) -> None:
    remove_old_outputs()

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM estimation_pair_hs2_year_intermediate
        )
        TO '{sql_path(HS2_PANEL_DIR)}'
        (
            FORMAT PARQUET,
            PARTITION_BY (year),
            COMPRESSION ZSTD
        )
        """
    )

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM estimation_pair_year_intermediate
        )
        TO '{sql_path(PAIR_YEAR_OUTPUT)}'
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
            FROM estimation_pair_enduse_year_ddd
        )
        TO '{sql_path(DDD_OUTPUT)}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD
        )
        """
    )


def export_audits(
    con: duckdb.DuckDBPyConnection,
    source_stats: dict[str, int | float],
    panel_stats: dict[str, int | float],
) -> None:
    annual_summary = con.execute(
        """
        SELECT
            year,
            COUNT(*) AS pair_year_rows,
            SUM(positive_trade::INTEGER)
                AS positive_pair_year_rows,
            SUM(structural_zero::INTEGER)
                AS zero_pair_year_rows,
            SUM(trade_value_1000usd)
                AS intermediate_trade_value_1000usd,
            SUM(
                baseline_depth_available::INTEGER
            ) AS baseline_depth_available_rows,
            ANY_VALUE(gpr_mean) AS gpr_mean,
            ANY_VALUE(gpr_mean_z) AS gpr_mean_z,
            ANY_VALUE(high_gpr_annual_p75)
                AS high_gpr_annual_p75,
            ANY_VALUE(high_gpr_annual_p90)
                AS high_gpr_annual_p90
        FROM estimation_pair_year_intermediate
        GROUP BY year
        ORDER BY year
        """
    ).fetchdf()

    annual_summary.to_csv(
        AUDIT_DIR
        / "step8_pair_year_annual_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    hs2_summary = con.execute(
        """
        SELECT
            hs2,
            COUNT(DISTINCT directed_pair_id)
                AS supported_directed_pairs,
            COUNT(*) AS panel_rows,
            SUM(positive_trade::INTEGER)
                AS positive_rows,
            SUM(structural_zero::INTEGER)
                AS zero_rows,
            SUM(trade_value_1000usd)
                AS trade_value_1000usd,
            AVG(positive_trade::INTEGER)
                AS positive_row_share
        FROM estimation_pair_hs2_year_intermediate
        GROUP BY hs2
        ORDER BY hs2
        """
    ).fetchdf()

    hs2_summary.to_csv(
        AUDIT_DIR
        / "step8_hs2_support_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    ddd_summary = con.execute(
        """
        SELECT
            end_use,
            COUNT(*) AS panel_rows,
            SUM(positive_trade::INTEGER)
                AS positive_rows,
            SUM(structural_zero::INTEGER)
                AS zero_rows,
            SUM(trade_value_1000usd)
                AS trade_value_1000usd,
            AVG(positive_trade::INTEGER)
                AS positive_row_share
        FROM estimation_pair_enduse_year_ddd
        GROUP BY end_use
        ORDER BY end_use
        """
    ).fetchdf()

    ddd_summary.to_csv(
        AUDIT_DIR
        / "step8_ddd_enduse_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    missing_depth = con.execute(
        """
        SELECT
            exporter_iso3,
            importer_iso3,
            year,
            fta_active_l1,
            depth_data_complete_l1,
            depth_strict_l1,
            missing_content_agreement_count,
            gpr_mean_z
        FROM estimation_pair_year_intermediate
        WHERE NOT baseline_depth_available
        ORDER BY year, exporter_iso3, importer_iso3
        """
    ).fetchdf()

    missing_depth.to_csv(
        AUDIT_DIR
        / "step8_baseline_missing_depth_pair_years.csv",
        index=False,
        encoding="utf-8-sig",
    )

    pair_year_zero_share = (
        panel_stats["pair_year_zero_rows"]
        / panel_stats["pair_year_rows"]
    )

    hs2_zero_share = (
        panel_stats["hs2_zero_rows"]
        / panel_stats["hs2_panel_rows"]
    )

    ddd_zero_share = (
        panel_stats["ddd_zero_rows"]
        / panel_stats["ddd_rows"]
    )

    report_lines = [
        "=" * 94,
        "AIID DTA–GPR PROJECT — STEP 8 ESTIMATION PANELS",
        "=" * 94,
        f"Project root: {PROJECT_ROOT}",
        "",
        "A. INPUT VALIDATION",
        "-" * 94,
        (
            "Positive intermediate pair–HS2–year rows: "
            f"{int(source_stats['positive_hs2_rows']):,}"
        ),
        (
            "Positive intermediate pair–year rows: "
            f"{int(source_stats['positive_pair_rows']):,}"
        ),
        (
            "DTA directed pair–year rows: "
            f"{int(source_stats['expected_pair_year_rows']):,}"
        ),
        (
            f"GPR years merged: "
            f"{END_YEAR - START_YEAR + 1}"
        ),
        "",
        "B. COMPLETE PAIR–YEAR PANEL",
        "-" * 94,
        (
            f"Rows: {int(panel_stats['pair_year_rows']):,}"
        ),
        (
            "Structural-zero rows: "
            f"{int(panel_stats['pair_year_zero_rows']):,} "
            f"({pair_year_zero_share:.6%})"
        ),
        (
            "Rows unavailable for the lagged-depth baseline: "
            f"{int(panel_stats['baseline_missing_pair_years']):,}"
        ),
        "",
        "C. PAIR–HS2–YEAR PPML SUPPORT PANEL",
        "-" * 94,
        (
            "Unique supported pair–HS2 groups: "
            f"{int(panel_stats['support_groups']):,}"
        ),
        (
            "Distinct intermediate HS2 chapters: "
            f"{int(panel_stats['hs2_count']):,}"
        ),
        (
            "Rows after adding all within-support zero years: "
            f"{int(panel_stats['hs2_panel_rows']):,}"
        ),
        (
            "Structural-zero rows: "
            f"{int(panel_stats['hs2_zero_rows']):,} "
            f"({hs2_zero_share:.6%})"
        ),
        (
            "Rows unavailable for the lagged-depth baseline: "
            f"{int(panel_stats['baseline_missing_hs2_rows']):,}"
        ),
        (
            "All pair–HS2 groups are positive in at least "
            "one year: True"
        ),
        "",
        "D. INTERMEDIATE–CONSUMPTION DDD PANEL",
        "-" * 94,
        (
            f"Rows: {int(panel_stats['ddd_rows']):,}"
        ),
        (
            "Structural-zero rows: "
            f"{int(panel_stats['ddd_zero_rows']):,} "
            f"({ddd_zero_share:.6%})"
        ),
        "",
        "E. BASELINE VARIABLES",
        "-" * 94,
        (
            "Main treatment scale: depth_strict_l1_10 "
            "(10 legally enforceable policy areas)"
        ),
        (
            "Main shock: gpr_mean_z "
            "(one historical standard deviation)"
        ),
        (
            "Main interaction: "
            "gpr_x_depth_strict_l1_10"
        ),
        (
            "FTA-existence comparison: gpr_x_fta_l1"
        ),
        (
            "Baseline estimation flag: "
            "baseline_depth_available"
        ),
        "",
        "F. FIXED-EFFECT IDENTIFIERS",
        "-" * 94,
        "directed_pair_id",
        "pair_hs2_id",
        "exporter_year_id",
        "importer_year_id",
        "hs2_year_id",
        "pair_enduse_id",
        "enduse_year_id",
        "",
        "G. OUTPUT FILES",
        "-" * 94,
        (
            "data/processed/"
            "estimation_pair_hs2_year_intermediate/"
            "  [year-partitioned Parquet dataset]"
        ),
        (
            "data/processed/"
            "estimation_pair_year_intermediate.parquet"
        ),
        (
            "data/processed/"
            "estimation_pair_enduse_year_ddd.parquet"
        ),
        "outputs/audit/step8_estimation_panel_audit.txt",
        "outputs/audit/step8_pair_year_annual_summary.csv",
        "outputs/audit/step8_hs2_support_summary.csv",
        "outputs/audit/step8_ddd_enduse_summary.csv",
        (
            "outputs/audit/"
            "step8_baseline_missing_depth_pair_years.csv"
        ),
        "",
        "H. ECONOMETRIC NOTE",
        "-" * 94,
        (
            "The HS2 panel retains every zero year inside a "
            "pair–HS2 group that trades positively at least once."
        ),
        (
            "Pair–HS2 groups that are zero in all 17 years are "
            "omitted because pair–HS2 fixed effects make them "
            "separated and non-informative in PPML."
        ),
        (
            "Do not run the final models until the panel audit "
            "has been reviewed and the R pilot script is prepared."
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
    print("=" * 94)
    print("STEP 8 — MERGE TRADE, DTA AND GPR")
    print("=" * 94)
    print(f"Project root: {PROJECT_ROOT}")

    check_required_files()

    print("Opening DuckDB and validating source files ...")

    con = duckdb.connect(str(DATABASE_FILE))

    con.execute(
        f"SET temp_directory = '{sql_path(TEMP_DIR)}'"
    )
    con.execute("SET preserve_insertion_order = false")

    create_source_views(con)
    source_stats = validate_sources(con)

    print("Constructing the complete pair-year core ...")
    build_pair_year_core(con)

    print("Creating the zero-filled pair-year panel ...")
    build_pair_year_panel(con)

    print(
        "Creating the pair–HS2 support panel with "
        "within-support structural zeros ..."
    )
    build_hs2_support_panel(con)

    print(
        "Creating the intermediate–consumption DDD panel ..."
    )
    build_ddd_panel(con)

    print("Running final panel checks ...")
    panel_stats = validate_built_panels(
        con,
        source_stats,
    )

    print("Writing Parquet outputs ...")
    export_panels(con)

    print("Writing audit outputs ...")
    export_audits(
        con,
        source_stats,
        panel_stats,
    )

    con.execute("CHECKPOINT")
    con.close()


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        failure_lines = [
            "=" * 94,
            "STEP 8 FAILED",
            "=" * 94,
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

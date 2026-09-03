from __future__ import annotations

from pathlib import Path
import os
import sys
import traceback

import duckdb
import pandas as pd


# ============================================================
# AIID DTA–GPR PROJECT
# STEP 15B — BUILD COUNTRY-SPECIFIC PAIR-GPR PANELS
#
# The source contains 44 country-specific GPR series.
#
# For pairs in which both partners have country GPR data:
#   pair_gpr_average = (GPR_exporter + GPR_importer) / 2
#   pair_gpr_maximum = max(GPR_exporter, GPR_importer)
#
# Both pair shocks are re-standardized over the complete set of
# covered unordered pair-years in 2007–2023.
#
# This step builds and audits the trade-value and link-survival
# robustness panels. It does not estimate regressions.
# ============================================================


PROJECT_ROOT = Path(
    os.environ.get(
        "AIID_PROJECT_ROOT",
        r"H:\AIID_DTA_GPR",
    )
)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit"
TEMP_DIR = INTERIM_DIR / "duckdb_temp_step15b"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
INTERIM_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

COUNTRY_SAMPLE_FILE = (
    PROCESSED_DIR
    / "country_sample_160.csv"
)

COUNTRY_GPR_FILE = (
    INTERIM_DIR
    / "gpr_country_annual_1985_2023.parquet"
)

GLOBAL_GPR_FILE = (
    PROCESSED_DIR
    / "gpr_annual_core_2007_2023.parquet"
)

TRADE_FILE = (
    PROCESSED_DIR
    / "estimation_hs2_ppml_compact.parquet"
)

SURVIVAL_FILE = (
    PROCESSED_DIR
    / "estimation_hs2_trade_link_survival.parquet"
)

PAIR_SHOCK_FILE = (
    INTERIM_DIR
    / "country_specific_pair_gpr_2007_2023.parquet"
)

TRADE_OUTPUT_FILE = (
    PROCESSED_DIR
    / "estimation_hs2_ppml_country_gpr.parquet"
)

SURVIVAL_OUTPUT_FILE = (
    PROCESSED_DIR
    / "estimation_hs2_survival_country_gpr.parquet"
)

DATABASE_FILE = (
    INTERIM_DIR
    / "step15b_country_gpr.duckdb"
)

REPORT_FILE = (
    AUDIT_DIR
    / "step15b_country_gpr_panel_audit.txt"
)

COUNTRY_COVERAGE_FILE = (
    AUDIT_DIR
    / "step15b_country_gpr_sample_coverage.csv"
)

SHOCK_SUMMARY_FILE = (
    AUDIT_DIR
    / "step15b_country_gpr_pair_shock_summary.csv"
)

PANEL_SUMMARY_FILE = (
    AUDIT_DIR
    / "step15b_country_gpr_panel_summary.csv"
)

EXPECTED_TRADE_ROWS = 16_752_461
EXPECTED_SURVIVAL_ROWS = 8_219_579
EXPECTED_COUNTRY_GPR_SERIES = 44
EXPECTED_YEARS = 17


def sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def validate_inputs() -> None:
    required = [
        COUNTRY_SAMPLE_FILE,
        COUNTRY_GPR_FILE,
        GLOBAL_GPR_FILE,
        TRADE_FILE,
        SURVIVAL_FILE,
    ]

    missing = [
        path
        for path in required
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing required file(s):\n"
            + "\n".join(str(path) for path in missing)
        )


def create_source_views(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE TABLE country_sample AS
        SELECT
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

    con.execute(
        f"""
        CREATE OR REPLACE VIEW country_gpr AS
        SELECT
            TRIM(iso3) AS iso3,
            CAST(year AS INTEGER) AS year,
            CAST(gpr_country_mean_z AS DOUBLE)
                AS gpr_country_mean_z,
            CAST(log_gpr_country_mean_z AS DOUBLE)
                AS log_gpr_country_mean_z
        FROM read_parquet(
            '{sql_path(COUNTRY_GPR_FILE)}'
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW global_gpr AS
        SELECT
            CAST(year AS INTEGER) AS year,
            CAST(gpr_mean_z AS DOUBLE)
                AS global_gpr_mean_z
        FROM read_parquet(
            '{sql_path(GLOBAL_GPR_FILE)}'
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW trade_source AS
        SELECT *
        FROM read_parquet(
            '{sql_path(TRADE_FILE)}'
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW survival_source AS
        SELECT *
        FROM read_parquet(
            '{sql_path(SURVIVAL_FILE)}'
        )
        """
    )


def validate_sources(
    con: duckdb.DuckDBPyConnection,
) -> None:
    country_sample_stats = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT final_sample_rank)
                AS ranks,
            COUNT(DISTINCT analysis_iso3)
                AS iso3_codes,
            MIN(final_sample_rank)
                AS min_rank,
            MAX(final_sample_rank)
                AS max_rank
        FROM country_sample
        """
    ).fetchone()

    if country_sample_stats != (
        160,
        160,
        160,
        1,
        160,
    ):
        raise ValueError(
            "Country sample failed its audit. "
            f"Observed: {country_sample_stats}"
        )

    country_gpr_stats = con.execute(
        """
        SELECT
            COUNT(DISTINCT iso3) AS countries,
            COUNT(*) AS rows,
            MIN(year) AS min_year,
            MAX(year) AS max_year,
            COUNT(*) FILTER (
                WHERE gpr_country_mean_z IS NULL
                   OR log_gpr_country_mean_z IS NULL
            ) AS missing_rows
        FROM country_gpr
        """
    ).fetchone()

    if country_gpr_stats[0] != EXPECTED_COUNTRY_GPR_SERIES:
        raise ValueError(
            "Unexpected number of country-specific GPR series: "
            f"{country_gpr_stats[0]}"
        )

    if country_gpr_stats[2:] != (
        1985,
        2023,
        0,
    ):
        raise ValueError(
            "Country GPR file failed year/missing audit. "
            f"Observed: {country_gpr_stats}"
        )

    trade_rows = con.execute(
        "SELECT COUNT(*) FROM trade_source"
    ).fetchone()[0]

    survival_rows = con.execute(
        "SELECT COUNT(*) FROM survival_source"
    ).fetchone()[0]

    if trade_rows != EXPECTED_TRADE_ROWS:
        raise ValueError(
            f"Unexpected compact trade rows: {trade_rows:,}"
        )

    if survival_rows != EXPECTED_SURVIVAL_ROWS:
        raise ValueError(
            f"Unexpected survival rows: {survival_rows:,}"
        )


def build_country_overlap(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    con.execute(
        """
        CREATE OR REPLACE TABLE covered_countries AS
        SELECT
            s.final_sample_rank,
            s.analysis_iso3
        FROM country_sample s
        INNER JOIN (
            SELECT DISTINCT iso3
            FROM country_gpr
        ) g
            ON s.analysis_iso3 = g.iso3
        ORDER BY s.final_sample_rank
        """
    )

    coverage = con.execute(
        """
        SELECT
            s.final_sample_rank,
            s.analysis_iso3,
            CASE
                WHEN c.analysis_iso3 IS NOT NULL
                THEN 1
                ELSE 0
            END AS has_country_gpr
        FROM country_sample s
        LEFT JOIN covered_countries c
            USING (
                final_sample_rank,
                analysis_iso3
            )
        ORDER BY s.final_sample_rank
        """
    ).fetchdf()

    covered_count = int(
        coverage["has_country_gpr"].sum()
    )

    if covered_count < 30:
        raise ValueError(
            "Too few final-sample economies overlap the "
            f"country-specific GPR data: {covered_count}"
        )

    coverage.to_csv(
        COUNTRY_COVERAGE_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    return coverage


def build_pair_shocks(
    con: duckdb.DuckDBPyConnection,
) -> None:
    # Build every unordered pair among the covered economies,
    # independently of trade-support selection.
    con.execute(
        """
        CREATE OR REPLACE TABLE pair_country_gpr_raw AS
        SELECT
            a.final_sample_rank AS rank_low,
            b.final_sample_rank AS rank_high,

            CAST(
                (a.final_sample_rank - 1) * 160
                + (b.final_sample_rank - 1)
                AS INTEGER
            ) AS unordered_pair_cluster_id,

            ga.year,

            CAST(
                0.5 * (
                    ga.gpr_country_mean_z
                    + gb.gpr_country_mean_z
                )
                AS DOUBLE
            ) AS pair_gpr_average_raw,

            CAST(
                GREATEST(
                    ga.gpr_country_mean_z,
                    gb.gpr_country_mean_z
                )
                AS DOUBLE
            ) AS pair_gpr_maximum_raw,

            CAST(
                0.5 * (
                    ga.log_gpr_country_mean_z
                    + gb.log_gpr_country_mean_z
                )
                AS DOUBLE
            ) AS pair_log_gpr_average_raw

        FROM covered_countries a

        INNER JOIN covered_countries b
            ON a.final_sample_rank
               < b.final_sample_rank

        INNER JOIN country_gpr ga
            ON ga.iso3 = a.analysis_iso3
           AND ga.year BETWEEN 2007 AND 2023

        INNER JOIN country_gpr gb
            ON gb.iso3 = b.analysis_iso3
           AND gb.year = ga.year
        """
    )

    raw_stats = con.execute(
        """
        SELECT
            AVG(pair_gpr_average_raw)
                AS avg_mean,
            STDDEV_SAMP(pair_gpr_average_raw)
                AS avg_sd,
            AVG(pair_gpr_maximum_raw)
                AS max_mean,
            STDDEV_SAMP(pair_gpr_maximum_raw)
                AS max_sd,
            AVG(pair_log_gpr_average_raw)
                AS log_avg_mean,
            STDDEV_SAMP(pair_log_gpr_average_raw)
                AS log_avg_sd
        FROM pair_country_gpr_raw
        """
    ).fetchone()

    if any(
        value is None
        for value in raw_stats
    ):
        raise ValueError(
            "Invalid pair-GPR standardization statistics."
        )

    (
        avg_mean,
        avg_sd,
        max_mean,
        max_sd,
        log_avg_mean,
        log_avg_sd,
    ) = raw_stats

    if min(avg_sd, max_sd, log_avg_sd) <= 0:
        raise ValueError(
            "At least one pair-GPR standard deviation "
            "is non-positive."
        )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE pair_country_gpr AS
        SELECT
            r.unordered_pair_cluster_id,
            r.rank_low,
            r.rank_high,
            r.year,

            CAST(
                (
                    r.pair_gpr_average_raw
                    - {avg_mean}
                ) / {avg_sd}
                AS DOUBLE
            ) AS pair_country_gpr_average_z,

            CAST(
                (
                    r.pair_gpr_maximum_raw
                    - {max_mean}
                ) / {max_sd}
                AS DOUBLE
            ) AS pair_country_gpr_maximum_z,

            CAST(
                (
                    r.pair_log_gpr_average_raw
                    - {log_avg_mean}
                ) / {log_avg_sd}
                AS DOUBLE
            ) AS pair_country_log_gpr_average_z,

            r.pair_gpr_average_raw,
            r.pair_gpr_maximum_raw,
            r.pair_log_gpr_average_raw,

            g.global_gpr_mean_z

        FROM pair_country_gpr_raw r

        INNER JOIN global_gpr g
            USING (year)
        """
    )

    pair_stats = con.execute(
        """
        SELECT
            COUNT(*) AS pair_year_rows,
            COUNT(DISTINCT unordered_pair_cluster_id)
                AS unordered_pairs,
            COUNT(DISTINCT year) AS years,
            MIN(year) AS minimum_year,
            MAX(year) AS maximum_year,
            AVG(pair_country_gpr_average_z)
                AS average_z_mean,
            STDDEV_SAMP(pair_country_gpr_average_z)
                AS average_z_sd,
            AVG(pair_country_gpr_maximum_z)
                AS maximum_z_mean,
            STDDEV_SAMP(pair_country_gpr_maximum_z)
                AS maximum_z_sd,
            CORR(
                pair_country_gpr_average_z,
                pair_country_gpr_maximum_z
            ) AS corr_average_maximum,
            CORR(
                pair_country_gpr_average_z,
                global_gpr_mean_z
            ) AS corr_average_global,
            CORR(
                pair_country_gpr_maximum_z,
                global_gpr_mean_z
            ) AS corr_maximum_global
        FROM pair_country_gpr
        """
    ).fetchdf()

    row = pair_stats.iloc[0]

    if int(row["years"]) != EXPECTED_YEARS:
        raise ValueError(
            "Pair-country GPR does not cover 17 years."
        )

    if (
        int(row["minimum_year"]) != 2007
        or int(row["maximum_year"]) != 2023
    ):
        raise ValueError(
            "Pair-country GPR must cover 2007–2023."
        )

    pair_stats.to_csv(
        SHOCK_SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    if PAIR_SHOCK_FILE.exists():
        PAIR_SHOCK_FILE.unlink()

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM pair_country_gpr
        )
        TO '{sql_path(PAIR_SHOCK_FILE)}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD
        )
        """
    )


def write_trade_panel(
    con: duckdb.DuckDBPyConnection,
) -> None:
    if TRADE_OUTPUT_FILE.exists():
        TRADE_OUTPUT_FILE.unlink()

    con.execute(
        f"""
        COPY (
            SELECT
                t.*,

                p.pair_country_gpr_average_z,
                p.pair_country_gpr_maximum_z,
                p.pair_country_log_gpr_average_z,

                CAST(
                    p.pair_country_gpr_average_z
                    * t.fta_active_l1
                    AS DOUBLE
                ) AS pair_avg_gpr_x_fta_l1,

                CAST(
                    p.pair_country_gpr_average_z
                    * t.depth_strict_l1_10
                    AS DOUBLE
                ) AS pair_avg_gpr_x_depth_l1_10,

                CAST(
                    p.pair_country_gpr_maximum_z
                    * t.fta_active_l1
                    AS DOUBLE
                ) AS pair_max_gpr_x_fta_l1,

                CAST(
                    p.pair_country_gpr_maximum_z
                    * t.depth_strict_l1_10
                    AS DOUBLE
                ) AS pair_max_gpr_x_depth_l1_10,

                CAST(
                    p.pair_country_log_gpr_average_z
                    * t.fta_active_l1
                    AS DOUBLE
                ) AS pair_log_avg_gpr_x_fta_l1,

                CAST(
                    p.pair_country_log_gpr_average_z
                    * t.depth_strict_l1_10
                    AS DOUBLE
                ) AS pair_log_avg_gpr_x_depth_l1_10

            FROM trade_source t

            INNER JOIN pair_country_gpr p
                USING (
                    unordered_pair_cluster_id,
                    year
                )
        )
        TO '{sql_path(TRADE_OUTPUT_FILE)}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD,
            ROW_GROUP_SIZE 250000
        )
        """
    )


def write_survival_panel(
    con: duckdb.DuckDBPyConnection,
) -> None:
    if SURVIVAL_OUTPUT_FILE.exists():
        SURVIVAL_OUTPUT_FILE.unlink()

    con.execute(
        f"""
        COPY (
            SELECT
                s.*,

                p.pair_country_gpr_average_z,
                p.pair_country_gpr_maximum_z,
                p.pair_country_log_gpr_average_z,

                CAST(
                    p.pair_country_gpr_average_z
                    * s.fta_active_l1
                    AS DOUBLE
                ) AS pair_avg_gpr_x_fta_l1,

                CAST(
                    p.pair_country_gpr_average_z
                    * s.depth_strict_l1_10
                    AS DOUBLE
                ) AS pair_avg_gpr_x_depth_l1_10,

                CAST(
                    p.pair_country_gpr_maximum_z
                    * s.fta_active_l1
                    AS DOUBLE
                ) AS pair_max_gpr_x_fta_l1,

                CAST(
                    p.pair_country_gpr_maximum_z
                    * s.depth_strict_l1_10
                    AS DOUBLE
                ) AS pair_max_gpr_x_depth_l1_10,

                CAST(
                    p.pair_country_log_gpr_average_z
                    * s.fta_active_l1
                    AS DOUBLE
                ) AS pair_log_avg_gpr_x_fta_l1,

                CAST(
                    p.pair_country_log_gpr_average_z
                    * s.depth_strict_l1_10
                    AS DOUBLE
                ) AS pair_log_avg_gpr_x_depth_l1_10

            FROM survival_source s

            INNER JOIN pair_country_gpr p
                USING (
                    unordered_pair_cluster_id,
                    year
                )
        )
        TO '{sql_path(SURVIVAL_OUTPUT_FILE)}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD,
            ROW_GROUP_SIZE 250000
        )
        """
    )


def audit_outputs(
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    con.execute(
        f"""
        CREATE OR REPLACE VIEW trade_country_gpr AS
        SELECT *
        FROM read_parquet(
            '{sql_path(TRADE_OUTPUT_FILE)}'
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW survival_country_gpr AS
        SELECT *
        FROM read_parquet(
            '{sql_path(SURVIVAL_OUTPUT_FILE)}'
        )
        """
    )

    summary = con.execute(
        f"""
        SELECT
            'trade_value' AS panel,
            COUNT(*) AS rows,
            COUNT(DISTINCT pair_hs2_fe_id)
                AS pair_hs2_groups,
            COUNT(DISTINCT unordered_pair_cluster_id)
                AS unordered_pair_clusters,
            COUNT(DISTINCT year) AS years,
            MIN(year) AS minimum_year,
            MAX(year) AS maximum_year,
            AVG(
                CAST(
                    trade_value_musd = 0
                    AS INTEGER
                )
            ) AS zero_share,
            NULL::DOUBLE AS survival_rate,
            COUNT(*) FILTER (
                WHERE pair_country_gpr_average_z IS NULL
                   OR pair_country_gpr_maximum_z IS NULL
                   OR pair_avg_gpr_x_depth_l1_10 IS NULL
                   OR pair_max_gpr_x_depth_l1_10 IS NULL
            ) AS missing_shock_rows,
            {EXPECTED_TRADE_ROWS} AS full_panel_rows,
            COUNT(*) / {EXPECTED_TRADE_ROWS}.0
                AS retained_row_share
        FROM trade_country_gpr

        UNION ALL

        SELECT
            'link_survival' AS panel,
            COUNT(*) AS rows,
            COUNT(DISTINCT pair_hs2_fe_id)
                AS pair_hs2_groups,
            COUNT(DISTINCT unordered_pair_cluster_id)
                AS unordered_pair_clusters,
            COUNT(DISTINCT year) AS years,
            MIN(year) AS minimum_year,
            MAX(year) AS maximum_year,
            NULL::DOUBLE AS zero_share,
            AVG(survive_t) AS survival_rate,
            COUNT(*) FILTER (
                WHERE pair_country_gpr_average_z IS NULL
                   OR pair_country_gpr_maximum_z IS NULL
                   OR pair_avg_gpr_x_depth_l1_10 IS NULL
                   OR pair_max_gpr_x_depth_l1_10 IS NULL
            ) AS missing_shock_rows,
            {EXPECTED_SURVIVAL_ROWS} AS full_panel_rows,
            COUNT(*) / {EXPECTED_SURVIVAL_ROWS}.0
                AS retained_row_share
        FROM survival_country_gpr
        """
    ).fetchdf()

    if (
        summary["rows"].le(0).any()
        or summary["missing_shock_rows"].ne(0).any()
    ):
        raise ValueError(
            "Country-GPR output panel audit failed."
        )

    summary.to_csv(
        PANEL_SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    return summary


def write_report(
    coverage: pd.DataFrame,
    panel_summary: pd.DataFrame,
) -> None:
    covered_count = int(
        coverage["has_country_gpr"].sum()
    )

    pair_shock_summary = pd.read_csv(
        SHOCK_SUMMARY_FILE
    ).iloc[0]

    trade_row = panel_summary.loc[
        panel_summary["panel"] == "trade_value"
    ].iloc[0]

    survival_row = panel_summary.loc[
        panel_summary["panel"] == "link_survival"
    ].iloc[0]

    report_lines = [
        "=" * 108,
        "AIID DTA–GPR PROJECT — STEP 15B COUNTRY-SPECIFIC PAIR-GPR PANELS",
        "=" * 108,
        f"Project root: {PROJECT_ROOT}",
        "",
        "A. COUNTRY COVERAGE",
        "-" * 108,
        (
            "Country-specific GPR series in source: "
            f"{EXPECTED_COUNTRY_GPR_SERIES}"
        ),
        (
            "Series overlapping the final 160-economy sample: "
            f"{covered_count}"
        ),
        (
            "Potential unordered pairs among covered economies: "
            f"{int(pair_shock_summary['unordered_pairs']):,}"
        ),
        "",
        "B. PAIR-SHOCK CONSTRUCTION",
        "-" * 108,
        (
            "Average shock: mean of exporter and importer "
            "country-specific GPR z-scores."
        ),
        (
            "Maximum shock: larger of exporter and importer "
            "country-specific GPR z-scores."
        ),
        (
            "Both shocks are re-standardized over all covered "
            "unordered pair-years in 2007–2023."
        ),
        (
            "Correlation, average vs maximum pair GPR: "
            f"{float(pair_shock_summary['corr_average_maximum']):.6f}"
        ),
        (
            "Correlation, average pair GPR vs global GPR: "
            f"{float(pair_shock_summary['corr_average_global']):.6f}"
        ),
        (
            "Correlation, maximum pair GPR vs global GPR: "
            f"{float(pair_shock_summary['corr_maximum_global']):.6f}"
        ),
        "",
        "C. TRADE-VALUE ROBUSTNESS PANEL",
        "-" * 108,
        f"Rows: {int(trade_row['rows']):,}",
        (
            "Unordered-pair clusters: "
            f"{int(trade_row['unordered_pair_clusters']):,}"
        ),
        (
            "Retained share of the global-GPR panel: "
            f"{float(trade_row['retained_row_share']):.6%}"
        ),
        "",
        "D. LINK-SURVIVAL ROBUSTNESS PANEL",
        "-" * 108,
        f"Rows: {int(survival_row['rows']):,}",
        (
            "Unordered-pair clusters: "
            f"{int(survival_row['unordered_pair_clusters']):,}"
        ),
        (
            "Retained share of the global-GPR panel: "
            f"{float(survival_row['retained_row_share']):.6%}"
        ),
        (
            "Survival rate in covered-country panel: "
            f"{float(survival_row['survival_rate']):.6%}"
        ),
        "",
        "E. INTERPRETATION LIMIT",
        "-" * 108,
        (
            "This is a restricted-sample robustness check, not "
            "a replacement for the global-GPR baseline. It covers "
            "only pairs for which both countries have a national "
            "GPR series."
        ),
        "",
        "F. OUTPUT FILES",
        "-" * 108,
        "data/interim/country_specific_pair_gpr_2007_2023.parquet",
        "data/processed/estimation_hs2_ppml_country_gpr.parquet",
        "data/processed/estimation_hs2_survival_country_gpr.parquet",
        "outputs/audit/step15b_country_gpr_panel_audit.txt",
        "outputs/audit/step15b_country_gpr_sample_coverage.csv",
        "outputs/audit/step15b_country_gpr_pair_shock_summary.csv",
        "outputs/audit/step15b_country_gpr_panel_summary.csv",
        "",
        "G. NEXT ACTION",
        "-" * 108,
        (
            "Send the report and three audit CSVs to ChatGPT "
            "before estimating country-specific GPR regressions."
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
    print("=" * 108)
    print("STEP 15B — BUILD COUNTRY-SPECIFIC PAIR-GPR PANELS")
    print("=" * 108)
    print(f"Project root: {PROJECT_ROOT}")

    validate_inputs()

    con = duckdb.connect(str(DATABASE_FILE))

    con.execute(
        f"SET temp_directory = '{sql_path(TEMP_DIR)}'"
    )
    con.execute(
        "SET preserve_insertion_order = false"
    )

    print("Opening country, GPR, trade and survival files ...")
    create_source_views(con)

    print("Validating source coverage ...")
    validate_sources(con)

    print("Matching the 44 country-GPR series to the final sample ...")
    coverage = build_country_overlap(con)

    print("Constructing standardized pair-specific GPR shocks ...")
    build_pair_shocks(con)

    print("Writing trade-value country-GPR panel ...")
    write_trade_panel(con)

    print("Writing link-survival country-GPR panel ...")
    write_survival_panel(con)

    print("Auditing country-GPR output panels ...")
    panel_summary = audit_outputs(con)

    con.execute("CHECKPOINT")
    con.close()

    write_report(
        coverage,
        panel_summary,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        failure_lines = [
            "=" * 108,
            "STEP 15B FAILED",
            "=" * 108,
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

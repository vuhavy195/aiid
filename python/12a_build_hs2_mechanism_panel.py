from __future__ import annotations

from pathlib import Path
import os
import sys
import traceback

import duckdb
import pandas as pd


# ============================================================
# AIID DTA–GPR PROJECT
# STEP 12A — BUILD HS2 MECHANISM PANEL
#
# This step adds lagged DTA provision bundles to the compact
# 16.75-million-row HS2 PPML panel.
#
# It does not estimate any regression.
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
TEMP_DIR = INTERIM_DIR / "duckdb_temp_step12a"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
INTERIM_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

COMPACT_HS2_FILE = (
    PROCESSED_DIR
    / "estimation_hs2_ppml_compact.parquet"
)

DTA_CORE_FILE = (
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

OUTPUT_FILE = (
    PROCESSED_DIR
    / "estimation_hs2_ppml_mechanisms.parquet"
)

DATABASE_FILE = (
    INTERIM_DIR
    / "step12a_hs2_mechanisms.duckdb"
)

REPORT_FILE = (
    AUDIT_DIR
    / "step12a_hs2_mechanism_audit.txt"
)

SUMMARY_FILE = (
    AUDIT_DIR
    / "step12a_mechanism_summary.csv"
)

CORRELATION_FILE = (
    AUDIT_DIR
    / "step12a_mechanism_correlations.csv"
)

EXPECTED_ROWS = 16_752_461
EXPECTED_CLUSTERS = 12_454
EXPECTED_YEARS = 17


SELECTED_PROVISIONS = [
    "Customs",
    "SPS",
    "TBT",
    "PublicProcurement",
    "TRIMs",
    "GATS",
    "TRIPs",
    "CompetitionPolicy",
    "EnvironmentalLaws",
    "IPR",
    "Investment",
    "DataProtection",
    "InformationSociety",
    "ResearchandTechnology",
    "InnovationPolicies",
    "MovementofCapital",
]


BUNDLES = {
    "border_coordination": [
        "Customs",
        "SPS",
        "TBT",
    ],
    "investment_production": [
        "Investment",
        "TRIMs",
        "CompetitionPolicy",
        "MovementofCapital",
    ],
    "digital_knowledge": [
        "DataProtection",
        "InformationSociety",
        "ResearchandTechnology",
        "InnovationPolicies",
        "IPR",
        "TRIPs",
    ],
    "services_procurement": [
        "GATS",
        "PublicProcurement",
    ],
    "environmental": [
        "EnvironmentalLaws",
    ],
}


def sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def validate_inputs() -> None:
    required = [
        COMPACT_HS2_FILE,
        DTA_CORE_FILE,
        GPR_FILE,
        COUNTRY_SAMPLE_FILE,
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
        CREATE OR REPLACE VIEW hs2_compact AS
        SELECT *
        FROM read_parquet(
            '{sql_path(COMPACT_HS2_FILE)}'
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW dta_core AS
        SELECT *
        FROM read_parquet(
            '{sql_path(DTA_CORE_FILE)}'
        )
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW gpr_source AS
        SELECT
            CAST(year AS INTEGER) AS year,
            CAST(gpr_mean_z AS DOUBLE) AS gpr_mean_z
        FROM read_parquet(
            '{sql_path(GPR_FILE)}'
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


def validate_source_schema(
    con: duckdb.DuckDBPyConnection,
) -> None:
    dta_columns = {
        row[0]
        for row in con.execute(
            "DESCRIBE dta_core"
        ).fetchall()
    }

    required_dta_columns = {
        "exporter_code",
        "importer_code",
        "year",
        "depth_data_complete_l1",
    } | {
        f"strict_{name}_l1"
        for name in SELECTED_PROVISIONS
    }

    missing = required_dta_columns - dta_columns

    if missing:
        raise ValueError(
            "DTA core is missing required mechanism columns: "
            f"{sorted(missing)}"
        )

    compact_stats = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT unordered_pair_cluster_id)
                AS clusters,
            COUNT(DISTINCT year)
                AS years
        FROM hs2_compact
        """
    ).fetchone()

    if compact_stats != (
        EXPECTED_ROWS,
        EXPECTED_CLUSTERS,
        EXPECTED_YEARS,
    ):
        raise ValueError(
            "Compact HS2 source failed its audit. "
            f"Observed: {compact_stats}"
        )


def build_unordered_mechanism_panel(
    con: duckdb.DuckDBPyConnection,
) -> None:
    provision_select = ",\n".join(
        [
            f"""
            CAST(d.strict_{name}_l1 AS TINYINT)
                AS strict_{name}_l1
            """.strip()
            for name in SELECTED_PROVISIONS
        ]
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE
        directed_mechanism_pair_year AS
        SELECT
            CAST(d.year AS SMALLINT) AS year,

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
            ) AS unordered_pair_cluster_id,

            CAST(
                d.depth_data_complete_l1
                AS BOOLEAN
            ) AS depth_data_complete_l1,

            {provision_select}

        FROM dta_core d

        INNER JOIN country_rank er
            ON d.exporter_code = er.country_code

        INNER JOIN country_rank ir
            ON d.importer_code = ir.country_code
        """
    )

    # Every unordered pair-year appears twice in directed data.
    # Mechanism variables must be identical in both directions.
    symmetry_checks = []

    for name in SELECTED_PROVISIONS:
        symmetry_checks.append(
            f"""
            MIN(strict_{name}_l1)
            <> MAX(strict_{name}_l1)
            """.strip()
        )

    symmetry_condition = "\nOR ".join(symmetry_checks)

    asymmetric_rows = con.execute(
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT
                unordered_pair_cluster_id,
                year
            FROM directed_mechanism_pair_year
            GROUP BY
                unordered_pair_cluster_id,
                year
            HAVING
                COUNT(*) <> 2
                OR MIN(depth_data_complete_l1)
                   <> MAX(depth_data_complete_l1)
                OR {symmetry_condition}
        )
        """
    ).fetchone()[0]

    if asymmetric_rows:
        raise ValueError(
            "Mechanism symmetry failed for "
            f"{asymmetric_rows:,} unordered pair-years."
        )

    provision_max_select = ",\n".join(
        [
            f"""
            CAST(
                MAX(strict_{name}_l1)
                AS TINYINT
            ) AS strict_{name}_l1
            """.strip()
            for name in SELECTED_PROVISIONS
        ]
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE
        mechanism_pair_year AS
        SELECT
            unordered_pair_cluster_id,
            year,
            CAST(
                MAX(depth_data_complete_l1)
                AS BOOLEAN
            ) AS depth_data_complete_l1,
            {provision_max_select}
        FROM directed_mechanism_pair_year
        GROUP BY
            unordered_pair_cluster_id,
            year
        """
    )


def add_bundle_variables(
    con: duckdb.DuckDBPyConnection,
) -> None:
    bundle_expressions = []

    for bundle_name, provisions in BUNDLES.items():
        count_expression = " + ".join(
            [
                f"strict_{name}_l1"
                for name in provisions
            ]
        )

        bundle_size = len(provisions)

        bundle_expressions.extend(
            [
                f"""
                CAST(
                    {count_expression}
                    AS TINYINT
                ) AS {bundle_name}_count_l1
                """.strip(),
                f"""
                CAST(
                    ({count_expression}) / {bundle_size}.0
                    AS DOUBLE
                ) AS {bundle_name}_share_l1
                """.strip(),
            ]
        )

    bundle_select = ",\n".join(bundle_expressions)

    con.execute(
        f"""
        CREATE OR REPLACE TABLE
        mechanism_pair_year_bundles AS
        SELECT
            m.*,
            g.gpr_mean_z,
            {bundle_select}
        FROM mechanism_pair_year m
        INNER JOIN gpr_source g
            USING (year)
        """
    )


def write_output(
    con: duckdb.DuckDBPyConnection,
) -> None:
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    individual_columns = ",\n".join(
        [
            f"""
            CAST(
                m.strict_{name}_l1
                AS TINYINT
            ) AS strict_{name}_l1,

            CAST(
                m.gpr_mean_z
                * m.strict_{name}_l1
                AS DOUBLE
            ) AS gpr_x_strict_{name}_l1
            """.strip()
            for name in SELECTED_PROVISIONS
        ]
    )

    bundle_columns = []

    for bundle_name in BUNDLES:
        bundle_columns.extend(
            [
                f"""
                CAST(
                    m.{bundle_name}_count_l1
                    AS TINYINT
                ) AS {bundle_name}_count_l1
                """.strip(),
                f"""
                CAST(
                    m.{bundle_name}_share_l1
                    AS DOUBLE
                ) AS {bundle_name}_share_l1
                """.strip(),
                f"""
                CAST(
                    m.gpr_mean_z
                    * m.{bundle_name}_share_l1
                    AS DOUBLE
                ) AS gpr_x_{bundle_name}_share_l1
                """.strip(),
            ]
        )

    bundle_select = ",\n".join(bundle_columns)

    con.execute(
        f"""
        COPY (
            SELECT
                h.*,
                CAST(
                    m.gpr_mean_z
                    AS DOUBLE
                ) AS gpr_mean_z,

                {individual_columns},

                {bundle_select}

            FROM hs2_compact h

            INNER JOIN mechanism_pair_year_bundles m
                ON h.unordered_pair_cluster_id
                   = m.unordered_pair_cluster_id
               AND h.year = m.year

            WHERE m.depth_data_complete_l1
        )
        TO '{sql_path(OUTPUT_FILE)}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD,
            ROW_GROUP_SIZE 250000
        )
        """
    )


def audit_output(
    con: duckdb.DuckDBPyConnection,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    con.execute(
        f"""
        CREATE OR REPLACE VIEW mechanism_output AS
        SELECT *
        FROM read_parquet(
            '{sql_path(OUTPUT_FILE)}'
        )
        """
    )

    missing_checks = [
        "gpr_mean_z IS NULL",
    ]

    for name in SELECTED_PROVISIONS:
        missing_checks.extend(
            [
                f"strict_{name}_l1 IS NULL",
                f"gpr_x_strict_{name}_l1 IS NULL",
            ]
        )

    for bundle_name in BUNDLES:
        missing_checks.extend(
            [
                f"{bundle_name}_count_l1 IS NULL",
                f"{bundle_name}_share_l1 IS NULL",
                f"gpr_x_{bundle_name}_share_l1 IS NULL",
            ]
        )

    missing_condition = "\nOR ".join(
        missing_checks
    )

    basic_stats = con.execute(
        f"""
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT unordered_pair_cluster_id)
                AS clusters,
            COUNT(DISTINCT year)
                AS years,
            COUNT(*) FILTER (
                WHERE {missing_condition}
            ) AS rows_with_missing_mechanisms
        FROM mechanism_output
        """
    ).fetchdf()

    row = basic_stats.iloc[0]

    if int(row["rows"]) != EXPECTED_ROWS:
        raise ValueError(
            f"Expected {EXPECTED_ROWS:,} output rows, "
            f"found {int(row['rows']):,}."
        )

    if int(row["clusters"]) != EXPECTED_CLUSTERS:
        raise ValueError(
            "Unexpected mechanism-output cluster count."
        )

    if int(row["years"]) != EXPECTED_YEARS:
        raise ValueError(
            "Unexpected mechanism-output year coverage."
        )

    if int(row["rows_with_missing_mechanisms"]) != 0:
        raise ValueError(
            "Missing mechanism values detected."
        )

    summary_rows = []

    for name in SELECTED_PROVISIONS:
        stats = con.execute(
            f"""
            SELECT
                AVG(
                    strict_{name}_l1
                ) AS prevalence_all_rows,
                AVG(
                    strict_{name}_l1
                ) FILTER (
                    WHERE fta_active_l1 = 1
                ) AS prevalence_fta_rows,
                COUNT(DISTINCT
                    unordered_pair_cluster_id
                ) FILTER (
                    WHERE strict_{name}_l1 = 1
                ) AS clusters_with_provision
            FROM mechanism_output
            """
        ).fetchone()

        summary_rows.append(
            {
                "variable_type": "individual_provision",
                "mechanism": name,
                "number_of_components": 1,
                "prevalence_all_rows": stats[0],
                "prevalence_fta_rows": stats[1],
                "clusters_with_positive_value": stats[2],
            }
        )

    for bundle_name, provisions in BUNDLES.items():
        stats = con.execute(
            f"""
            SELECT
                AVG(
                    {bundle_name}_share_l1
                ) AS mean_share_all_rows,
                AVG(
                    {bundle_name}_share_l1
                ) FILTER (
                    WHERE fta_active_l1 = 1
                ) AS mean_share_fta_rows,
                COUNT(DISTINCT
                    unordered_pair_cluster_id
                ) FILTER (
                    WHERE {bundle_name}_count_l1 > 0
                ) AS clusters_with_bundle
            FROM mechanism_output
            """
        ).fetchone()

        summary_rows.append(
            {
                "variable_type": "bundle",
                "mechanism": bundle_name,
                "number_of_components": len(provisions),
                "prevalence_all_rows": stats[0],
                "prevalence_fta_rows": stats[1],
                "clusters_with_positive_value": stats[2],
            }
        )

    summary = pd.DataFrame(summary_rows)

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    bundle_names = list(BUNDLES.keys())

    bundle_select = ", ".join(
        [
            f"{name}_share_l1"
            for name in bundle_names
        ]
        + [
            "depth_strict_l1_10",
            "fta_active_l1",
        ]
    )

    correlation_data = con.execute(
        f"""
        SELECT
            {bundle_select}
        FROM mechanism_output
        GROUP BY
            unordered_pair_cluster_id,
            year,
            {bundle_select}
        """
    ).fetchdf()

    correlations = correlation_data.corr(
        numeric_only=True
    )

    correlations.to_csv(
        CORRELATION_FILE,
        encoding="utf-8-sig",
    )

    return basic_stats, summary


def write_report(
    basic_stats: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
    row = basic_stats.iloc[0]

    file_size_gb = (
        OUTPUT_FILE.stat().st_size
        / 1024
        / 1024
        / 1024
    )

    report_lines = [
        "=" * 100,
        "AIID DTA–GPR PROJECT — STEP 12A HS2 MECHANISM PANEL",
        "=" * 100,
        f"Project root: {PROJECT_ROOT}",
        "",
        "A. OUTPUT PANEL",
        "-" * 100,
        f"Rows: {int(row['rows']):,}",
        (
            "Unordered-pair clusters: "
            f"{int(row['clusters']):,}"
        ),
        f"Years: {int(row['years']):,}",
        (
            "Rows with missing mechanism values: "
            f"{int(row['rows_with_missing_mechanisms']):,}"
        ),
        (
            f"Output Parquet size: {file_size_gb:.3f} GB"
        ),
        "",
        "B. PRE-SPECIFIED MECHANISM BUNDLES",
        "-" * 100,
        (
            "border_coordination: "
            "Customs, SPS, TBT"
        ),
        (
            "investment_production: "
            "Investment, TRIMs, CompetitionPolicy, "
            "MovementofCapital"
        ),
        (
            "digital_knowledge: "
            "DataProtection, InformationSociety, "
            "ResearchandTechnology, InnovationPolicies, "
            "IPR, TRIPs"
        ),
        (
            "services_procurement: "
            "GATS, PublicProcurement"
        ),
        (
            "environmental: EnvironmentalLaws"
        ),
        "",
        "C. INTERPRETATION",
        "-" * 100,
        (
            "Each bundle_share_l1 ranges from 0 to 1 and equals "
            "the share of the pre-specified provisions that are "
            "legally enforceable in the previous year."
        ),
        (
            "Each gpr_x_<bundle>_share_l1 interaction combines "
            "a one-standard-deviation global GPR increase with "
            "a movement from none to all provisions in that bundle."
        ),
        (
            "Individual provision indicators and interactions "
            "are also retained for later FDR-controlled tests."
        ),
        "",
        "D. OUTPUT FILES",
        "-" * 100,
        "data/processed/estimation_hs2_ppml_mechanisms.parquet",
        "outputs/audit/step12a_hs2_mechanism_audit.txt",
        "outputs/audit/step12a_mechanism_summary.csv",
        "outputs/audit/step12a_mechanism_correlations.csv",
        "",
        "E. NEXT ACTION",
        "-" * 100,
        (
            "Send the report, summary and correlation CSVs "
            "to ChatGPT before estimating mechanism models."
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
    print("STEP 12A — BUILD HS2 MECHANISM PANEL")
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

    print("Opening compact HS2, DTA and GPR files ...")
    create_source_views(con)

    print("Validating mechanism columns and source coverage ...")
    validate_source_schema(con)

    print("Collapsing symmetric DTA mechanisms to unordered pair-years ...")
    build_unordered_mechanism_panel(con)

    print("Constructing five pre-specified mechanism bundles ...")
    add_bundle_variables(con)

    print("Joining mechanisms to the full compact HS2 panel ...")
    write_output(con)

    print("Auditing the mechanism output ...")
    basic_stats, summary = audit_output(con)

    con.execute("CHECKPOINT")
    con.close()

    write_report(
        basic_stats,
        summary,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        failure_lines = [
            "=" * 100,
            "STEP 12A FAILED",
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

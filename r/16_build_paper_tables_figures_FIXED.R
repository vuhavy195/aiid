
# ============================================================
# AIID DTA-GPR PAPER
# BUILD FINAL PAPER TABLES AND FIGURES
#
# This script does NOT re-estimate the empirical models.
# It reads the final processed panels and the coefficient CSVs
# already produced in Steps 10B-15C, then creates publication-
# ready tables, figures, an Excel workbook, and a manifest.
# ============================================================

rm(list = ls(all.names = TRUE))
invisible(gc(full = TRUE))

# ------------------------------------------------------------
# 1. PROJECT PATHS
# ------------------------------------------------------------
PROJECT_ROOT <- "H:/AIID_DTA_GPR"

INPUT_TABLE_DIR <- file.path(
  PROJECT_ROOT, "outputs", "tables"
)
INPUT_AUDIT_DIR <- file.path(
  PROJECT_ROOT, "outputs", "audit"
)
PROCESSED_DIR <- file.path(
  PROJECT_ROOT, "data", "processed"
)

PAPER_OUT <- file.path(
  PROJECT_ROOT, "outputs", "paper_outputs"
)
MAIN_TABLE_DIR <- file.path(
  PAPER_OUT, "main_tables"
)
APP_TABLE_DIR <- file.path(
  PAPER_OUT, "appendix_tables"
)
FIGURE_DIR <- file.path(
  PAPER_OUT, "figures"
)
FIGURE_DATA_DIR <- file.path(
  PAPER_OUT, "figure_data"
)

for (directory in c(
  PAPER_OUT,
  MAIN_TABLE_DIR,
  APP_TABLE_DIR,
  FIGURE_DIR,
  FIGURE_DATA_DIR
)) {
  dir.create(
    directory,
    recursive = TRUE,
    showWarnings = FALSE
  )
}

# ------------------------------------------------------------
# 2. PACKAGES
# ------------------------------------------------------------
required_packages <- c(
  "data.table",
  "ggplot2",
  "openxlsx",
  "DBI",
  "duckdb",
  "scales"
)

missing_packages <- setdiff(
  required_packages,
  rownames(installed.packages())
)

if (length(missing_packages) > 0L) {
  install.packages(
    missing_packages,
    repos = "https://cloud.r-project.org",
    dependencies = TRUE
  )
}

suppressPackageStartupMessages({
  library(data.table)
  library(ggplot2)
  library(openxlsx)
  library(DBI)
  library(duckdb)
  library(scales)
})

# ------------------------------------------------------------
# 3. HELPERS
# ------------------------------------------------------------
first_existing <- function(paths) {
  hit <- paths[file.exists(paths)]
  if (length(hit) == 0L) {
    return(NA_character_)
  }
  normalizePath(
    hit[1L],
    winslash = "/",
    mustWork = TRUE
  )
}

require_path <- function(path, label = "Required input") {
  if (
    length(path) != 1L ||
    is.na(path) ||
    !file.exists(path)
  ) {
    stop(
      paste0(
        label,
        " not found:\n",
        path
      ),
      call. = FALSE
    )
  }
  invisible(path)
}

sql_path <- function(path) {
  escaped <- normalizePath(
    path,
    winslash = "/",
    mustWork = TRUE
  )
  gsub(
    "'",
    "''",
    escaped,
    fixed = TRUE
  )
}

read_output_csv <- function(path) {
  require_path(path)
  output <- fread(
    path,
    encoding = "UTF-8"
  )
  if ("index" %in% names(output)) {
    output[, index := NULL]
  }
  output
}

pick_column <- function(
  data,
  candidates,
  required = TRUE
) {
  hit <- candidates[
    candidates %in% names(data)
  ]
  if (length(hit) > 0L) {
    return(hit[1L])
  }
  if (required) {
    stop(
      paste0(
        "None of these columns were found: ",
        paste(candidates, collapse = ", "),
        "\nAvailable columns: ",
        paste(names(data), collapse = ", ")
      ),
      call. = FALSE
    )
  }
  NA_character_
}

stars_from_p <- function(p_value) {
  fifelse(
    is.na(p_value),
    "",
    fifelse(
      p_value < 0.01,
      "***",
      fifelse(
        p_value < 0.05,
        "**",
        fifelse(
          p_value < 0.10,
          "*",
          ""
        )
      )
    )
  )
}

format_number <- function(
  value,
  digits = 4L
) {
  ifelse(
    is.na(value),
    "",
    formatC(
      value,
      digits = digits,
      format = "f"
    )
  )
}

format_integer <- function(value) {
  ifelse(
    is.na(value),
    "",
    format(
      round(value),
      big.mark = ",",
      scientific = FALSE,
      trim = TRUE
    )
  )
}

coefficient_cell <- function(
  estimate,
  std_error,
  p_value,
  effect = NULL,
  effect_suffix = NULL,
  estimate_digits = 4L,
  effect_digits = 2L
) {
  star <- stars_from_p(p_value)
  line_1 <- paste0(
    format_number(
      estimate,
      estimate_digits
    ),
    star
  )
  line_2 <- paste0(
    "(",
    format_number(
      std_error,
      estimate_digits
    ),
    ")"
  )

  if (
    is.null(effect) ||
    is.na(effect)
  ) {
    return(
      paste(
        line_1,
        line_2,
        sep = "\n"
      )
    )
  }

  line_3 <- paste0(
    "[",
    ifelse(
      effect > 0,
      "+",
      ""
    ),
    format_number(
      effect,
      effect_digits
    ),
    effect_suffix,
    "]"
  )

  paste(
    line_1,
    line_2,
    line_3,
    sep = "\n"
  )
}

save_table_csv <- function(
  data,
  filename,
  appendix = FALSE
) {
  folder <- if (appendix) {
    APP_TABLE_DIR
  } else {
    MAIN_TABLE_DIR
  }
  output_path <- file.path(
    folder,
    filename
  )
  fwrite(
    as.data.table(data),
    output_path,
    bom = TRUE
  )
  output_path
}

save_plot_both <- function(
  plot_object,
  filename_stem,
  width,
  height
) {
  png_file <- file.path(
    FIGURE_DIR,
    paste0(filename_stem, ".png")
  )
  pdf_file <- file.path(
    FIGURE_DIR,
    paste0(filename_stem, ".pdf")
  )

  ggsave(
    png_file,
    plot = plot_object,
    width = width,
    height = height,
    units = "in",
    dpi = 600,
    bg = "white"
  )

  ggsave(
    pdf_file,
    plot = plot_object,
    width = width,
    height = height,
    units = "in",
    bg = "white"
  )

  c(png_file, pdf_file)
}

theme_paper <- function(base_size = 11) {
  theme_minimal(base_size = base_size) +
    theme(
      plot.title = element_text(
        face = "bold",
        hjust = 0
      ),
      plot.subtitle = element_text(
        hjust = 0
      ),
      panel.grid.minor = element_blank(),
      panel.grid.major.y = element_blank(),
      legend.position = "bottom",
      strip.text = element_text(
        face = "bold"
      ),
      axis.title = element_text(
        face = "plain"
      )
    )
}

# ------------------------------------------------------------
# 4. INPUT FILES
# ------------------------------------------------------------
trade_panel_file <- first_existing(
  c(
    file.path(
      PROCESSED_DIR,
      "estimation_hs2_ppml_mechanisms.parquet"
    ),
    file.path(
      PROCESSED_DIR,
      "estimation_hs2_ppml_compact.parquet"
    )
  )
)

survival_panel_file <- first_existing(
  c(
    file.path(
      PROCESSED_DIR,
      "estimation_hs2_trade_link_survival.parquet"
    )
  )
)

recovery_panel_file <- first_existing(
  c(
    file.path(
      PROCESSED_DIR,
      "estimation_hs2_post_exit_recovery.parquet"
    )
  )
)

gpr_annual_file <- first_existing(
  c(
    file.path(
      PROCESSED_DIR,
      "gpr_annual_core_2007_2023.csv"
    )
  )
)

input_files <- list(
  step10b = file.path(
    INPUT_TABLE_DIR,
    "step10b_hs2_core_coefficients.csv"
  ),
  step10c = file.path(
    INPUT_TABLE_DIR,
    "step10c_hs2_robustness_coefficients.csv"
  ),
  step11 = file.path(
    INPUT_TABLE_DIR,
    "step11_hs2_sector_coefficients.csv"
  ),
  step12b = file.path(
    INPUT_TABLE_DIR,
    "step12b_mechanism_bundle_coefficients.csv"
  ),
  step12c = file.path(
    INPUT_TABLE_DIR,
    "step12c_individual_provision_coefficients.csv"
  ),
  step13b = file.path(
    INPUT_TABLE_DIR,
    "step13b_hs2_survival_interactions.csv"
  ),
  step13c = file.path(
    INPUT_TABLE_DIR,
    "step13c_survival_robustness_coefficients.csv"
  ),
  step13c_loo = file.path(
    INPUT_TABLE_DIR,
    "step13c_survival_leave_one_year_out.csv"
  ),
  step14b = file.path(
    INPUT_TABLE_DIR,
    "step14b_recovery_interactions.csv"
  ),
  step14b_net = file.path(
    INPUT_TABLE_DIR,
    "step14b_recovery_net_effects.csv"
  ),
  step15a = file.path(
    INPUT_TABLE_DIR,
    "step15a_fta_only_depth_coefficients.csv"
  ),
  step15c = file.path(
    INPUT_TABLE_DIR,
    "step15c_country_gpr_coefficients.csv"
  ),
  survival_by_year = file.path(
    INPUT_AUDIT_DIR,
    "step13a_hs2_survival_by_year.csv"
  ),
  recovery_by_year = file.path(
    INPUT_AUDIT_DIR,
    "step14a_hs2_recovery_by_exit_year.csv"
  )
)

for (path in c(
  trade_panel_file,
  survival_panel_file,
  recovery_panel_file,
  gpr_annual_file,
  unlist(input_files[
    c(
      "step10b",
      "step10c",
      "step11",
      "step12b",
      "step12c",
      "step13b",
      "step13c",
      "step13c_loo",
      "step14b",
      "step14b_net",
      "step15a",
      "step15c"
    )
  ])
)) {
  require_path(path)
}

# ------------------------------------------------------------
# 5. TABLE 1: VARIABLE DEFINITIONS
# ------------------------------------------------------------
table_1 <- data.table(
  Variable = c(
    "TradeValue",
    "FTA",
    "DTAdepth",
    "GlobalGPR",
    "GPRThreat",
    "GPRAct",
    "GPRPeak",
    "PairGPRAvg",
    "PairGPRMax",
    "Survival",
    "Reentry1Y",
    "Reentry2Y",
    "FullRecovery1Y",
    "FullRecovery2Y",
    "LaggedTrade"
  ),
  Definition = c(
    paste(
      "Bilateral intermediate-goods exports from economy i",
      "to economy j, aggregated to HS2 and measured in",
      "millions of current U.S. dollars."
    ),
    paste(
      "Indicator equal to one when at least one preferential",
      "trade agreement was in force for the bilateral pair",
      "in the preceding year."
    ),
    paste(
      "Number of legally enforceable policy areas in active",
      "agreements, divided by ten; overlapping agreements are",
      "combined using the provision-level maximum."
    ),
    paste(
      "Annual mean of the global Geopolitical Risk Index,",
      "standardized using the 1985-2019 historical mean and",
      "standard deviation."
    ),
    paste(
      "Standardized annual mean of the geopolitical-threat",
      "component."
    ),
    paste(
      "Standardized annual mean of the geopolitical-acts",
      "component."
    ),
    paste(
      "Standardized maximum monthly global GPR observation",
      "within each year."
    ),
    paste(
      "Average of standardized exporter- and importer-specific",
      "GPR indices for each bilateral pair-year."
    ),
    paste(
      "Maximum of standardized exporter- and importer-specific",
      "GPR indices for each bilateral pair-year."
    ),
    paste(
      "Indicator equal to one when a pair-HS2 relationship",
      "with positive trade in t-1 remains positive in t."
    ),
    paste(
      "Indicator equal to one when an exited trade link",
      "records positive trade again in t+1."
    ),
    paste(
      "Indicator equal to one when an exited trade link",
      "records positive trade in t+1 or t+2."
    ),
    paste(
      "Indicator equal to one when trade in t+1 returns to",
      "at least the pre-exit value in t-1."
    ),
    paste(
      "Indicator equal to one when trade in t+1 or t+2 returns",
      "to at least the pre-exit value in t-1."
    ),
    paste(
      "Natural logarithm of one plus intermediate-goods trade",
      "value in the preceding year."
    )
  ),
  Source = c(
    "CEPII BACI HS2007; UNSD HS2007-BEC Rev. 4 correspondence",
    "WTO RTA Database; World Bank Deep Trade Agreements Database",
    "World Bank Deep Trade Agreements Horizontal Content Database",
    "Caldara and Iacoviello (2022)",
    "Caldara and Iacoviello (2022)",
    "Caldara and Iacoviello (2022)",
    "Authors' calculation from Caldara and Iacoviello (2022)",
    "Authors' calculation from country-specific GPR series",
    "Authors' calculation from country-specific GPR series",
    "Authors' calculation from CEPII BACI",
    "Authors' calculation from CEPII BACI",
    "Authors' calculation from CEPII BACI",
    "Authors' calculation from CEPII BACI",
    "Authors' calculation from CEPII BACI",
    "Authors' calculation from CEPII BACI"
  )
)

save_table_csv(
  table_1,
  "table1_variable_definitions.csv"
)

# ------------------------------------------------------------
# 6. TABLE 2: DESCRIPTIVE STATISTICS
# ------------------------------------------------------------
con <- dbConnect(
  duckdb::duckdb(),
  dbdir = ":memory:"
)

trade_sql <- sql_path(
  trade_panel_file
)
survival_sql <- sql_path(
  survival_panel_file
)
recovery_sql <- sql_path(
  recovery_panel_file
)

descriptive_query <- sprintf(
"
WITH descriptive AS (

  SELECT
    1 AS sort_order,
    'Intermediate-goods trade value (USD million)' AS variable,
    COUNT(trade_value_musd) AS n,
    AVG(trade_value_musd) AS mean,
    STDDEV_SAMP(trade_value_musd) AS sd,
    MIN(trade_value_musd) AS min,
    QUANTILE_CONT(trade_value_musd, 0.25) AS p25,
    QUANTILE_CONT(trade_value_musd, 0.50) AS median,
    QUANTILE_CONT(trade_value_musd, 0.75) AS p75,
    MAX(trade_value_musd) AS max
  FROM read_parquet('%s')

  UNION ALL

  SELECT
    2,
    'FTA membership, t-1',
    COUNT(fta_active_l1),
    AVG(fta_active_l1),
    STDDEV_SAMP(fta_active_l1),
    MIN(fta_active_l1),
    QUANTILE_CONT(fta_active_l1, 0.25),
    QUANTILE_CONT(fta_active_l1, 0.50),
    QUANTILE_CONT(fta_active_l1, 0.75),
    MAX(fta_active_l1)
  FROM read_parquet('%s')

  UNION ALL

  SELECT
    3,
    'Legally enforceable DTA depth, t-1',
    COUNT(depth_strict_l1_10),
    AVG(depth_strict_l1_10),
    STDDEV_SAMP(depth_strict_l1_10),
    MIN(depth_strict_l1_10),
    QUANTILE_CONT(depth_strict_l1_10, 0.25),
    QUANTILE_CONT(depth_strict_l1_10, 0.50),
    QUANTILE_CONT(depth_strict_l1_10, 0.75),
    MAX(depth_strict_l1_10)
  FROM read_parquet('%s')

  UNION ALL

  SELECT
    4,
    'Global GPR, standardized',
    COUNT(gpr_mean_z),
    AVG(gpr_mean_z),
    STDDEV_SAMP(gpr_mean_z),
    MIN(gpr_mean_z),
    QUANTILE_CONT(gpr_mean_z, 0.25),
    QUANTILE_CONT(gpr_mean_z, 0.50),
    QUANTILE_CONT(gpr_mean_z, 0.75),
    MAX(gpr_mean_z)
  FROM read_parquet('%s')

  UNION ALL

  SELECT
    5,
    'Lagged link size, ln(1 + Trade t-1)',
    COUNT(log1p_trade_value_l1_musd),
    AVG(log1p_trade_value_l1_musd),
    STDDEV_SAMP(log1p_trade_value_l1_musd),
    MIN(log1p_trade_value_l1_musd),
    QUANTILE_CONT(log1p_trade_value_l1_musd, 0.25),
    QUANTILE_CONT(log1p_trade_value_l1_musd, 0.50),
    QUANTILE_CONT(log1p_trade_value_l1_musd, 0.75),
    MAX(log1p_trade_value_l1_musd)
  FROM read_parquet('%s')

  UNION ALL

  SELECT
    6,
    'Trade-link survival',
    COUNT(survive_t),
    AVG(survive_t),
    STDDEV_SAMP(survive_t),
    MIN(survive_t),
    QUANTILE_CONT(survive_t, 0.25),
    QUANTILE_CONT(survive_t, 0.50),
    QUANTILE_CONT(survive_t, 0.75),
    MAX(survive_t)
  FROM read_parquet('%s')

  UNION ALL

  SELECT
    7,
    'Post-exit re-entry within one year',
    COUNT(reenter_1y),
    AVG(reenter_1y),
    STDDEV_SAMP(reenter_1y),
    MIN(reenter_1y),
    QUANTILE_CONT(reenter_1y, 0.25),
    QUANTILE_CONT(reenter_1y, 0.50),
    QUANTILE_CONT(reenter_1y, 0.75),
    MAX(reenter_1y)
  FROM read_parquet('%s')
  WHERE reentry_1y_available = 1

  UNION ALL

  SELECT
    8,
    'Post-exit re-entry within two years',
    COUNT(reenter_within_2y),
    AVG(reenter_within_2y),
    STDDEV_SAMP(reenter_within_2y),
    MIN(reenter_within_2y),
    QUANTILE_CONT(reenter_within_2y, 0.25),
    QUANTILE_CONT(reenter_within_2y, 0.50),
    QUANTILE_CONT(reenter_within_2y, 0.75),
    MAX(reenter_within_2y)
  FROM read_parquet('%s')
  WHERE reentry_2y_available = 1

  UNION ALL

  SELECT
    9,
    'Full recovery within one year',
    COUNT(full_recovery_1y),
    AVG(full_recovery_1y),
    STDDEV_SAMP(full_recovery_1y),
    MIN(full_recovery_1y),
    QUANTILE_CONT(full_recovery_1y, 0.25),
    QUANTILE_CONT(full_recovery_1y, 0.50),
    QUANTILE_CONT(full_recovery_1y, 0.75),
    MAX(full_recovery_1y)
  FROM read_parquet('%s')
  WHERE reentry_1y_available = 1

  UNION ALL

  SELECT
    10,
    'Full recovery within two years',
    COUNT(full_recovery_within_2y),
    AVG(full_recovery_within_2y),
    STDDEV_SAMP(full_recovery_within_2y),
    MIN(full_recovery_within_2y),
    QUANTILE_CONT(full_recovery_within_2y, 0.25),
    QUANTILE_CONT(full_recovery_within_2y, 0.50),
    QUANTILE_CONT(full_recovery_within_2y, 0.75),
    MAX(full_recovery_within_2y)
  FROM read_parquet('%s')
  WHERE reentry_2y_available = 1
)
SELECT *
FROM descriptive
ORDER BY sort_order
",
  trade_sql,
  trade_sql,
  trade_sql,
  trade_sql,
  survival_sql,
  survival_sql,
  recovery_sql,
  recovery_sql,
  recovery_sql,
  recovery_sql
)

table_2 <- as.data.table(
  dbGetQuery(
    con,
    descriptive_query
  )
)

table_2[, sort_order := NULL]

for (column in c(
  "mean",
  "sd",
  "min",
  "p25",
  "median",
  "p75",
  "max"
)) {
  set(
    table_2,
    j = column,
    value = round(
      table_2[[column]],
      3
    )
  )
}

setnames(
  table_2,
  c(
    "variable",
    "n",
    "mean",
    "sd",
    "min",
    "p25",
    "median",
    "p75",
    "max"
  ),
  c(
    "Variable",
    "N",
    "Mean",
    "SD",
    "Min",
    "p25",
    "Median",
    "p75",
    "Max"
  )
)

save_table_csv(
  table_2,
  "table2_descriptive_statistics.csv"
)

# Annual pair-level agreement coverage for Figure 2
annual_agreement_query <- sprintf(
"
WITH pair_year AS (
  SELECT
    year,
    unordered_pair_cluster_id,
    MAX(fta_active_l1) AS fta_active_l1,
    MAX(depth_strict_l1_10) AS depth_strict_l1_10
  FROM read_parquet('%s')
  GROUP BY
    year,
    unordered_pair_cluster_id
)
SELECT
  year,
  100.0 * AVG(fta_active_l1) AS fta_coverage_percent,
  AVG(
    CASE
      WHEN fta_active_l1 = 1
      THEN 10.0 * depth_strict_l1_10
      ELSE NULL
    END
  ) AS mean_depth_provisions
FROM pair_year
GROUP BY year
ORDER BY year
",
  trade_sql
)

annual_agreement <- as.data.table(
  dbGetQuery(
    con,
    annual_agreement_query
  )
)

dbDisconnect(
  con,
  shutdown = TRUE
)

annual_gpr <- fread(
  gpr_annual_file,
  encoding = "UTF-8"
)

figure_2_data <- merge(
  annual_gpr[
    ,
    .(
      year,
      gpr_mean_z
    )
  ],
  annual_agreement,
  by = "year",
  all = TRUE
)

fwrite(
  figure_2_data,
  file.path(
    FIGURE_DATA_DIR,
    "figure2_gpr_agreement_coverage_data.csv"
  ),
  bom = TRUE
)

# ------------------------------------------------------------
# 7. TABLE 3: BASELINE PPML
# ------------------------------------------------------------
step10b <- read_output_csv(
  input_files$step10b
)
step10c <- read_output_csv(
  input_files$step10c
)

table_3_tidy <- rbindlist(
  list(
    step10b[
      model == "hs2_fta" &
        inference == "pair_plus_year_cluster" &
        term == "gpr_x_fta_l1",
      .(
        Specification = "(1) FTA interaction",
        Term = "GPR x FTA",
        estimate,
        std_error,
        p_value,
        effect = percent_effect,
        nobs
      )
    ],
    step10b[
      model == "hs2_depth" &
        inference == "pair_plus_year_cluster" &
        term == "gpr_x_depth_strict_l1_10",
      .(
        Specification = "(2) Depth interaction",
        Term = "GPR x DTA depth",
        estimate,
        std_error,
        p_value,
        effect = percent_effect,
        nobs
      )
    ],
    step10c[
      model == "joint_fta_depth" &
        inference == "pair_plus_year_cluster" &
        term == "gpr_x_fta_l1",
      .(
        Specification = "(3) Joint FTA + depth",
        Term = "GPR x FTA",
        estimate,
        std_error,
        p_value,
        effect = percent_effect,
        nobs
      )
    ],
    step10c[
      model == "joint_fta_depth" &
        inference == "pair_plus_year_cluster" &
        term == "gpr_x_depth_strict_l1_10",
      .(
        Specification = "(3) Joint FTA + depth",
        Term = "GPR x DTA depth",
        estimate,
        std_error,
        p_value,
        effect = percent_effect,
        nobs
      )
    ]
  ),
  fill = TRUE
)

table_3_tidy[
  ,
  Cell := mapply(
    coefficient_cell,
    estimate,
    std_error,
    p_value,
    effect,
    MoreArgs = list(
      effect_suffix = "%"
    )
  )
]

table_3 <- dcast(
  table_3_tidy,
  Term ~ Specification,
  value.var = "Cell",
  fill = "—"
)

setnames(
  table_3,
  "Term",
  "Variable"
)

table_3 <- rbindlist(
  list(
    table_3,
    data.table(
      Variable = c(
        "FTA level term",
        "DTA-depth level term",
        "Pair-HS2 fixed effects",
        "Exporter-year fixed effects",
        "Importer-year fixed effects",
        "HS2-year fixed effects",
        "Observations"
      ),
      `(1) FTA interaction` = c(
        "Included",
        "—",
        "Yes",
        "Yes",
        "Yes",
        "Yes",
        format_integer(
          table_3_tidy[
            Specification ==
              "(1) FTA interaction",
            unique(nobs)
          ]
        )
      ),
      `(2) Depth interaction` = c(
        "—",
        "Included",
        "Yes",
        "Yes",
        "Yes",
        "Yes",
        format_integer(
          table_3_tidy[
            Specification ==
              "(2) Depth interaction",
            unique(nobs)
          ]
        )
      ),
      `(3) Joint FTA + depth` = c(
        "Included",
        "Included",
        "Yes",
        "Yes",
        "Yes",
        "Yes",
        format_integer(
          table_3_tidy[
            Specification ==
              "(3) Joint FTA + depth",
            unique(nobs)
          ]
        )
      )
    )
  ),
  fill = TRUE
)

save_table_csv(
  table_3,
  "table3_baseline_ppml.csv"
)

save_table_csv(
  table_3_tidy,
  "table3_baseline_ppml_tidy.csv"
)

# ------------------------------------------------------------
# 8. TABLE 4 AND FIGURE 3: SECTOR HETEROGENEITY
# ------------------------------------------------------------
sector_raw <- read_output_csv(
  input_files$step11
)

sector_name_col <- pick_column(
  sector_raw,
  c(
    "sector_name",
    "sector"
  )
)
fdr_col <- pick_column(
  sector_raw,
  c(
    "p_value_fdr_bh",
    "fdr_p_value"
  )
)

sector <- copy(
  sector_raw[
    inference == "pair_plus_year_cluster"
  ]
)

setnames(
  sector,
  sector_name_col,
  "Sector"
)
setnames(
  sector,
  fdr_col,
  "FDR_p"
)

if (!"percent_effect" %in% names(sector)) {
  sector[
    ,
    percent_effect :=
      100 * (
        exp(estimate) - 1
      )
  ]
}

if (
  !"percent_effect_ci_low" %in%
    names(sector)
) {
  sector[
    ,
    percent_effect_ci_low :=
      100 * (
        exp(
          estimate -
            1.96 * std_error
        ) - 1
      )
  ]
}

if (
  !"percent_effect_ci_high" %in%
    names(sector)
) {
  sector[
    ,
    percent_effect_ci_high :=
      100 * (
        exp(
          estimate +
            1.96 * std_error
        ) - 1
      )
  ]
}

sector[
  ,
  Term_Label := fifelse(
    model == "fta",
    "GPR x FTA",
    "GPR x DTA depth"
  )
]

sector[
  ,
  Cell := mapply(
    coefficient_cell,
    estimate,
    std_error,
    FDR_p,
    percent_effect,
    MoreArgs = list(
      effect_suffix = "%"
    )
  )
]

sector_fta <- sector[
  model == "fta",
  .(
    Sector,
    FTA_Cell = Cell,
    FTA_FDR_p = FDR_p,
    FTA_Effect = percent_effect,
    Observations = nobs
  )
]

sector_depth <- sector[
  model == "depth",
  .(
    Sector,
    Depth_Cell = Cell,
    Depth_FDR_p = FDR_p,
    Depth_Effect = percent_effect,
    Observations_Depth = nobs
  )
]

sector_wide <- merge(
  sector_fta,
  sector_depth,
  by = "Sector",
  all = TRUE
)

table_4 <- sector_wide[
  FTA_Effect < 0 &
    Depth_Effect < 0 &
    FTA_FDR_p < 0.10 &
    Depth_FDR_p < 0.10
][
  order(Depth_Effect),
  .(
    Sector,
    `GPR x FTA` = FTA_Cell,
    `BH-FDR p: FTA` =
      round(FTA_FDR_p, 4),
    `GPR x DTA depth` =
      Depth_Cell,
    `BH-FDR p: Depth` =
      round(Depth_FDR_p, 4),
    Observations =
      format_integer(Observations)
  )
]

appendix_table_a1 <- sector_wide[
  ,
  .(
    Sector,
    `GPR x FTA` = FTA_Cell,
    `BH-FDR p: FTA` =
      round(FTA_FDR_p, 4),
    `GPR x DTA depth` =
      Depth_Cell,
    `BH-FDR p: Depth` =
      round(Depth_FDR_p, 4),
    Observations =
      format_integer(Observations)
  )
][
  order(Sector)
]

save_table_csv(
  table_4,
  "table4_key_sector_heterogeneity.csv"
)

save_table_csv(
  appendix_table_a1,
  "appendix_table_a1_full_sector_results.csv",
  appendix = TRUE
)

sector_plot_data <- copy(
  sector[
    ,
    .(
      Sector,
      Term_Label,
      Effect = percent_effect,
      CI_Low = percent_effect_ci_low,
      CI_High = percent_effect_ci_high,
      FDR_p
    )
  ]
)

sector_order <- sector_plot_data[
  Term_Label == "GPR x DTA depth"
][
  order(Effect),
  Sector
]

sector_plot_data[
  ,
  Sector := factor(
    Sector,
    levels = rev(sector_order)
  )
]

figure_3 <- ggplot(
  sector_plot_data,
  aes(
    x = Effect,
    y = Sector
  )
) +
  geom_vline(
    xintercept = 0,
    linewidth = 0.4,
    linetype = "dashed"
  ) +
  geom_errorbarh(
    aes(
      xmin = CI_Low,
      xmax = CI_High
    ),
    height = 0.15,
    linewidth = 0.45
  ) +
  geom_point(
    aes(
      shape = FDR_p < 0.10
    ),
    size = 2.3
  ) +
  facet_wrap(
    ~Term_Label,
    ncol = 2,
    scales = "free_x"
  ) +
  scale_shape_manual(
    values = c(
      `TRUE` = 16,
      `FALSE` = 1
    ),
    labels = c(
      `TRUE` = "BH-FDR p < 0.10",
      `FALSE` = "Not FDR-significant"
    ),
    name = NULL
  ) +
  labs(
    title = paste(
      "Sectoral Heterogeneity in the Response",
      "of Intermediate-Goods Trade to Global GPR"
    ),
    x = "Exact percentage effect",
    y = NULL
  ) +
  theme_paper()

save_plot_both(
  figure_3,
  "figure3_sector_heterogeneity",
  width = 11,
  height = 6.5
)

fwrite(
  sector_plot_data,
  file.path(
    FIGURE_DATA_DIR,
    "figure3_sector_heterogeneity_data.csv"
  ),
  bom = TRUE
)

# ------------------------------------------------------------
# 9. TABLE 5: TRADE-LINK SURVIVAL
# ------------------------------------------------------------
survival_main <- read_output_csv(
  input_files$step13b
)

survival_main <- survival_main[
  inference == "pair_plus_year_cluster"
]

survival_spec_labels <- c(
  fta_no_size =
    "(1) FTA, no size",
  fta_size_adjusted =
    "(2) FTA + size",
  depth_no_size =
    "(3) Depth, no size",
  depth_size_adjusted =
    "(4) Depth + size",
  joint_size_adjusted =
    "(5) Joint + size"
)

survival_tidy <- survival_main[
  model %in% names(
    survival_spec_labels
  ),
  .(
    Specification =
      survival_spec_labels[model],
    Term = fifelse(
      grepl(
        "fta",
        term,
        fixed = TRUE
      ),
      "GPR x FTA",
      "GPR x DTA depth"
    ),
    estimate,
    std_error,
    p_value,
    effect =
      effect_percentage_points,
    nobs,
    Size_Control =
      grepl(
        "size_adjusted",
        model,
        fixed = TRUE
      )
  )
]

survival_tidy[
  ,
  Cell := mapply(
    coefficient_cell,
    estimate,
    std_error,
    p_value,
    effect,
    MoreArgs = list(
      effect_suffix = " pp"
    )
  )
]

table_5 <- dcast(
  survival_tidy,
  Term ~ Specification,
  value.var = "Cell",
  fill = "—"
)

setnames(
  table_5,
  "Term",
  "Variable"
)

spec_order_5 <- unname(
  survival_spec_labels
)

table_5 <- table_5[
  ,
  c(
    "Variable",
    spec_order_5
  ),
  with = FALSE
]

size_control_row <- data.table(
  Variable = "Lagged link-size control"
)

observation_row <- data.table(
  Variable = "Observations"
)

for (
  spec_name in spec_order_5
) {
  size_control_row[
    ,
    (spec_name) := ifelse(
      unique(
        survival_tidy[
          Specification ==
            spec_name,
          Size_Control
        ]
      ),
      "Yes",
      "No"
    )
  ]

  observation_row[
    ,
    (spec_name) :=
      format_integer(
        unique(
          survival_tidy[
            Specification ==
              spec_name,
            nobs
          ]
        )
      )
  ]
}

fixed_effect_rows <- data.table(
  Variable = c(
    "Pair-HS2 fixed effects",
    "Exporter-year fixed effects",
    "Importer-year fixed effects",
    "HS2-year fixed effects"
  )
)

for (
  spec_name in spec_order_5
) {
  fixed_effect_rows[
    ,
    (spec_name) := "Yes"
  ]
}

table_5 <- rbindlist(
  list(
    table_5,
    size_control_row,
    fixed_effect_rows,
    observation_row
  ),
  fill = TRUE
)

save_table_csv(
  table_5,
  "table5_trade_link_survival.csv"
)

save_table_csv(
  survival_tidy,
  "table5_trade_link_survival_tidy.csv"
)

# ------------------------------------------------------------
# 10. TABLE 6 AND FIGURE 4: SURVIVAL ROBUSTNESS
# ------------------------------------------------------------
survival_robust <- read_output_csv(
  input_files$step13c
)

survival_robust <- survival_robust[
  inference == "pair_plus_year_cluster" &
    term == "shock_x_depth"
]

if (
  !"effect_percentage_points" %in%
    names(survival_robust)
) {
  survival_robust[
    ,
    effect_percentage_points :=
      100 * estimate
  ]
}

if (
  !"ci_low_percentage_points" %in%
    names(survival_robust)
) {
  survival_robust[
    ,
    ci_low_percentage_points :=
      100 * (
        estimate -
          1.96 * std_error
      )
  ]
  survival_robust[
    ,
    ci_high_percentage_points :=
      100 * (
        estimate +
          1.96 * std_error
      )
  ]
}

sample_col_13c <- pick_column(
  survival_robust,
  c(
    "sample",
    "sample_name"
  ),
  required = FALSE
)

shock_labels <- c(
  mean_gpr = "Baseline annual mean GPR",
  log_mean_gpr = "Log annual mean GPR",
  threat_gpr = "GPR threats",
  act_gpr = "GPR acts",
  peak_gpr = "Annual peak GPR"
)

full_robust <- survival_robust[
  shock %in% names(
    shock_labels
  )
]

if (!is.na(sample_col_13c)) {
  full_robust <- full_robust[
    get(sample_col_13c) %in%
      c(
        "full_2008_2023",
        "full_sample",
        "full"
      )
  ]
}

# If the file uses one full-sample row per shock and no explicit
# full-sample labels, retain the first unique shock.
if (nrow(full_robust) == 0L) {
  full_robust <- survival_robust[
    shock %in% names(
      shock_labels
    )
  ][
    !duplicated(shock)
  ]
}

table_6_panel_a <- full_robust[
  ,
  .(
    Panel = "A. Alternative global GPR measures",
    Check = shock_labels[shock],
    Estimate = estimate,
    SE = std_error,
    `Effect (pp)` =
      effect_percentage_points,
    `p-value` = p_value,
    N = nobs
  )
]

established <- data.table()

if (!is.na(sample_col_13c)) {
  established <- survival_robust[
    grepl(
      "100k|1m",
      get(sample_col_13c),
      ignore.case = TRUE
    ),
    .(
      Panel =
        "B. Established-link samples",
      Check = fifelse(
        grepl(
          "100k",
          get(sample_col_13c),
          ignore.case = TRUE
        ),
        "Lagged trade at least USD 100,000",
        "Lagged trade at least USD 1 million"
      ),
      Estimate = estimate,
      SE = std_error,
      `Effect (pp)` =
        effect_percentage_points,
      `p-value` = p_value,
      N = nobs
    )
  ]
}

fta_only <- read_output_csv(
  input_files$step15a
)

fta_only <- fta_only[
  inference == "pair_plus_year_cluster" &
    model == "fta_only_survival_size_adjusted"
]

if (!"effect" %in% names(fta_only)) {
  fta_only[
    ,
    effect := 100 * estimate
  ]
}

table_6_panel_c <- fta_only[
  ,
  .(
    Panel =
      "C. Active-FTA-only sample",
    Check =
      "FTA-only, size-adjusted survival",
    Estimate = estimate,
    SE = std_error,
    `Effect (pp)` = 100 * estimate,
    `p-value` = p_value,
    N = nobs
  )
]

table_6 <- rbindlist(
  list(
    table_6_panel_a,
    established,
    table_6_panel_c
  ),
  fill = TRUE
)

table_6[
  ,
  `:=`(
    Estimate =
      round(Estimate, 4),
    SE =
      round(SE, 4),
    `Effect (pp)` =
      round(
        `Effect (pp)`,
        3
      ),
    `p-value` =
      round(
        `p-value`,
        4
      ),
    N =
      format_integer(N)
  )
]

save_table_csv(
  table_6,
  "table6_survival_robustness.csv"
)

leave_one_out <- read_output_csv(
  input_files$step13c_loo
)

leave_one_out <- leave_one_out[
  inference == "pair_plus_year_cluster" &
    term == "shock_x_depth"
]

excluded_year_col <- pick_column(
  leave_one_out,
  c(
    "excluded_year",
    "year_excluded"
  )
)

if (
  !"effect_percentage_points" %in%
    names(leave_one_out)
) {
  leave_one_out[
    ,
    effect_percentage_points :=
      100 * estimate
  ]
}

if (
  !"ci_low_percentage_points" %in%
    names(leave_one_out)
) {
  leave_one_out[
    ,
    ci_low_percentage_points :=
      100 * (
        estimate -
          1.96 * std_error
      )
  ]
  leave_one_out[
    ,
    ci_high_percentage_points :=
      100 * (
        estimate +
          1.96 * std_error
      )
  ]
}

setnames(
  leave_one_out,
  excluded_year_col,
  "Excluded_Year"
)

baseline_depth_effect <- survival_main[
  model == "joint_size_adjusted" &
    inference == "pair_plus_year_cluster" &
    term ==
      "gpr_x_depth_strict_l1_10",
  effect_percentage_points
]

figure_4 <- ggplot(
  leave_one_out,
  aes(
    x = factor(Excluded_Year),
    y = effect_percentage_points
  )
) +
  geom_hline(
    yintercept = 0,
    linewidth = 0.4,
    linetype = "dashed"
  ) +
  geom_hline(
    yintercept =
      baseline_depth_effect,
    linewidth = 0.5,
    linetype = "dotdash"
  ) +
  geom_errorbar(
    aes(
      ymin = ci_low_percentage_points,
      ymax = ci_high_percentage_points
    ),
    width = 0.18,
    linewidth = 0.45
  ) +
  geom_point(
    size = 2.2
  ) +
  labs(
    title = paste(
      "Leave-One-Year-Out Estimates of the",
      "DTA Depth-Survival Interaction"
    ),
    subtitle = paste(
      "Dashed-dot line denotes the full-sample estimate"
    ),
    x = "Excluded transition year",
    y = "Effect on link-survival probability (percentage points)"
  ) +
  theme_paper() +
  theme(
    axis.text.x = element_text(
      angle = 45,
      hjust = 1
    )
  )

save_plot_both(
  figure_4,
  "figure4_leave_one_year_out_survival",
  width = 9.5,
  height = 5.8
)

fwrite(
  leave_one_out,
  file.path(
    FIGURE_DATA_DIR,
    "figure4_leave_one_year_out_data.csv"
  ),
  bom = TRUE
)

# ------------------------------------------------------------
# 11. TABLE 7: POST-EXIT RECOVERY
# ------------------------------------------------------------
recovery_interactions <- read_output_csv(
  input_files$step14b
)

recovery_interactions <- recovery_interactions[
  inference == "pair_plus_year_cluster" &
    term ==
      "gpr_x_depth_strict_l1_10"
]

outcome_labels <- c(
  reenter_1y =
    "Re-entry within one year",
  reenter_within_2y =
    "Re-entry within two years",
  full_recovery_1y =
    "Full recovery within one year",
  full_recovery_within_2y =
    "Full recovery within two years"
)

recovery_interactions[
  ,
  Outcome_Label :=
    outcome_labels[outcome]
]

recovery_interactions[
  ,
  Cell := mapply(
    coefficient_cell,
    estimate,
    std_error,
    p_value,
    effect_percentage_points,
    MoreArgs = list(
      effect_suffix = " pp"
    )
  )
]

recovery_directed <- recovery_interactions[
  fe_spec == "directed_pair_fe",
  .(
    Outcome = Outcome_Label,
    `Directed-pair FE` = Cell,
    `N: directed-pair FE` =
      format_integer(nobs)
  )
]

recovery_pair_hs2 <- recovery_interactions[
  fe_spec == "pair_hs2_fe",
  .(
    Outcome = Outcome_Label,
    `Pair-HS2 FE` = Cell,
    `N: pair-HS2 FE` =
      format_integer(nobs)
  )
]

table_7 <- merge(
  recovery_directed,
  recovery_pair_hs2,
  by = "Outcome",
  all = TRUE
)

table_7[
  ,
  order_id :=
    match(
      Outcome,
      unname(outcome_labels)
    )
]

setorder(
  table_7,
  order_id
)

table_7[
  ,
  order_id := NULL
]

save_table_csv(
  table_7,
  "table7_post_exit_recovery.csv"
)

# Appendix table: net recovery interaction by agreement depth
recovery_net <- read_output_csv(
  input_files$step14b_net
)

appendix_table_a4 <- recovery_net[
  fe_spec == "directed_pair_fe" &
    inference == "pair_plus_year_cluster" &
    enforceable_provisions %in%
      c(0, 10, 20, 30),
  .(
    Outcome =
      outcome_labels[outcome],
    `Enforceable provisions` =
      enforceable_provisions,
    `Net effect (pp)` =
      round(
        effect_percentage_points,
        4
      ),
    `p-value` =
      round(
        p_value,
        4
      ),
    N =
      format_integer(nobs)
  )
][
  order(
    Outcome,
    `Enforceable provisions`
  )
]

save_table_csv(
  appendix_table_a4,
  "appendix_table_a4_recovery_net_effects.csv",
  appendix = TRUE
)

# ------------------------------------------------------------
# 12. TABLE 8: COUNTRY-SPECIFIC GPR ROBUSTNESS
# ------------------------------------------------------------
country_gpr <- read_output_csv(
  input_files$step15c
)

country_gpr <- country_gpr[
  inference == "pair_plus_year_cluster"
]

country_gpr[
  ,
  Shock_Label := fcase(
    shock == "restricted_global_gpr",
      "Restricted-sample global GPR",
    shock == "pair_average_country_gpr",
      "Average pair-country GPR",
    shock == "pair_maximum_country_gpr",
      "Maximum pair-country GPR",
    shock ==
      "pair_log_average_country_gpr",
      "Log-average pair-country GPR",
    default = shock
  )
]

country_gpr[
  ,
  Term_Label := fifelse(
    term == "shock_x_fta",
    "GPR x FTA",
    "GPR x DTA depth"
  )
]

country_gpr[
  ,
  Effect := fifelse(
    outcome_type ==
      "trade_value_ppml",
    100 * (
      exp(estimate) - 1
    ),
    100 * estimate
  )
]

country_gpr[
  ,
  Effect_Unit := fifelse(
    outcome_type ==
      "trade_value_ppml",
    "%",
    " pp"
  )
]

country_gpr[
  ,
  Cell := mapply(
    coefficient_cell,
    estimate,
    std_error,
    p_value,
    Effect,
    Effect_Unit
  )
]

table_8_long <- country_gpr[
  ,
  .(
    Panel = fifelse(
      outcome_type ==
        "trade_value_ppml",
      "A. Intermediate-goods trade value",
      "B. Trade-link survival"
    ),
    Shock = Shock_Label,
    Term = Term_Label,
    Cell,
    N =
      format_integer(nobs)
  )
]

table_8 <- dcast(
  table_8_long,
  Panel + Shock + N ~ Term,
  value.var = "Cell",
  fill = "—"
)

setcolorder(
  table_8,
  c(
    "Panel",
    "Shock",
    "GPR x FTA",
    "GPR x DTA depth",
    "N"
  )
)

save_table_csv(
  table_8,
  "table8_country_specific_gpr.csv"
)

# Appendix coefficient plot for country-specific GPR
country_plot_data <- country_gpr[
  ,
  .(
    Outcome = fifelse(
      outcome_type ==
        "trade_value_ppml",
      "Trade value (%)",
      "Link survival (pp)"
    ),
    Shock = Shock_Label,
    Term = Term_Label,
    Effect,
    CI_Low = fifelse(
      outcome_type ==
        "trade_value_ppml",
      100 * (
        exp(
          estimate -
            1.96 * std_error
        ) - 1
      ),
      100 * (
        estimate -
          1.96 * std_error
      )
    ),
    CI_High = fifelse(
      outcome_type ==
        "trade_value_ppml",
      100 * (
        exp(
          estimate +
            1.96 * std_error
        ) - 1
      ),
      100 * (
        estimate +
          1.96 * std_error
      )
    )
  )
]

figure_a2 <- ggplot(
  country_plot_data,
  aes(
    x = Effect,
    y = Shock,
    shape = Term
  )
) +
  geom_vline(
    xintercept = 0,
    linewidth = 0.4,
    linetype = "dashed"
  ) +
  geom_errorbarh(
    aes(
      xmin = CI_Low,
      xmax = CI_High
    ),
    height = 0.14,
    position = position_dodge(
      width = 0.45
    )
  ) +
  geom_point(
    size = 2.2,
    position = position_dodge(
      width = 0.45
    )
  ) +
  facet_wrap(
    ~Outcome,
    scales = "free_x",
    ncol = 1
  ) +
  labs(
    title = paste(
      "Country-Specific GPR Robustness:",
      "Trade Value and Link Survival"
    ),
    x = "Estimated interaction effect",
    y = NULL,
    shape = NULL
  ) +
  theme_paper()

save_plot_both(
  figure_a2,
  "appendix_figure_a2_country_gpr_coefficients",
  width = 9,
  height = 7.5
)

fwrite(
  country_plot_data,
  file.path(
    FIGURE_DATA_DIR,
    "appendix_figure_a2_country_gpr_data.csv"
  ),
  bom = TRUE
)

# ------------------------------------------------------------
# 13. APPENDIX TABLES: BUNDLES AND PROVISIONS
# ------------------------------------------------------------
bundle_results <- read_output_csv(
  input_files$step12b
)

appendix_table_a2 <- bundle_results[
  model_spec == "conditional_on_fta" &
    inference == "pair_plus_year_cluster",
  .(
    Bundle = bundle_label,
    Estimate =
      round(estimate, 4),
    SE =
      round(std_error, 4),
    `Full-bundle effect (%)` =
      round(
        percent_effect_full_bundle,
        3
      ),
    `Raw p-value` =
      round(p_value, 4),
    `BH-FDR p-value` =
      round(
        p_value_fdr_bh,
        4
      ),
    N =
      format_integer(nobs)
  )
][
  order(Bundle)
]

save_table_csv(
  appendix_table_a2,
  "appendix_table_a2_dta_bundles.csv",
  appendix = TRUE
)

provision_results <- read_output_csv(
  input_files$step12c
)

appendix_table_a3 <- provision_results[
  inference == "pair_plus_year_cluster",
  .(
    Provision = provision_label,
    Estimate =
      round(estimate, 4),
    SE =
      round(std_error, 4),
    `Effect (%)` =
      round(percent_effect, 3),
    `Raw p-value` =
      round(p_value, 4),
    `BH-FDR p-value` =
      round(
        p_value_fdr_bh,
        4
      ),
    N =
      format_integer(nobs)
  )
][
  order(Provision)
]

save_table_csv(
  appendix_table_a3,
  "appendix_table_a3_individual_provisions.csv",
  appendix = TRUE
)

# ------------------------------------------------------------
# 14. FIGURE 1: CONCEPTUAL FRAMEWORK
# ------------------------------------------------------------
figure_1 <- ggplot() +
  annotate(
    "rect",
    xmin = 3.4,
    xmax = 6.6,
    ymin = 8.6,
    ymax = 9.6,
    fill = "white",
    color = "black",
    linewidth = 0.6
  ) +
  annotate(
    "text",
    x = 5,
    y = 9.25,
    label = "TRADE AGREEMENTS",
    fontface = "bold",
    size = 5
  ) +
  annotate(
    "text",
    x = 5,
    y = 8.9,
    label = "FTA membership | DTA depth",
    size = 3.8
  ) +
  annotate(
    "rect",
    xmin = 0.7,
    xmax = 4.4,
    ymin = 4.4,
    ymax = 7.5,
    fill = "white",
    color = "black",
    linewidth = 0.6
  ) +
  annotate(
    "text",
    x = 2.55,
    y = 7.15,
    label = "INSTITUTIONAL BUFFERING",
    fontface = "bold",
    size = 4
  ) +
  annotate(
    "text",
    x = 2.55,
    y = 5.95,
    label = paste(
      "Lower trade costs",
      "Regulatory coordination",
      "Credible commitments",
      "Customs cooperation",
      sep = "\n"
    ),
    lineheight = 1.25,
    size = 3.6
  ) +
  annotate(
    "text",
    x = 2.55,
    y = 4.75,
    label = "Greater trade resilience",
    fontface = "bold",
    size = 3.7
  ) +
  annotate(
    "rect",
    xmin = 5.6,
    xmax = 9.3,
    ymin = 4.4,
    ymax = 7.5,
    fill = "white",
    color = "black",
    linewidth = 0.6
  ) +
  annotate(
    "text",
    x = 7.45,
    y = 7.15,
    label = "INTEGRATION EXPOSURE",
    fontface = "bold",
    size = 4
  ) +
  annotate(
    "text",
    x = 7.45,
    y = 5.95,
    label = paste(
      "Deeper specialization",
      "Input specificity",
      "Supplier dependence",
      "Switching costs",
      sep = "\n"
    ),
    lineheight = 1.25,
    size = 3.6
  ) +
  annotate(
    "text",
    x = 7.45,
    y = 4.75,
    label = "Greater shock sensitivity",
    fontface = "bold",
    size = 3.7
  ) +
  annotate(
    "rect",
    xmin = 2.0,
    xmax = 8.0,
    ymin = 1.2,
    ymax = 2.4,
    fill = "white",
    color = "black",
    linewidth = 0.6
  ) +
  annotate(
    "text",
    x = 5,
    y = 1.8,
    label = paste(
      "TRADE VALUE | LINK SURVIVAL |",
      "POST-EXIT RECOVERY"
    ),
    fontface = "bold",
    size = 4.2
  ) +
  annotate(
    "segment",
    x = 5,
    xend = 2.55,
    y = 8.6,
    yend = 7.55,
    arrow = grid::arrow(
      length = grid::unit(
        0.15,
        "inches"
      ),
      type = "closed"
    ),
    linewidth = 0.6
  ) +
  annotate(
    "segment",
    x = 5,
    xend = 7.45,
    y = 8.6,
    yend = 7.55,
    arrow = grid::arrow(
      length = grid::unit(
        0.15,
        "inches"
      ),
      type = "closed"
    ),
    linewidth = 0.6
  ) +
  annotate(
    "segment",
    x = 2.55,
    xend = 4.6,
    y = 4.35,
    yend = 2.45,
    arrow = grid::arrow(
      length = grid::unit(
        0.15,
        "inches"
      ),
      type = "closed"
    ),
    linewidth = 0.6
  ) +
  annotate(
    "segment",
    x = 7.45,
    xend = 5.4,
    y = 4.35,
    yend = 2.45,
    arrow = grid::arrow(
      length = grid::unit(
        0.15,
        "inches"
      ),
      type = "closed"
    ),
    linewidth = 0.6
  ) +
  coord_cartesian(
    xlim = c(0, 10),
    ylim = c(0.5, 10)
  ) +
  theme_void()

save_plot_both(
  figure_1,
  "figure1_conceptual_framework",
  width = 11,
  height = 7
)

# ------------------------------------------------------------
# 15. FIGURE 2: GPR AND AGREEMENT COVERAGE
# ------------------------------------------------------------
figure_2_long <- rbindlist(
  list(
    figure_2_data[
      ,
      .(
        year,
        Metric =
          "Global GPR (standardized)",
        Value = gpr_mean_z
      )
    ],
    figure_2_data[
      ,
      .(
        year,
        Metric =
          "Bilateral pairs with active FTA (%)",
        Value =
          fta_coverage_percent
      )
    ],
    figure_2_data[
      ,
      .(
        year,
        Metric =
          "Mean enforceable depth among active FTAs",
        Value =
          mean_depth_provisions
      )
    ]
  )
)

metric_order <- c(
  "Global GPR (standardized)",
  "Bilateral pairs with active FTA (%)",
  "Mean enforceable depth among active FTAs"
)

figure_2_long[
  ,
  Metric := factor(
    Metric,
    levels = metric_order
  )
]

figure_2 <- ggplot(
  figure_2_long,
  aes(
    x = year,
    y = Value
  )
) +
  geom_line(
    linewidth = 0.7
  ) +
  geom_point(
    size = 1.5
  ) +
  facet_wrap(
    ~Metric,
    scales = "free_y",
    ncol = 1
  ) +
  scale_x_continuous(
    breaks = seq(
      2007,
      2023,
      by = 2
    )
  ) +
  labs(
    title = paste(
      "Global Geopolitical Risk and",
      "Trade-Agreement Coverage, 2007-2023"
    ),
    x = "Year",
    y = NULL
  ) +
  theme_paper()

save_plot_both(
  figure_2,
  "figure2_gpr_agreement_coverage",
  width = 9.5,
  height = 8.2
)

# ------------------------------------------------------------
# 16. APPENDIX FIGURE A1: EXIT AND RECOVERY RATES
# ------------------------------------------------------------
if (
  file.exists(
    input_files$survival_by_year
  ) &&
    file.exists(
      input_files$recovery_by_year
    )
) {
  survival_by_year <- read_output_csv(
    input_files$survival_by_year
  )
  recovery_by_year <- read_output_csv(
    input_files$recovery_by_year
  )

  recovery_year_col <- pick_column(
    recovery_by_year,
    c(
      "exit_year",
      "year"
    )
  )

  reentry_1y_col <- pick_column(
    recovery_by_year,
    c(
      "reentry_1y_rate",
      "reenter_1y_rate",
      "share_reenter_1y"
    ),
    required = FALSE
  )

  reentry_2y_col <- pick_column(
    recovery_by_year,
    c(
      "reentry_within_2y_rate",
      "reenter_within_2y_rate",
      "share_reenter_within_2y"
    ),
    required = FALSE
  )

  if (
    !is.na(reentry_1y_col) &&
      !is.na(reentry_2y_col)
  ) {
    appendix_figure_a1_data <- rbindlist(
      list(
        survival_by_year[
          ,
          .(
            year,
            Rate =
              100 * exit_rate,
            Series =
              "Exit rate"
          )
        ],
        recovery_by_year[
          ,
          .(
            year =
              get(
                recovery_year_col
              ),
            Rate =
              100 * get(
                reentry_1y_col
              ),
            Series =
              "One-year re-entry rate"
          )
        ],
        recovery_by_year[
          ,
          .(
            year =
              get(
                recovery_year_col
              ),
            Rate =
              100 * get(
                reentry_2y_col
              ),
            Series =
              "Two-year re-entry rate"
          )
        ]
      )
    )

    figure_a1 <- ggplot(
      appendix_figure_a1_data,
      aes(
        x = year,
        y = Rate,
        linetype = Series,
        shape = Series
      )
    ) +
      geom_line(
        linewidth = 0.7
      ) +
      geom_point(
        size = 1.7
      ) +
      scale_x_continuous(
        breaks = seq(
          min(
            appendix_figure_a1_data$year,
            na.rm = TRUE
          ),
          max(
            appendix_figure_a1_data$year,
            na.rm = TRUE
          ),
          by = 2
        )
      ) +
      labs(
        title = paste(
          "Annual Trade-Link Exit and",
          "Post-Exit Re-entry Rates"
        ),
        x = "Year",
        y = "Percent",
        linetype = NULL,
        shape = NULL
      ) +
      theme_paper()

    save_plot_both(
      figure_a1,
      "appendix_figure_a1_exit_reentry_rates",
      width = 9.5,
      height = 5.8
    )

    fwrite(
      appendix_figure_a1_data,
      file.path(
        FIGURE_DATA_DIR,
        "appendix_figure_a1_exit_reentry_data.csv"
      ),
      bom = TRUE
    )
  } else {
    warning(
      paste(
        "Recovery-by-year file exists, but expected",
        "re-entry-rate columns were not detected.",
        "Appendix Figure A1 was skipped."
      )
    )
  }
}

# ------------------------------------------------------------
# 17. EXCEL WORKBOOK
# ------------------------------------------------------------
workbook_file <- file.path(
  PAPER_OUT,
  "AIID_DTA_GPR_Paper_Tables.xlsx"
)

wb <- createWorkbook()

header_style <- createStyle(
  textDecoration = "bold",
  border = "Bottom",
  borderStyle = "thin",
  valign = "center",
  wrapText = TRUE
)

title_style <- createStyle(
  textDecoration = "bold",
  fontSize = 12
)

body_style <- createStyle(
  valign = "top",
  wrapText = TRUE
)

add_table_sheet <- function(
  workbook,
  sheet_name,
  table_title,
  data
) {
  addWorksheet(
    workbook,
    sheet_name
  )

  writeData(
    workbook,
    sheet_name,
    table_title,
    startRow = 1,
    startCol = 1
  )

  addStyle(
    workbook,
    sheet_name,
    title_style,
    rows = 1,
    cols = 1,
    gridExpand = TRUE
  )

  writeData(
    workbook,
    sheet_name,
    data,
    startRow = 3,
    startCol = 1,
    withFilter = FALSE
  )

  addStyle(
    workbook,
    sheet_name,
    header_style,
    rows = 3,
    cols = seq_len(
      ncol(data)
    ),
    gridExpand = TRUE
  )

  if (nrow(data) > 0L) {
    addStyle(
      workbook,
      sheet_name,
      body_style,
      rows = 4:(
        nrow(data) + 3L
      ),
      cols = seq_len(
        ncol(data)
      ),
      gridExpand = TRUE
    )
  }

  freezePane(
    workbook,
    sheet_name,
    firstActiveRow = 4
  )

  setColWidths(
    workbook,
    sheet_name,
    cols = seq_len(
      ncol(data)
    ),
    widths = "auto"
  )
}

add_table_sheet(
  wb,
  "T1_Variables",
  "Table 1. Variable Definitions and Data Sources",
  table_1
)

add_table_sheet(
  wb,
  "T2_Descriptives",
  "Table 2. Descriptive Statistics of Key Variables",
  table_2
)

add_table_sheet(
  wb,
  "T3_Baseline_PPML",
  "Table 3. Baseline PPML Estimates for Intermediate-Goods Trade",
  table_3
)

add_table_sheet(
  wb,
  "T4_Key_Sectors",
  "Table 4. Key Sector Heterogeneity Results",
  table_4
)

add_table_sheet(
  wb,
  "T5_Survival",
  "Table 5. Trade-Link Survival under Global GPR",
  table_5
)

add_table_sheet(
  wb,
  "T6_Robustness",
  "Table 6. Robustness of the DTA Depth-Survival Association",
  table_6
)

add_table_sheet(
  wb,
  "T7_Recovery",
  "Table 7. Post-Exit Recovery Outcomes",
  table_7
)

add_table_sheet(
  wb,
  "T8_Country_GPR",
  "Table 8. Country-Specific GPR Robustness",
  table_8
)

add_table_sheet(
  wb,
  "A1_All_Sectors",
  "Appendix Table A1. Full Sector-Level Results",
  appendix_table_a1
)

add_table_sheet(
  wb,
  "A2_Bundles",
  "Appendix Table A2. DTA Provision Bundles",
  appendix_table_a2
)

add_table_sheet(
  wb,
  "A3_Provisions",
  "Appendix Table A3. Individual Enforceable Provisions",
  appendix_table_a3
)

add_table_sheet(
  wb,
  "A4_Recovery_Net",
  "Appendix Table A4. Net Recovery Effects by Agreement Depth",
  appendix_table_a4
)

saveWorkbook(
  wb,
  workbook_file,
  overwrite = TRUE
)

# ------------------------------------------------------------
# 18. OUTPUT MANIFEST
# ------------------------------------------------------------
all_output_files <- list.files(
  PAPER_OUT,
  recursive = TRUE,
  full.names = TRUE
)

all_output_files <- all_output_files[
  !grepl(
    "paper_output_manifest.csv$",
    all_output_files
  )
]

manifest <- data.table(
  File = normalizePath(
    all_output_files,
    winslash = "/",
    mustWork = TRUE
  ),
  Relative_Path = substring(
    normalizePath(
      all_output_files,
      winslash = "/",
      mustWork = TRUE
    ),
    nchar(
      normalizePath(
        PAPER_OUT,
        winslash = "/",
        mustWork = TRUE
      )
    ) + 2L
  ),
  Size_KB = round(
    file.info(
      all_output_files
    )$size / 1024,
    2
  ),
  Modified = file.info(
    all_output_files
  )$mtime
)

fwrite(
  manifest,
  file.path(
    PAPER_OUT,
    "paper_output_manifest.csv"
  ),
  bom = TRUE
)

# ------------------------------------------------------------
# 19. COMPLETION REPORT
# ------------------------------------------------------------
report_lines <- c(
  paste(
    rep("=", 92),
    collapse = ""
  ),
  "AIID DTA-GPR PAPER OUTPUT GENERATOR COMPLETED",
  paste(
    rep("=", 92),
    collapse = ""
  ),
  paste0(
    "Output root: ",
    PAPER_OUT
  ),
  "",
  "MAIN TABLES",
  "- Table 1: Variable definitions and sources",
  "- Table 2: Descriptive statistics",
  "- Table 3: Baseline PPML",
  "- Table 4: Key sector heterogeneity",
  "- Table 5: Trade-link survival",
  "- Table 6: Survival robustness",
  "- Table 7: Post-exit recovery",
  "- Table 8: Country-specific GPR robustness",
  "",
  "MAIN FIGURES",
  "- Figure 1: Conceptual framework",
  "- Figure 2: GPR and agreement coverage",
  "- Figure 3: Sector heterogeneity coefficient plot",
  "- Figure 4: Leave-one-year-out survival estimates",
  "",
  "APPENDIX OUTPUTS",
  "- Full ten-sector table",
  "- DTA bundle table",
  "- Individual-provision table",
  "- Recovery net-effects table",
  "- Annual exit/re-entry figure when audit columns are available",
  "- Country-GPR coefficient figure",
  "",
  paste0(
    "Excel workbook: ",
    workbook_file
  ),
  paste0(
    "Manifest: ",
    file.path(
      PAPER_OUT,
      "paper_output_manifest.csv"
    )
  )
)

writeLines(
  report_lines,
  file.path(
    PAPER_OUT,
    "paper_output_report.txt"
  ),
  useBytes = TRUE
)

cat(
  paste(
    report_lines,
    collapse = "\n"
  ),
  "\n"
)

# ============================================================
# AIID DTA–GPR PROJECT
# STEP 9 — R ENVIRONMENT CHECK + PILOT PPML
#
# This script intentionally runs the smaller pair-year and DDD
# panels first. It does NOT run the 16.75-million-row HS2 model.
# ============================================================

# ------------------------------------------------------------
# 0. PROJECT PATH
# ------------------------------------------------------------
PROJECT_ROOT <- "H:/AIID_DTA_GPR"

PAIR_YEAR_FILE <- file.path(
  PROJECT_ROOT,
  "data",
  "processed",
  "estimation_pair_year_intermediate.parquet"
)

DDD_FILE <- file.path(
  PROJECT_ROOT,
  "data",
  "processed",
  "estimation_pair_enduse_year_ddd.parquet"
)

AUDIT_DIR <- file.path(
  PROJECT_ROOT,
  "outputs",
  "audit"
)

TABLE_DIR <- file.path(
  PROJECT_ROOT,
  "outputs",
  "tables"
)

FIGURE_DIR <- file.path(
  PROJECT_ROOT,
  "outputs",
  "figures"
)

MODEL_DIR <- file.path(
  PROJECT_ROOT,
  "outputs",
  "models"
)

dir.create(AUDIT_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(TABLE_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(FIGURE_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(MODEL_DIR, recursive = TRUE, showWarnings = FALSE)


# ------------------------------------------------------------
# 1. INSTALL AND LOAD PACKAGES
# ------------------------------------------------------------
required_packages <- c(
  "arrow",
  "data.table",
  "fixest",
  "ggplot2"
)

installed <- rownames(installed.packages())

missing_packages <- setdiff(
  required_packages,
  installed
)

if (length(missing_packages) > 0) {
  message(
    "Installing missing packages: ",
    paste(missing_packages, collapse = ", ")
  )

  install.packages(
    missing_packages,
    repos = "https://cloud.r-project.org",
    dependencies = TRUE
  )
}

suppressPackageStartupMessages({
  library(arrow)
  library(data.table)
  library(fixest)
  library(ggplot2)
})

# Use all available CPU threads in fixest.
setFixest_nthreads(0)


# ------------------------------------------------------------
# 2. HELPER FUNCTIONS
# ------------------------------------------------------------
stop_if_missing <- function(paths) {
  missing <- paths[!file.exists(paths)]

  if (length(missing) > 0) {
    stop(
      paste0(
        "Missing required file(s):\n",
        paste(missing, collapse = "\n")
      ),
      call. = FALSE
    )
  }
}


make_unordered_pair_id <- function(exporter, importer) {
  paste(
    pmin(exporter, importer),
    pmax(exporter, importer),
    sep = "_"
  )
}


extract_fixest_coefficients <- function(model, model_name) {
  coefficient_table <- as.data.frame(
    fixest::coeftable(model)
  )

  coefficient_table$term <- rownames(
    coefficient_table
  )

  rownames(coefficient_table) <- NULL

  # fixest's coeftable has four numeric columns:
  # estimate, standard error, test statistic, and p-value.
  names(coefficient_table)[1:4] <- c(
    "estimate",
    "std_error",
    "z_value",
    "p_value"
  )

  coefficient_table$model <- model_name

  coefficient_table[
    ,
    c(
      "model",
      "term",
      "estimate",
      "std_error",
      "z_value",
      "p_value"
    )
  ]
}


write_fixest_table <- function(
  models,
  file_path,
  coefficient_dictionary
) {
  table_output <- fixest::etable(
    models,
    tex = FALSE,
    dict = coefficient_dictionary,
    fitstat = ~ n + ll + sq.cor,
    digits = 4,
    se.below = TRUE
  )

  write.csv(
    table_output,
    file_path,
    row.names = FALSE,
    fileEncoding = "UTF-8"
  )
}


# ------------------------------------------------------------
# 3. VERIFY INPUT FILES
# ------------------------------------------------------------
stop_if_missing(
  c(
    PAIR_YEAR_FILE,
    DDD_FILE
  )
)

message("Reading the pair-year panel ...")

pair_year <- as.data.table(
  arrow::read_parquet(
    PAIR_YEAR_FILE,
    as_data_frame = TRUE
  )
)

message("Reading the DDD panel ...")

ddd <- as.data.table(
  arrow::read_parquet(
    DDD_FILE,
    as_data_frame = TRUE
  )
)


# ------------------------------------------------------------
# 4. DATA AUDIT
# ------------------------------------------------------------
expected_pair_year_rows <- 160L * 159L * 17L
expected_ddd_rows <- expected_pair_year_rows * 2L

if (nrow(pair_year) != expected_pair_year_rows) {
  stop(
    paste0(
      "Unexpected pair-year row count: ",
      format(nrow(pair_year), big.mark = ","),
      ". Expected ",
      format(expected_pair_year_rows, big.mark = ","),
      "."
    ),
    call. = FALSE
  )
}

if (nrow(ddd) != expected_ddd_rows) {
  stop(
    paste0(
      "Unexpected DDD row count: ",
      format(nrow(ddd), big.mark = ","),
      ". Expected ",
      format(expected_ddd_rows, big.mark = ","),
      "."
    ),
    call. = FALSE
  )
}

pair_year_duplicate_count <- pair_year[
  ,
  .N,
  by = .(
    exporter_iso3,
    importer_iso3,
    year
  )
][N > 1, .N]

if (pair_year_duplicate_count > 0) {
  stop(
    "Duplicate exporter-importer-year keys in pair-year panel.",
    call. = FALSE
  )
}

ddd_duplicate_count <- ddd[
  ,
  .N,
  by = .(
    exporter_iso3,
    importer_iso3,
    year,
    end_use
  )
][N > 1, .N]

if (ddd_duplicate_count > 0) {
  stop(
    "Duplicate exporter-importer-year-end-use keys in DDD panel.",
    call. = FALSE
  )
}

pair_year[
  ,
  unordered_pair_id := make_unordered_pair_id(
    exporter_iso3,
    importer_iso3
  )
]

ddd[
  ,
  unordered_pair_id := make_unordered_pair_id(
    exporter_iso3,
    importer_iso3
  )
]

# Convert Arrow logical values explicitly.
pair_year[
  ,
  baseline_depth_available :=
    as.logical(baseline_depth_available)
]

pair_year[
  ,
  structural_zero :=
    as.logical(structural_zero)
]

ddd[
  ,
  baseline_depth_available :=
    as.logical(baseline_depth_available)
]

ddd[
  ,
  structural_zero :=
    as.logical(structural_zero)
]

# Main estimation samples.
pair_baseline <- pair_year[
  baseline_depth_available == TRUE
]

ddd_baseline <- ddd[
  baseline_depth_available == TRUE
]

# Variable needed for the FTA-existence DDD model.
ddd_baseline[
  ,
  fta_intermediate :=
    fta_active_l1 * intermediate_good
]


# ------------------------------------------------------------
# 5. DESCRIPTIVE AUDIT OUTPUT
# ------------------------------------------------------------
pair_audit <- data.table(
  statistic = c(
    "rows_total",
    "rows_baseline",
    "rows_excluded_missing_lagged_depth",
    "structural_zero_rows_total",
    "structural_zero_share_total",
    "unique_directed_pairs",
    "unique_unordered_pairs",
    "minimum_year",
    "maximum_year",
    "total_trade_value_1000usd"
  ),
  value = c(
    nrow(pair_year),
    nrow(pair_baseline),
    nrow(pair_year) - nrow(pair_baseline),
    pair_year[structural_zero == TRUE, .N],
    pair_year[, mean(structural_zero)],
    pair_year[, uniqueN(directed_pair_id)],
    pair_year[, uniqueN(unordered_pair_id)],
    pair_year[, min(year)],
    pair_year[, max(year)],
    pair_year[, sum(trade_value_1000usd)]
  )
)

fwrite(
  pair_audit,
  file.path(
    AUDIT_DIR,
    "step9_pair_year_r_audit.csv"
  )
)

ddd_audit <- ddd[
  ,
  .(
    panel_rows = .N,
    positive_rows = sum(!structural_zero),
    zero_rows = sum(structural_zero),
    zero_share = mean(structural_zero),
    trade_value_1000usd =
      sum(trade_value_1000usd)
  ),
  by = end_use
][order(end_use)]

fwrite(
  ddd_audit,
  file.path(
    AUDIT_DIR,
    "step9_ddd_r_audit.csv"
  )
)


# ------------------------------------------------------------
# 6. PAIR-YEAR PILOT PPML
# ------------------------------------------------------------
message("Running pair-year PPML model 1 of 3: FTA existence ...")

model_pair_fta <- fixest::fepois(
  trade_value_1000usd ~
    fta_active_l1 +
    gpr_x_fta_l1
  |
    directed_pair_id +
    exporter_year_id +
    importer_year_id,
  data = pair_baseline,
  vcov = ~ unordered_pair_id,
  notes = TRUE,
  warn = TRUE
)

message("Running pair-year PPML model 2 of 3: DTA depth ...")

model_pair_depth <- fixest::fepois(
  trade_value_1000usd ~
    depth_strict_l1_10 +
    gpr_x_depth_strict_l1_10
  |
    directed_pair_id +
    exporter_year_id +
    importer_year_id,
  data = pair_baseline,
  vcov = ~ unordered_pair_id,
  notes = TRUE,
  warn = TRUE
)

message("Running pair-year PPML model 3 of 3: FTA existence + depth ...")

model_pair_both <- fixest::fepois(
  trade_value_1000usd ~
    fta_active_l1 +
    depth_strict_l1_10 +
    gpr_x_fta_l1 +
    gpr_x_depth_strict_l1_10
  |
    directed_pair_id +
    exporter_year_id +
    importer_year_id,
  data = pair_baseline,
  vcov = ~ unordered_pair_id,
  notes = TRUE,
  warn = TRUE
)


# ------------------------------------------------------------
# 7. INTERMEDIATE–CONSUMPTION DDD PILOT PPML
# ------------------------------------------------------------
message("Running DDD PPML model 1 of 2: FTA existence ...")

model_ddd_fta <- fixest::fepois(
  trade_value_1000usd ~
    fta_intermediate +
    ddd_gpr_fta_intermediate
  |
    directed_pair_year_id +
    pair_enduse_id +
    enduse_year_id,
  data = ddd_baseline,
  vcov = ~ unordered_pair_id,
  notes = TRUE,
  warn = TRUE
)

message("Running DDD PPML model 2 of 2: DTA depth ...")

model_ddd_depth <- fixest::fepois(
  trade_value_1000usd ~
    depth_intermediate +
    ddd_gpr_depth_intermediate
  |
    directed_pair_year_id +
    pair_enduse_id +
    enduse_year_id,
  data = ddd_baseline,
  vcov = ~ unordered_pair_id,
  notes = TRUE,
  warn = TRUE
)


# ------------------------------------------------------------
# 8. SAVE MODELS
# ------------------------------------------------------------
saveRDS(
  list(
    pair_fta = model_pair_fta,
    pair_depth = model_pair_depth,
    pair_both = model_pair_both,
    ddd_fta = model_ddd_fta,
    ddd_depth = model_ddd_depth
  ),
  file.path(
    MODEL_DIR,
    "step9_pilot_ppml_models.rds"
  )
)


# ------------------------------------------------------------
# 9. EXPORT REGRESSION TABLES
# ------------------------------------------------------------
coefficient_dictionary <- c(
  "fta_active_l1" =
    "FTA active, t-1",
  "depth_strict_l1_10" =
    "DTA depth, t-1 (10 provisions)",
  "gpr_x_fta_l1" =
    "GPR × FTA, t-1",
  "gpr_x_depth_strict_l1_10" =
    "GPR × DTA depth, t-1",
  "fta_intermediate" =
    "FTA × intermediate",
  "ddd_gpr_fta_intermediate" =
    "GPR × FTA × intermediate",
  "depth_intermediate" =
    "DTA depth × intermediate",
  "ddd_gpr_depth_intermediate" =
    "GPR × DTA depth × intermediate"
)

write_fixest_table(
  list(
    "FTA existence" = model_pair_fta,
    "DTA depth" = model_pair_depth,
    "FTA + depth" = model_pair_both
  ),
  file.path(
    TABLE_DIR,
    "step9_pair_year_ppml.csv"
  ),
  coefficient_dictionary
)

write_fixest_table(
  list(
    "FTA DDD" = model_ddd_fta,
    "Depth DDD" = model_ddd_depth
  ),
  file.path(
    TABLE_DIR,
    "step9_ddd_ppml.csv"
  ),
  coefficient_dictionary
)


# ------------------------------------------------------------
# 10. EXPORT MACHINE-READABLE COEFFICIENTS
# ------------------------------------------------------------
coefficient_results <- rbindlist(
  list(
    extract_fixest_coefficients(
      model_pair_fta,
      "pair_fta"
    ),
    extract_fixest_coefficients(
      model_pair_depth,
      "pair_depth"
    ),
    extract_fixest_coefficients(
      model_pair_both,
      "pair_both"
    ),
    extract_fixest_coefficients(
      model_ddd_fta,
      "ddd_fta"
    ),
    extract_fixest_coefficients(
      model_ddd_depth,
      "ddd_depth"
    )
  ),
  fill = TRUE
)

coefficient_results[
  ,
  percent_effect := 100 * (exp(estimate) - 1)
]

coefficient_results[
  ,
  ci_low := estimate - 1.96 * std_error
]

coefficient_results[
  ,
  ci_high := estimate + 1.96 * std_error
]

coefficient_results[
  ,
  percent_effect_ci_low :=
    100 * (exp(ci_low) - 1)
]

coefficient_results[
  ,
  percent_effect_ci_high :=
    100 * (exp(ci_high) - 1)
]

fwrite(
  coefficient_results,
  file.path(
    TABLE_DIR,
    "step9_pilot_coefficients.csv"
  )
)


# ------------------------------------------------------------
# 11. COEFFICIENT PLOT
# ------------------------------------------------------------
plot_terms <- c(
  "gpr_x_fta_l1",
  "gpr_x_depth_strict_l1_10",
  "ddd_gpr_fta_intermediate",
  "ddd_gpr_depth_intermediate"
)

plot_data <- coefficient_results[
  term %in% plot_terms
]

plot_data[
  ,
  term_label := factor(
    term,
    levels = plot_terms,
    labels = c(
      "GPR × FTA",
      "GPR × DTA depth",
      "GPR × FTA × intermediate",
      "GPR × DTA depth × intermediate"
    )
  )
]

coefficient_plot <- ggplot(
  plot_data,
  aes(
    x = estimate,
    y = term_label
  )
) +
  geom_vline(
    xintercept = 0,
    linetype = "dashed"
  ) +
  geom_errorbarh(
    aes(
      xmin = ci_low,
      xmax = ci_high
    ),
    height = 0.15
  ) +
  geom_point() +
  facet_wrap(
    ~ model,
    scales = "free_y"
  ) +
  labs(
    title = "Pilot PPML interaction estimates",
    x = "Poisson coefficient with 95% confidence interval",
    y = NULL,
    caption = paste(
      "Standard errors clustered by unordered country pair.",
      "These are pilot results, not the final HS2 estimates."
    )
  ) +
  theme_minimal(base_size = 11)

ggsave(
  filename = file.path(
    FIGURE_DIR,
    "step9_pilot_interaction_coefficients.png"
  ),
  plot = coefficient_plot,
  width = 11,
  height = 7,
  dpi = 300
)


# ------------------------------------------------------------
# 12. WRITE HUMAN-READABLE REPORT
# ------------------------------------------------------------
important_terms <- coefficient_results[
  term %in% c(
    "gpr_x_fta_l1",
    "gpr_x_depth_strict_l1_10",
    "ddd_gpr_fta_intermediate",
    "ddd_gpr_depth_intermediate"
  )
][order(model, term)]

report_lines <- c(
  paste(rep("=", 94), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 9 R PILOT PPML",
  paste(rep("=", 94), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. DATA CHECK",
  paste(rep("-", 94), collapse = ""),
  paste0(
    "Pair-year rows: ",
    format(nrow(pair_year), big.mark = ",")
  ),
  paste0(
    "Pair-year baseline rows: ",
    format(nrow(pair_baseline), big.mark = ",")
  ),
  paste0(
    "Excluded pair-year rows with incomplete lagged depth: ",
    format(
      nrow(pair_year) - nrow(pair_baseline),
      big.mark = ","
    )
  ),
  paste0(
    "DDD rows: ",
    format(nrow(ddd), big.mark = ",")
  ),
  paste0(
    "DDD baseline rows: ",
    format(nrow(ddd_baseline), big.mark = ",")
  ),
  "",
  "B. PILOT MODEL PURPOSE",
  paste(rep("-", 94), collapse = ""),
  paste(
    "The pair-year models test whether FTA existence and",
    "legally enforceable DTA depth condition the trade response",
    "to global geopolitical risk."
  ),
  paste(
    "The DDD models compare intermediate and consumption goods",
    "within the same directed pair-year."
  ),
  "",
  "C. IMPORTANT INTERACTION COEFFICIENTS",
  paste(rep("-", 94), collapse = "")
)

for (row_index in seq_len(nrow(important_terms))) {
  row <- important_terms[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$model,
      " | ",
      row$term,
      " | beta=",
      sprintf("%.6f", row$estimate),
      " | SE=",
      sprintf("%.6f", row$std_error),
      " | p=",
      sprintf("%.6f", row$p_value),
      " | exp(beta)-1=",
      sprintf("%.4f%%", row$percent_effect)
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "D. INFERENCE NOTE",
  paste(rep("-", 94), collapse = ""),
  paste(
    "Pilot standard errors are clustered by unordered bilateral",
    "pair, giving both trade directions the same cluster."
  ),
  paste(
    "Final inference will add sensitivity checks for common",
    "year-level shocks and the full pair–HS2 specification."
  ),
  "",
  "E. OUTPUT FILES",
  paste(rep("-", 94), collapse = ""),
  "outputs/audit/step9_r_pilot_report.txt",
  "outputs/audit/step9_pair_year_r_audit.csv",
  "outputs/audit/step9_ddd_r_audit.csv",
  "outputs/tables/step9_pair_year_ppml.csv",
  "outputs/tables/step9_ddd_ppml.csv",
  "outputs/tables/step9_pilot_coefficients.csv",
  "outputs/figures/step9_pilot_interaction_coefficients.png",
  "outputs/models/step9_pilot_ppml_models.rds",
  "",
  "F. NEXT ACTION",
  paste(rep("-", 94), collapse = ""),
  paste(
    "Send the pilot report, coefficient CSV, pair-year table,",
    "DDD table, and coefficient figure to ChatGPT."
  ),
  paste(
    "Do not run the 16.75-million-row HS2 model until these",
    "pilot estimates and any separation warnings are reviewed."
  ),
  "",
  "R SESSION INFORMATION",
  paste(rep("-", 94), collapse = ""),
  capture.output(sessionInfo())
)

writeLines(
  report_lines,
  con = file.path(
    AUDIT_DIR,
    "step9_r_pilot_report.txt"
  ),
  useBytes = TRUE
)

message("")
message("STEP 9 COMPLETED SUCCESSFULLY")
message(
  "Main report: ",
  file.path(
    AUDIT_DIR,
    "step9_r_pilot_report.txt"
  )
)

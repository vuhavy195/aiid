# ============================================================
# AIID DTA–GPR PROJECT
# STEP 10B — FULL HS2 CORE PPML
#
# Runs two core models on the compact 16.75-million-row HS2 panel:
#   1. FTA-existence model
#   2. Legally enforceable DTA-depth model
#
# Each coefficient is reported with:
#   - unordered-pair clustered standard errors
#   - unordered-pair + year two-way clustered standard errors
#
# The two models are run sequentially to reduce peak memory use.
# ============================================================


# ------------------------------------------------------------
# 0. START WITH A CLEAN R SESSION
# ------------------------------------------------------------
rm(list = ls(all.names = TRUE))
invisible(gc(full = TRUE))


# ------------------------------------------------------------
# 1. PROJECT PATHS
# ------------------------------------------------------------
PROJECT_ROOT <- "H:/AIID_DTA_GPR"

COMPACT_FILE <- file.path(
  PROJECT_ROOT,
  "data",
  "processed",
  "estimation_hs2_ppml_compact.parquet"
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

dir.create(
  AUDIT_DIR,
  recursive = TRUE,
  showWarnings = FALSE
)

dir.create(
  TABLE_DIR,
  recursive = TRUE,
  showWarnings = FALSE
)

REPORT_FILE <- file.path(
  AUDIT_DIR,
  "step10b_hs2_core_report.txt"
)

MODEL_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step10b_hs2_model_audit.csv"
)

COEFFICIENT_FILE <- file.path(
  TABLE_DIR,
  "step10b_hs2_core_coefficients.csv"
)

EXPECTED_ROWS <- 16752461L
EXPECTED_PAIR_HS2_GROUPS <- 985562L
EXPECTED_PAIR_CLUSTERS <- 12454L
EXPECTED_YEARS <- 17L
EXPECTED_HS2 <- 88L


# ------------------------------------------------------------
# 2. INSTALL AND LOAD PACKAGES
# ------------------------------------------------------------
required_packages <- c(
  "arrow",
  "data.table",
  "fixest"
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
  library(arrow)
  library(data.table)
  library(fixest)
})

setFixest_nthreads(0)


# ------------------------------------------------------------
# 3. HELPER FUNCTIONS
# ------------------------------------------------------------
stop_if_missing <- function(path) {
  if (!file.exists(path)) {
    stop(
      paste0(
        "Required file not found:\n",
        path
      ),
      call. = FALSE
    )
  }
}


extract_target_result <- function(
  model,
  model_name,
  target_term,
  vcov_spec,
  inference_name
) {
  coefficient_table <- as.data.frame(
    fixest::coeftable(
      model,
      vcov = vcov_spec
    )
  )

  coefficient_table$term <- rownames(
    coefficient_table
  )

  rownames(coefficient_table) <- NULL

  names(coefficient_table)[1:4] <- c(
    "estimate",
    "std_error",
    "z_value",
    "p_value"
  )

  target <- coefficient_table[
    coefficient_table$term == target_term,
    ,
    drop = FALSE
  ]

  if (nrow(target) != 1L) {
    stop(
      paste0(
        "Expected exactly one coefficient named '",
        target_term,
        "' in ",
        model_name,
        ", but found ",
        nrow(target),
        "."
      ),
      call. = FALSE
    )
  }

  target$model <- model_name
  target$inference <- inference_name
  target$nobs <- fixest::nobs(model)

  target$ci_low <- (
    target$estimate
    - 1.96 * target$std_error
  )

  target$ci_high <- (
    target$estimate
    + 1.96 * target$std_error
  )

  target$percent_effect <- (
    100 * (exp(target$estimate) - 1)
  )

  target$percent_effect_ci_low <- (
    100 * (exp(target$ci_low) - 1)
  )

  target$percent_effect_ci_high <- (
    100 * (exp(target$ci_high) - 1)
  )

  target[
    ,
    c(
      "model",
      "inference",
      "term",
      "estimate",
      "std_error",
      "z_value",
      "p_value",
      "ci_low",
      "ci_high",
      "percent_effect",
      "percent_effect_ci_low",
      "percent_effect_ci_high",
      "nobs"
    )
  ]
}


fit_core_model <- function(
  formula,
  data
) {
  fixest::fepois(
    formula,
    data = data,
    vcov = ~ unordered_pair_cluster_id,
    fixef.rm = "perfect_fit",
    nthreads = 0,
    lean = FALSE,
    data.save = FALSE,
    mem.clean = TRUE,
    notes = TRUE,
    warn = TRUE,
    verbose = 0
  )
}


# ------------------------------------------------------------
# 4. READ ONLY THE COLUMNS REQUIRED FOR CORE MODELS
# ------------------------------------------------------------
stop_if_missing(COMPACT_FILE)

message("Reading the compact HS2 Parquet file ...")

required_columns <- c(
  "trade_value_musd",
  "year",
  "hs2",
  "fta_active_l1",
  "depth_strict_l1_10",
  "gpr_x_fta_l1",
  "gpr_x_depth_strict_l1_10",
  "pair_hs2_fe_id",
  "exporter_year_fe_id",
  "importer_year_fe_id",
  "hs2_year_fe_id",
  "unordered_pair_cluster_id"
)

hs2_data <- as.data.table(
  arrow::read_parquet(
    COMPACT_FILE,
    col_select = all_of(required_columns),
    as_data_frame = TRUE
  )
)

# Ensure compact integer storage.
integer_columns <- c(
  "year",
  "hs2",
  "fta_active_l1",
  "pair_hs2_fe_id",
  "exporter_year_fe_id",
  "importer_year_fe_id",
  "hs2_year_fe_id",
  "unordered_pair_cluster_id"
)

for (column in integer_columns) {
  set(
    hs2_data,
    j = column,
    value = as.integer(hs2_data[[column]])
  )
}


# ------------------------------------------------------------
# 5. INPUT AUDIT
# ------------------------------------------------------------
if (nrow(hs2_data) != EXPECTED_ROWS) {
  stop(
    paste0(
      "Unexpected row count: ",
      format(nrow(hs2_data), big.mark = ","),
      ". Expected ",
      format(EXPECTED_ROWS, big.mark = ","),
      "."
    ),
    call. = FALSE
  )
}

missing_required_values <- hs2_data[
  ,
  sum(
    is.na(trade_value_musd)
    | is.na(fta_active_l1)
    | is.na(depth_strict_l1_10)
    | is.na(gpr_x_fta_l1)
    | is.na(gpr_x_depth_strict_l1_10)
    | is.na(pair_hs2_fe_id)
    | is.na(exporter_year_fe_id)
    | is.na(importer_year_fe_id)
    | is.na(hs2_year_fe_id)
    | is.na(unordered_pair_cluster_id)
  )
]

if (missing_required_values != 0L) {
  stop(
    paste0(
      "Missing required values detected: ",
      missing_required_values
    ),
    call. = FALSE
  )
}

invalid_outcomes <- hs2_data[
  trade_value_musd < 0,
  .N
]

if (invalid_outcomes != 0L) {
  stop(
    paste0(
      "Negative trade outcomes detected: ",
      invalid_outcomes
    ),
    call. = FALSE
  )
}

input_audit <- data.table(
  statistic = c(
    "rows",
    "pair_hs2_fe_groups",
    "exporter_year_fe_groups",
    "importer_year_fe_groups",
    "hs2_year_fe_groups",
    "unordered_pair_clusters",
    "years",
    "hs2_chapters",
    "zero_outcome_rows",
    "zero_outcome_share",
    "total_trade_value_musd"
  ),
  value = c(
    nrow(hs2_data),
    uniqueN(hs2_data$pair_hs2_fe_id),
    uniqueN(hs2_data$exporter_year_fe_id),
    uniqueN(hs2_data$importer_year_fe_id),
    uniqueN(hs2_data$hs2_year_fe_id),
    uniqueN(hs2_data$unordered_pair_cluster_id),
    uniqueN(hs2_data$year),
    uniqueN(hs2_data$hs2),
    hs2_data[trade_value_musd == 0, .N],
    hs2_data[, mean(trade_value_musd == 0)],
    hs2_data[, sum(trade_value_musd)]
  )
)

if (
  hs2_data[, uniqueN(pair_hs2_fe_id)]
  != EXPECTED_PAIR_HS2_GROUPS
) {
  stop(
    "Unexpected number of pair-HS2 fixed-effect groups.",
    call. = FALSE
  )
}

if (
  hs2_data[, uniqueN(unordered_pair_cluster_id)]
  != EXPECTED_PAIR_CLUSTERS
) {
  stop(
    "Unexpected number of unordered-pair clusters.",
    call. = FALSE
  )
}

if (hs2_data[, uniqueN(year)] != EXPECTED_YEARS) {
  stop(
    "Unexpected number of years.",
    call. = FALSE
  )
}

if (hs2_data[, uniqueN(hs2)] != EXPECTED_HS2) {
  stop(
    "Unexpected number of HS2 chapters.",
    call. = FALSE
  )
}

fwrite(
  input_audit,
  file.path(
    AUDIT_DIR,
    "step10b_hs2_input_audit.csv"
  )
)


# ------------------------------------------------------------
# 6. MODEL 1 — FTA EXISTENCE
# ------------------------------------------------------------
message("")
message("Running full HS2 model 1 of 2: FTA existence ...")
message(
  "This may take a long time. ",
  "Do not close RStudio."
)

fta_elapsed <- system.time({
  model_fta <- fit_core_model(
    trade_value_musd ~
      fta_active_l1 +
      gpr_x_fta_l1
    |
      pair_hs2_fe_id +
      exporter_year_fe_id +
      importer_year_fe_id +
      hs2_year_fe_id,
    data = hs2_data
  )
})

fta_results <- rbindlist(
  list(
    extract_target_result(
      model_fta,
      "hs2_fta",
      "gpr_x_fta_l1",
      ~ unordered_pair_cluster_id,
      "pair_cluster"
    ),
    extract_target_result(
      model_fta,
      "hs2_fta",
      "gpr_x_fta_l1",
      ~ unordered_pair_cluster_id + year,
      "pair_plus_year_cluster"
    )
  ),
  fill = TRUE
)

fta_model_audit <- data.table(
  model = "hs2_fta",
  input_rows = nrow(hs2_data),
  estimation_rows = fixest::nobs(model_fta),
  removed_rows = (
    nrow(hs2_data)
    - fixest::nobs(model_fta)
  ),
  elapsed_seconds = unname(
    fta_elapsed[["elapsed"]]
  )
)

rm(model_fta)
invisible(gc(full = TRUE))


# ------------------------------------------------------------
# 7. MODEL 2 — DTA DEPTH
# ------------------------------------------------------------
message("")
message("Running full HS2 model 2 of 2: DTA depth ...")
message(
  "This may take a long time. ",
  "Do not close RStudio."
)

depth_elapsed <- system.time({
  model_depth <- fit_core_model(
    trade_value_musd ~
      depth_strict_l1_10 +
      gpr_x_depth_strict_l1_10
    |
      pair_hs2_fe_id +
      exporter_year_fe_id +
      importer_year_fe_id +
      hs2_year_fe_id,
    data = hs2_data
  )
})

depth_results <- rbindlist(
  list(
    extract_target_result(
      model_depth,
      "hs2_depth",
      "gpr_x_depth_strict_l1_10",
      ~ unordered_pair_cluster_id,
      "pair_cluster"
    ),
    extract_target_result(
      model_depth,
      "hs2_depth",
      "gpr_x_depth_strict_l1_10",
      ~ unordered_pair_cluster_id + year,
      "pair_plus_year_cluster"
    )
  ),
  fill = TRUE
)

depth_model_audit <- data.table(
  model = "hs2_depth",
  input_rows = nrow(hs2_data),
  estimation_rows = fixest::nobs(model_depth),
  removed_rows = (
    nrow(hs2_data)
    - fixest::nobs(model_depth)
  ),
  elapsed_seconds = unname(
    depth_elapsed[["elapsed"]]
  )
)

rm(model_depth)
invisible(gc(full = TRUE))


# ------------------------------------------------------------
# 8. EXPORT RESULTS
# ------------------------------------------------------------
coefficient_results <- rbindlist(
  list(
    fta_results,
    depth_results
  ),
  fill = TRUE
)

model_audit <- rbindlist(
  list(
    fta_model_audit,
    depth_model_audit
  ),
  fill = TRUE
)

fwrite(
  coefficient_results,
  COEFFICIENT_FILE
)

fwrite(
  model_audit,
  MODEL_AUDIT_FILE
)


# ------------------------------------------------------------
# 9. HUMAN-READABLE REPORT
# ------------------------------------------------------------
fta_pair <- coefficient_results[
  model == "hs2_fta"
  & inference == "pair_cluster"
]

fta_two_way <- coefficient_results[
  model == "hs2_fta"
  & inference == "pair_plus_year_cluster"
]

depth_pair <- coefficient_results[
  model == "hs2_depth"
  & inference == "pair_cluster"
]

depth_two_way <- coefficient_results[
  model == "hs2_depth"
  & inference == "pair_plus_year_cluster"
]

report_lines <- c(
  paste(rep("=", 98), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 10B FULL HS2 CORE PPML",
  paste(rep("=", 98), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. INPUT PANEL",
  paste(rep("-", 98), collapse = ""),
  paste0(
    "Rows loaded: ",
    format(nrow(hs2_data), big.mark = ",")
  ),
  paste0(
    "Pair-HS2 fixed-effect groups: ",
    format(
      hs2_data[, uniqueN(pair_hs2_fe_id)],
      big.mark = ","
    )
  ),
  paste0(
    "Unordered-pair clusters: ",
    format(
      hs2_data[
        ,
        uniqueN(unordered_pair_cluster_id)
      ],
      big.mark = ","
    )
  ),
  paste0(
    "Structural-zero share: ",
    sprintf(
      "%.6f%%",
      100 * hs2_data[
        ,
        mean(trade_value_musd == 0)
      ]
    )
  ),
  "",
  "B. FIXED EFFECTS",
  paste(rep("-", 98), collapse = ""),
  "pair_hs2_fe_id",
  "exporter_year_fe_id",
  "importer_year_fe_id",
  "hs2_year_fe_id",
  "",
  "C. FTA-EXISTENCE INTERACTION",
  paste(rep("-", 98), collapse = ""),
  paste0(
    "Pair clustered: beta=",
    sprintf("%.6f", fta_pair$estimate),
    ", SE=",
    sprintf("%.6f", fta_pair$std_error),
    ", p=",
    sprintf("%.6f", fta_pair$p_value),
    ", effect=",
    sprintf("%.4f%%", fta_pair$percent_effect)
  ),
  paste0(
    "Pair + year clustered: beta=",
    sprintf("%.6f", fta_two_way$estimate),
    ", SE=",
    sprintf("%.6f", fta_two_way$std_error),
    ", p=",
    sprintf("%.6f", fta_two_way$p_value),
    ", effect=",
    sprintf("%.4f%%", fta_two_way$percent_effect)
  ),
  paste0(
    "Estimation rows: ",
    format(
      fta_model_audit$estimation_rows,
      big.mark = ","
    )
  ),
  paste0(
    "Rows removed by PPML separation/singleton handling: ",
    format(
      fta_model_audit$removed_rows,
      big.mark = ","
    )
  ),
  paste0(
    "Elapsed time: ",
    sprintf(
      "%.2f minutes",
      fta_model_audit$elapsed_seconds / 60
    )
  ),
  "",
  "D. DTA-DEPTH INTERACTION",
  paste(rep("-", 98), collapse = ""),
  paste0(
    "Pair clustered: beta=",
    sprintf("%.6f", depth_pair$estimate),
    ", SE=",
    sprintf("%.6f", depth_pair$std_error),
    ", p=",
    sprintf("%.6f", depth_pair$p_value),
    ", effect=",
    sprintf("%.4f%%", depth_pair$percent_effect)
  ),
  paste0(
    "Pair + year clustered: beta=",
    sprintf("%.6f", depth_two_way$estimate),
    ", SE=",
    sprintf("%.6f", depth_two_way$std_error),
    ", p=",
    sprintf("%.6f", depth_two_way$p_value),
    ", effect=",
    sprintf("%.4f%%", depth_two_way$percent_effect)
  ),
  paste0(
    "Estimation rows: ",
    format(
      depth_model_audit$estimation_rows,
      big.mark = ","
    )
  ),
  paste0(
    "Rows removed by PPML separation/singleton handling: ",
    format(
      depth_model_audit$removed_rows,
      big.mark = ","
    )
  ),
  paste0(
    "Elapsed time: ",
    sprintf(
      "%.2f minutes",
      depth_model_audit$elapsed_seconds / 60
    )
  ),
  "",
  "E. INTERPRETATION SCALE",
  paste(rep("-", 98), collapse = ""),
  paste(
    "The FTA interaction compares FTA and non-FTA pairs",
    "when global GPR rises by one historical standard deviation."
  ),
  paste(
    "The depth interaction is for one historical standard",
    "deviation higher GPR and ten additional legally",
    "enforceable DTA policy areas."
  ),
  "",
  "F. OUTPUT FILES",
  paste(rep("-", 98), collapse = ""),
  "outputs/audit/step10b_hs2_core_report.txt",
  "outputs/audit/step10b_hs2_input_audit.csv",
  "outputs/audit/step10b_hs2_model_audit.csv",
  "outputs/tables/step10b_hs2_core_coefficients.csv",
  "",
  "G. NEXT ACTION",
  paste(rep("-", 98), collapse = ""),
  paste(
    "Send the report, coefficient CSV and model-audit CSV",
    "to ChatGPT before running alternative GPR measures or",
    "product-level heterogeneity models."
  ),
  "",
  "R SESSION INFORMATION",
  paste(rep("-", 98), collapse = ""),
  capture.output(sessionInfo())
)

writeLines(
  report_lines,
  REPORT_FILE,
  useBytes = TRUE
)

message("")
message("STEP 10B COMPLETED SUCCESSFULLY")
message("Main report: ", REPORT_FILE)

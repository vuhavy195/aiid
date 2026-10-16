# ============================================================
# AIID DTA–GPR PROJECT
# STEP 13B — HS2 TRADE-LINK SURVIVAL LPM
#
# Outcome:
#   survive_t = 1 if a positive pair-HS2 trade link in t-1
#                 remains positive in t
#             = 0 if that link disappears in t
#
# Core design:
#   - pair-HS2 fixed effects
#   - exporter-year fixed effects
#   - importer-year fixed effects
#   - HS2-year fixed effects
#   - unordered-pair clustered inference
#   - pair + year clustered sensitivity
#
# Five sequential models:
#   1. FTA interaction, no lagged-size control
#   2. FTA interaction, with lagged-size control
#   3. DTA-depth interaction, no lagged-size control
#   4. DTA-depth interaction, with lagged-size control
#   5. Joint FTA + depth, with lagged-size control
#
# Coefficients are linear-probability effects. Multiplying an
# interaction coefficient by 100 gives percentage-point change
# in the probability that an at-risk trade link survives.
# ============================================================


# ------------------------------------------------------------
# 0. CLEAN SESSION
# ------------------------------------------------------------
rm(list = ls(all.names = TRUE))
invisible(gc(full = TRUE))


# ------------------------------------------------------------
# 1. PROJECT PATHS
# ------------------------------------------------------------
PROJECT_ROOT <- "H:/AIID_DTA_GPR"

SURVIVAL_FILE <- file.path(
  PROJECT_ROOT,
  "data",
  "processed",
  "estimation_hs2_trade_link_survival.parquet"
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

dir.create(AUDIT_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(TABLE_DIR, recursive = TRUE, showWarnings = FALSE)

REPORT_FILE <- file.path(
  AUDIT_DIR,
  "step13b_hs2_survival_report.txt"
)

INPUT_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step13b_hs2_survival_input_audit.csv"
)

MODEL_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step13b_hs2_survival_model_audit.csv"
)

TARGET_FILE <- file.path(
  TABLE_DIR,
  "step13b_hs2_survival_interactions.csv"
)

ALL_COEFFICIENT_FILE <- file.path(
  TABLE_DIR,
  "step13b_hs2_survival_all_coefficients.csv"
)

EXPECTED_ROWS <- 8219579L
EXPECTED_PAIR_HS2_GROUPS <- 967746L
EXPECTED_PAIR_CLUSTERS <- 12436L
EXPECTED_YEARS <- 16L
EXPECTED_MIN_YEAR <- 2008L
EXPECTED_MAX_YEAR <- 2023L


# ------------------------------------------------------------
# 2. PACKAGES
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
# 3. HELPERS
# ------------------------------------------------------------
stop_if_missing <- function(path) {
  if (!file.exists(path)) {
    stop(
      paste0("Required file not found:\n", path),
      call. = FALSE
    )
  }
}


extract_coefficient_table <- function(
  model,
  model_name,
  inference_name,
  vcov_spec,
  mean_survival
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
    "t_value",
    "p_value"
  )

  coefficient_table$model <- model_name
  coefficient_table$inference <- inference_name
  coefficient_table$nobs <- stats::nobs(model)

  coefficient_table$ci_low <- (
    coefficient_table$estimate
    - 1.96 * coefficient_table$std_error
  )

  coefficient_table$ci_high <- (
    coefficient_table$estimate
    + 1.96 * coefficient_table$std_error
  )

  coefficient_table$effect_percentage_points <- (
    100 * coefficient_table$estimate
  )

  coefficient_table$ci_low_percentage_points <- (
    100 * coefficient_table$ci_low
  )

  coefficient_table$ci_high_percentage_points <- (
    100 * coefficient_table$ci_high
  )

  coefficient_table$effect_relative_to_mean_pct <- (
    100
    * coefficient_table$estimate
    / mean_survival
  )

  coefficient_table[
    ,
    c(
      "model",
      "inference",
      "term",
      "estimate",
      "std_error",
      "t_value",
      "p_value",
      "ci_low",
      "ci_high",
      "effect_percentage_points",
      "ci_low_percentage_points",
      "ci_high_percentage_points",
      "effect_relative_to_mean_pct",
      "nobs"
    )
  ]
}


fit_survival_model <- function(
  formula,
  data
) {
  fixest::feols(
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


run_model <- function(
  model_name,
  formula,
  target_terms,
  data,
  mean_survival
) {
  message("")
  message("Running survival model: ", model_name)

  elapsed <- system.time({
    model <- fit_survival_model(
      formula = formula,
      data = data
    )
  })

  pair_table <- extract_coefficient_table(
    model = model,
    model_name = model_name,
    inference_name = "pair_cluster",
    vcov_spec = ~ unordered_pair_cluster_id,
    mean_survival = mean_survival
  )

  two_way_table <- extract_coefficient_table(
    model = model,
    model_name = model_name,
    inference_name = "pair_plus_year_cluster",
    vcov_spec = ~ unordered_pair_cluster_id + year,
    mean_survival = mean_survival
  )

  all_coefficients <- rbindlist(
    list(
      pair_table,
      two_way_table
    ),
    fill = TRUE
  )

  target_results <- all_coefficients[
    term %in% target_terms
  ]

  expected_target_rows <- (
    length(target_terms) * 2L
  )

  if (nrow(target_results) != expected_target_rows) {
    stop(
      paste0(
        "Unexpected number of target coefficients in ",
        model_name,
        ": found ",
        nrow(target_results),
        ", expected ",
        expected_target_rows,
        "."
      ),
      call. = FALSE
    )
  }

  audit <- data.table(
    model = model_name,
    input_rows = nrow(data),
    estimation_rows = stats::nobs(model),
    removed_rows = (
      nrow(data)
      - stats::nobs(model)
    ),
    elapsed_seconds = unname(
      elapsed[["elapsed"]]
    )
  )

  rm(model)
  invisible(gc(full = TRUE))

  list(
    targets = target_results,
    all_coefficients = all_coefficients,
    audit = audit
  )
}


# ------------------------------------------------------------
# 4. READ DATA
# ------------------------------------------------------------
stop_if_missing(SURVIVAL_FILE)

message("Reading HS2 trade-link survival panel ...")

required_columns <- c(
  "survive_t",
  "exit_t",
  "year",
  "hs2",
  "trade_value_l1_musd",
  "log1p_trade_value_l1_musd",
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

survival_data <- as.data.table(
  arrow::read_parquet(
    SURVIVAL_FILE,
    col_select = all_of(required_columns),
    as_data_frame = TRUE
  )
)

integer_columns <- c(
  "survive_t",
  "exit_t",
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
    survival_data,
    j = column,
    value = as.integer(
      survival_data[[column]]
    )
  )
}


# ------------------------------------------------------------
# 5. INPUT AUDIT
# ------------------------------------------------------------
if (nrow(survival_data) != EXPECTED_ROWS) {
  stop(
    paste0(
      "Unexpected row count: ",
      format(nrow(survival_data), big.mark = ",")
    ),
    call. = FALSE
  )
}

if (
  survival_data[
    ,
    uniqueN(pair_hs2_fe_id)
  ] != EXPECTED_PAIR_HS2_GROUPS
) {
  stop(
    "Unexpected number of pair-HS2 groups.",
    call. = FALSE
  )
}

if (
  survival_data[
    ,
    uniqueN(unordered_pair_cluster_id)
  ] != EXPECTED_PAIR_CLUSTERS
) {
  stop(
    "Unexpected number of unordered-pair clusters.",
    call. = FALSE
  )
}

if (
  survival_data[
    ,
    uniqueN(year)
  ] != EXPECTED_YEARS
) {
  stop(
    "Unexpected number of years.",
    call. = FALSE
  )
}

if (
  survival_data[, min(year)] != EXPECTED_MIN_YEAR
  || survival_data[, max(year)] != EXPECTED_MAX_YEAR
) {
  stop(
    "Unexpected survival-panel year range.",
    call. = FALSE
  )
}

if (
  survival_data[
    ,
    anyNA(.SD),
    .SDcols = required_columns
  ]
) {
  stop(
    "Missing values detected in required variables.",
    call. = FALSE
  )
}

if (
  survival_data[
    ,
    any(!survive_t %in% c(0L, 1L))
  ]
  || survival_data[
    ,
    any(!exit_t %in% c(0L, 1L))
  ]
  || survival_data[
    ,
    any(survive_t + exit_t != 1L)
  ]
) {
  stop(
    "Invalid binary survival coding detected.",
    call. = FALSE
  )
}

mean_survival <- survival_data[
  ,
  mean(survive_t)
]

input_audit <- data.table(
  statistic = c(
    "rows",
    "mean_survival",
    "mean_exit",
    "pair_hs2_fe_groups",
    "exporter_year_fe_groups",
    "importer_year_fe_groups",
    "hs2_year_fe_groups",
    "unordered_pair_clusters",
    "years",
    "minimum_year",
    "maximum_year",
    "mean_log1p_lagged_trade_musd"
  ),
  value = c(
    nrow(survival_data),
    mean_survival,
    survival_data[, mean(exit_t)],
    survival_data[, uniqueN(pair_hs2_fe_id)],
    survival_data[, uniqueN(exporter_year_fe_id)],
    survival_data[, uniqueN(importer_year_fe_id)],
    survival_data[, uniqueN(hs2_year_fe_id)],
    survival_data[
      ,
      uniqueN(unordered_pair_cluster_id)
    ],
    survival_data[, uniqueN(year)],
    survival_data[, min(year)],
    survival_data[, max(year)],
    survival_data[
      ,
      mean(log1p_trade_value_l1_musd)
    ]
  )
)

fwrite(
  input_audit,
  INPUT_AUDIT_FILE
)


# ------------------------------------------------------------
# 6. MODEL SPECIFICATIONS
# ------------------------------------------------------------
model_specs <- list(
  list(
    name = "fta_no_size",
    formula =
      survive_t ~
        fta_active_l1 +
        gpr_x_fta_l1
      |
        pair_hs2_fe_id +
        exporter_year_fe_id +
        importer_year_fe_id +
        hs2_year_fe_id,
    targets = c(
      "gpr_x_fta_l1"
    )
  ),
  list(
    name = "fta_size_adjusted",
    formula =
      survive_t ~
        log1p_trade_value_l1_musd +
        fta_active_l1 +
        gpr_x_fta_l1
      |
        pair_hs2_fe_id +
        exporter_year_fe_id +
        importer_year_fe_id +
        hs2_year_fe_id,
    targets = c(
      "gpr_x_fta_l1"
    )
  ),
  list(
    name = "depth_no_size",
    formula =
      survive_t ~
        depth_strict_l1_10 +
        gpr_x_depth_strict_l1_10
      |
        pair_hs2_fe_id +
        exporter_year_fe_id +
        importer_year_fe_id +
        hs2_year_fe_id,
    targets = c(
      "gpr_x_depth_strict_l1_10"
    )
  ),
  list(
    name = "depth_size_adjusted",
    formula =
      survive_t ~
        log1p_trade_value_l1_musd +
        depth_strict_l1_10 +
        gpr_x_depth_strict_l1_10
      |
        pair_hs2_fe_id +
        exporter_year_fe_id +
        importer_year_fe_id +
        hs2_year_fe_id,
    targets = c(
      "gpr_x_depth_strict_l1_10"
    )
  ),
  list(
    name = "joint_size_adjusted",
    formula =
      survive_t ~
        log1p_trade_value_l1_musd +
        fta_active_l1 +
        depth_strict_l1_10 +
        gpr_x_fta_l1 +
        gpr_x_depth_strict_l1_10
      |
        pair_hs2_fe_id +
        exporter_year_fe_id +
        importer_year_fe_id +
        hs2_year_fe_id,
    targets = c(
      "gpr_x_fta_l1",
      "gpr_x_depth_strict_l1_10"
    )
  )
)


# ------------------------------------------------------------
# 7. RUN MODELS SEQUENTIALLY
# ------------------------------------------------------------
target_results_list <- list()
all_coefficients_list <- list()
model_audit_list <- list()

for (model_index in seq_along(model_specs)) {
  specification <- model_specs[[model_index]]

  fitted <- run_model(
    model_name = specification$name,
    formula = specification$formula,
    target_terms = specification$targets,
    data = survival_data,
    mean_survival = mean_survival
  )

  target_results_list[[length(target_results_list) + 1L]] <-
    fitted$targets

  all_coefficients_list[[length(all_coefficients_list) + 1L]] <-
    fitted$all_coefficients

  model_audit_list[[length(model_audit_list) + 1L]] <-
    fitted$audit

  rm(fitted)
  invisible(gc(full = TRUE))
}


# ------------------------------------------------------------
# 8. EXPORT
# ------------------------------------------------------------
target_results <- rbindlist(
  target_results_list,
  fill = TRUE
)

all_coefficients <- rbindlist(
  all_coefficients_list,
  fill = TRUE
)

model_audit <- rbindlist(
  model_audit_list,
  fill = TRUE
)

fwrite(
  target_results,
  TARGET_FILE
)

fwrite(
  all_coefficients,
  ALL_COEFFICIENT_FILE
)

fwrite(
  model_audit,
  MODEL_AUDIT_FILE
)


# ------------------------------------------------------------
# 9. REPORT
# ------------------------------------------------------------
pair_results <- target_results[
  inference == "pair_cluster"
]

two_way_results <- target_results[
  inference == "pair_plus_year_cluster"
]

get_result <- function(
  data,
  model_name,
  term_name
) {
  result <- data[
    model == model_name
    & term == term_name
  ]

  if (nrow(result) != 1L) {
    stop(
      paste0(
        "Could not retrieve one result for ",
        model_name,
        " / ",
        term_name,
        "."
      ),
      call. = FALSE
    )
  }

  result
}

fta_size_pair <- get_result(
  pair_results,
  "fta_size_adjusted",
  "gpr_x_fta_l1"
)

fta_size_two_way <- get_result(
  two_way_results,
  "fta_size_adjusted",
  "gpr_x_fta_l1"
)

depth_size_pair <- get_result(
  pair_results,
  "depth_size_adjusted",
  "gpr_x_depth_strict_l1_10"
)

depth_size_two_way <- get_result(
  two_way_results,
  "depth_size_adjusted",
  "gpr_x_depth_strict_l1_10"
)

joint_fta_pair <- get_result(
  pair_results,
  "joint_size_adjusted",
  "gpr_x_fta_l1"
)

joint_depth_pair <- get_result(
  pair_results,
  "joint_size_adjusted",
  "gpr_x_depth_strict_l1_10"
)

report_lines <- c(
  paste(rep("=", 104), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 13B HS2 TRADE-LINK SURVIVAL LPM",
  paste(rep("=", 104), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. OUTCOME AND SAMPLE",
  paste(rep("-", 104), collapse = ""),
  paste0(
    "At-risk link-year rows: ",
    format(nrow(survival_data), big.mark = ",")
  ),
  paste0(
    "Mean survival probability: ",
    sprintf("%.6f%%", 100 * mean_survival)
  ),
  paste0(
    "Pair-HS2 fixed-effect groups: ",
    format(
      survival_data[, uniqueN(pair_hs2_fe_id)],
      big.mark = ","
    )
  ),
  paste0(
    "Unordered-pair clusters: ",
    format(
      survival_data[
        ,
        uniqueN(unordered_pair_cluster_id)
      ],
      big.mark = ","
    )
  ),
  "",
  "B. PRIMARY SIZE-ADJUSTED RESULTS",
  paste(rep("-", 104), collapse = ""),
  paste0(
    "GPR × FTA, pair clustered: beta=",
    sprintf("%.6f", fta_size_pair$estimate),
    ", effect=",
    sprintf(
      "%.4f percentage points",
      fta_size_pair$effect_percentage_points
    ),
    ", SE=",
    sprintf("%.6f", fta_size_pair$std_error),
    ", p=",
    sprintf("%.6f", fta_size_pair$p_value)
  ),
  paste0(
    "GPR × FTA, pair + year clustered: beta=",
    sprintf("%.6f", fta_size_two_way$estimate),
    ", effect=",
    sprintf(
      "%.4f percentage points",
      fta_size_two_way$effect_percentage_points
    ),
    ", SE=",
    sprintf("%.6f", fta_size_two_way$std_error),
    ", p=",
    sprintf("%.6f", fta_size_two_way$p_value)
  ),
  paste0(
    "GPR × depth, pair clustered: beta=",
    sprintf("%.6f", depth_size_pair$estimate),
    ", effect=",
    sprintf(
      "%.4f percentage points",
      depth_size_pair$effect_percentage_points
    ),
    ", SE=",
    sprintf("%.6f", depth_size_pair$std_error),
    ", p=",
    sprintf("%.6f", depth_size_pair$p_value)
  ),
  paste0(
    "GPR × depth, pair + year clustered: beta=",
    sprintf("%.6f", depth_size_two_way$estimate),
    ", effect=",
    sprintf(
      "%.4f percentage points",
      depth_size_two_way$effect_percentage_points
    ),
    ", SE=",
    sprintf("%.6f", depth_size_two_way$std_error),
    ", p=",
    sprintf("%.6f", depth_size_two_way$p_value)
  ),
  "",
  "C. JOINT SIZE-ADJUSTED MODEL — PAIR CLUSTERED",
  paste(rep("-", 104), collapse = ""),
  paste0(
    "GPR × FTA: beta=",
    sprintf("%.6f", joint_fta_pair$estimate),
    ", effect=",
    sprintf(
      "%.4f percentage points",
      joint_fta_pair$effect_percentage_points
    ),
    ", p=",
    sprintf("%.6f", joint_fta_pair$p_value)
  ),
  paste0(
    "GPR × depth: beta=",
    sprintf("%.6f", joint_depth_pair$estimate),
    ", effect=",
    sprintf(
      "%.4f percentage points",
      joint_depth_pair$effect_percentage_points
    ),
    ", p=",
    sprintf("%.6f", joint_depth_pair$p_value)
  ),
  "",
  "D. INTERPRETATION",
  paste(rep("-", 104), collapse = ""),
  paste(
    "A positive interaction means the agreement variable",
    "raises the probability that an at-risk pair-HS2 link",
    "survives when global GPR rises by one standard deviation."
  ),
  paste(
    "A negative interaction means a higher probability of",
    "link exit under higher geopolitical risk."
  ),
  paste(
    "The depth coefficient is scaled to ten additional",
    "legally enforceable DTA policy areas."
  ),
  "",
  "E. OUTPUT FILES",
  paste(rep("-", 104), collapse = ""),
  "outputs/audit/step13b_hs2_survival_report.txt",
  "outputs/audit/step13b_hs2_survival_input_audit.csv",
  "outputs/audit/step13b_hs2_survival_model_audit.csv",
  "outputs/tables/step13b_hs2_survival_interactions.csv",
  "outputs/tables/step13b_hs2_survival_all_coefficients.csv",
  "",
  "F. NEXT ACTION",
  paste(rep("-", 104), collapse = ""),
  paste(
    "Send the report, interaction CSV and model-audit CSV",
    "to ChatGPT before running survival robustness checks."
  )
)

writeLines(
  report_lines,
  REPORT_FILE,
  useBytes = TRUE
)

message("")
message("STEP 13B COMPLETED SUCCESSFULLY")
message("Main report: ", REPORT_FILE)

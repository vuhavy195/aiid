# ============================================================
# AIID DTA–GPR PROJECT
# STEP 10C — FULL HS2 ROBUSTNESS PPML
#
# Sequentially runs:
# 1. Joint FTA + DTA-depth model
# 2. Alternative GPR measures for DTA depth
# 3. Sample sensitivity for both FTA and DTA depth
#
# Each target coefficient is reported with:
# - unordered-pair clustered standard errors
# - unordered-pair + year two-way clustered standard errors
#
# Models are deleted after extraction to limit RAM use.
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

dir.create(AUDIT_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(TABLE_DIR, recursive = TRUE, showWarnings = FALSE)

REPORT_FILE <- file.path(
  AUDIT_DIR,
  "step10c_hs2_robustness_report.txt"
)

MODEL_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step10c_hs2_robustness_model_audit.csv"
)

COEFFICIENT_FILE <- file.path(
  TABLE_DIR,
  "step10c_hs2_robustness_coefficients.csv"
)

EXPECTED_ROWS <- 16752461L


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


extract_target <- function(
  model,
  model_name,
  target_term,
  inference_name,
  vcov_spec
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
        "Expected one coefficient named ",
        target_term,
        " in ",
        model_name,
        "; found ",
        nrow(target),
        "."
      ),
      call. = FALSE
    )
  }

  target$model <- model_name
  target$inference <- inference_name
  target$nobs <- stats::nobs(model)

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


fit_model <- function(
  formula,
  data,
  subset_vector = NULL
) {
  fixest::fepois(
    formula,
    data = data,
    subset = subset_vector,
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


run_and_extract <- function(
  model_name,
  formula,
  target_terms,
  data,
  subset_vector = NULL
) {
  message("")
  message("Running: ", model_name)

  if (is.null(subset_vector)) {
    input_rows <- nrow(data)
  } else {
    input_rows <- sum(subset_vector)
  }

  elapsed <- system.time({
    model <- fit_model(
      formula = formula,
      data = data,
      subset_vector = subset_vector
    )
  })

  results <- list()

  for (target_term in target_terms) {
    results[[length(results) + 1L]] <- extract_target(
      model = model,
      model_name = model_name,
      target_term = target_term,
      inference_name = "pair_cluster",
      vcov_spec = ~ unordered_pair_cluster_id
    )

    results[[length(results) + 1L]] <- extract_target(
      model = model,
      model_name = model_name,
      target_term = target_term,
      inference_name = "pair_plus_year_cluster",
      vcov_spec = ~ unordered_pair_cluster_id + year
    )
  }

  audit <- data.table(
    model = model_name,
    input_rows = input_rows,
    estimation_rows = stats::nobs(model),
    removed_rows = input_rows - stats::nobs(model),
    elapsed_seconds = unname(
      elapsed[["elapsed"]]
    )
  )

  rm(model)
  invisible(gc(full = TRUE))

  list(
    results = rbindlist(results, fill = TRUE),
    audit = audit
  )
}


# ------------------------------------------------------------
# 4. READ COMPACT DATA
# ------------------------------------------------------------
stop_if_missing(COMPACT_FILE)

message("Reading compact HS2 data ...")

required_columns <- c(
  "trade_value_musd",
  "year",
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
  "unordered_pair_cluster_id"
)

hs2_data <- as.data.table(
  arrow::read_parquet(
    COMPACT_FILE,
    col_select = all_of(required_columns),
    as_data_frame = TRUE
  )
)

if (nrow(hs2_data) != EXPECTED_ROWS) {
  stop(
    paste0(
      "Unexpected row count: ",
      format(nrow(hs2_data), big.mark = ",")
    ),
    call. = FALSE
  )
}

integer_columns <- c(
  "year",
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

if (
  hs2_data[
    ,
    anyNA(.SD),
    .SDcols = required_columns
  ]
) {
  stop(
    "Missing values detected in required model variables.",
    call. = FALSE
  )
}


# ------------------------------------------------------------
# 5. MODEL SPECIFICATIONS
# ------------------------------------------------------------
results_list <- list()
audit_list <- list()


# 5.1 Joint FTA + depth model
joint <- run_and_extract(
  model_name = "joint_fta_depth",
  formula =
    trade_value_musd ~
      fta_active_l1 +
      depth_strict_l1_10 +
      gpr_x_fta_l1 +
      gpr_x_depth_strict_l1_10
    |
      pair_hs2_fe_id +
      exporter_year_fe_id +
      importer_year_fe_id +
      hs2_year_fe_id,
  target_terms = c(
    "gpr_x_fta_l1",
    "gpr_x_depth_strict_l1_10"
  ),
  data = hs2_data
)

results_list[[length(results_list) + 1L]] <- joint$results
audit_list[[length(audit_list) + 1L]] <- joint$audit
rm(joint)
invisible(gc(full = TRUE))


# 5.2 Alternative GPR measures for DTA depth
alternative_specs <- list(
  log_gpr = "log_gpr_x_depth_strict_l1_10",
  threat_gpr = "threat_gpr_x_depth_strict_l1_10",
  act_gpr = "act_gpr_x_depth_strict_l1_10",
  peak_gpr = "max_gpr_x_depth_strict_l1_10"
)

for (spec_name in names(alternative_specs)) {
  interaction_name <- alternative_specs[[spec_name]]

  formula_text <- paste0(
    "trade_value_musd ~ ",
    "depth_strict_l1_10 + ",
    interaction_name,
    " | pair_hs2_fe_id + ",
    "exporter_year_fe_id + ",
    "importer_year_fe_id + ",
    "hs2_year_fe_id"
  )

  fitted <- run_and_extract(
    model_name = paste0(
      "depth_",
      spec_name
    ),
    formula = as.formula(formula_text),
    target_terms = interaction_name,
    data = hs2_data
  )

  results_list[[length(results_list) + 1L]] <- fitted$results
  audit_list[[length(audit_list) + 1L]] <- fitted$audit

  rm(fitted)
  invisible(gc(full = TRUE))
}


# 5.3 Sample sensitivity: FTA and depth
sample_specs <- list(
  start_2008 = hs2_data$year >= 2008L,
  exclude_2020 = hs2_data$year != 2020L,
  exclude_2022 = hs2_data$year != 2022L
)

for (sample_name in names(sample_specs)) {
  subset_vector <- sample_specs[[sample_name]]

  fta_fit <- run_and_extract(
    model_name = paste0(
      "fta_",
      sample_name
    ),
    formula =
      trade_value_musd ~
        fta_active_l1 +
        gpr_x_fta_l1
      |
        pair_hs2_fe_id +
        exporter_year_fe_id +
        importer_year_fe_id +
        hs2_year_fe_id,
    target_terms = "gpr_x_fta_l1",
    data = hs2_data,
    subset_vector = subset_vector
  )

  results_list[[length(results_list) + 1L]] <- fta_fit$results
  audit_list[[length(audit_list) + 1L]] <- fta_fit$audit

  rm(fta_fit)
  invisible(gc(full = TRUE))

  depth_fit <- run_and_extract(
    model_name = paste0(
      "depth_",
      sample_name
    ),
    formula =
      trade_value_musd ~
        depth_strict_l1_10 +
        gpr_x_depth_strict_l1_10
      |
        pair_hs2_fe_id +
        exporter_year_fe_id +
        importer_year_fe_id +
        hs2_year_fe_id,
    target_terms = "gpr_x_depth_strict_l1_10",
    data = hs2_data,
    subset_vector = subset_vector
  )

  results_list[[length(results_list) + 1L]] <- depth_fit$results
  audit_list[[length(audit_list) + 1L]] <- depth_fit$audit

  rm(depth_fit)
  invisible(gc(full = TRUE))
}


# ------------------------------------------------------------
# 6. EXPORT
# ------------------------------------------------------------
all_results <- rbindlist(
  results_list,
  fill = TRUE
)

model_audit <- rbindlist(
  audit_list,
  fill = TRUE
)

fwrite(
  all_results,
  COEFFICIENT_FILE
)

fwrite(
  model_audit,
  MODEL_AUDIT_FILE
)


# ------------------------------------------------------------
# 7. REPORT
# ------------------------------------------------------------
pair_results <- all_results[
  inference == "pair_cluster"
]

joint_fta <- pair_results[
  model == "joint_fta_depth"
  & term == "gpr_x_fta_l1"
]

joint_depth <- pair_results[
  model == "joint_fta_depth"
  & term == "gpr_x_depth_strict_l1_10"
]

threat_result <- pair_results[
  model == "depth_threat_gpr"
]

act_result <- pair_results[
  model == "depth_act_gpr"
]

peak_result <- pair_results[
  model == "depth_peak_gpr"
]

fta_exclude_2022 <- pair_results[
  model == "fta_exclude_2022"
]

depth_exclude_2022 <- pair_results[
  model == "depth_exclude_2022"
]

report_lines <- c(
  paste(rep("=", 100), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 10C FULL HS2 ROBUSTNESS PPML",
  paste(rep("=", 100), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. JOINT FTA + DEPTH MODEL — PAIR-CLUSTERED",
  paste(rep("-", 100), collapse = ""),
  paste0(
    "GPR × FTA: beta=",
    sprintf("%.6f", joint_fta$estimate),
    ", SE=",
    sprintf("%.6f", joint_fta$std_error),
    ", p=",
    sprintf("%.6f", joint_fta$p_value),
    ", effect=",
    sprintf("%.4f%%", joint_fta$percent_effect)
  ),
  paste0(
    "GPR × depth: beta=",
    sprintf("%.6f", joint_depth$estimate),
    ", SE=",
    sprintf("%.6f", joint_depth$std_error),
    ", p=",
    sprintf("%.6f", joint_depth$p_value),
    ", effect=",
    sprintf("%.4f%%", joint_depth$percent_effect)
  ),
  "",
  "B. ALTERNATIVE GPR MEASURES — DEPTH, PAIR-CLUSTERED",
  paste(rep("-", 100), collapse = ""),
  paste0(
    "Threat component: beta=",
    sprintf("%.6f", threat_result$estimate),
    ", p=",
    sprintf("%.6f", threat_result$p_value)
  ),
  paste0(
    "Act component: beta=",
    sprintf("%.6f", act_result$estimate),
    ", p=",
    sprintf("%.6f", act_result$p_value)
  ),
  paste0(
    "Annual peak: beta=",
    sprintf("%.6f", peak_result$estimate),
    ", p=",
    sprintf("%.6f", peak_result$p_value)
  ),
  "",
  "C. EXCLUDING 2022 — PAIR-CLUSTERED",
  paste(rep("-", 100), collapse = ""),
  paste0(
    "FTA interaction: beta=",
    sprintf("%.6f", fta_exclude_2022$estimate),
    ", p=",
    sprintf("%.6f", fta_exclude_2022$p_value)
  ),
  paste0(
    "Depth interaction: beta=",
    sprintf("%.6f", depth_exclude_2022$estimate),
    ", p=",
    sprintf("%.6f", depth_exclude_2022$p_value)
  ),
  "",
  "D. OUTPUT FILES",
  paste(rep("-", 100), collapse = ""),
  "outputs/audit/step10c_hs2_robustness_report.txt",
  "outputs/audit/step10c_hs2_robustness_model_audit.csv",
  "outputs/tables/step10c_hs2_robustness_coefficients.csv",
  "",
  "E. NEXT ACTION",
  paste(rep("-", 100), collapse = ""),
  paste(
    "Send the report, coefficient CSV and model-audit CSV",
    "to ChatGPT before moving to HS2-sector heterogeneity."
  )
)

writeLines(
  report_lines,
  REPORT_FILE,
  useBytes = TRUE
)

message("")
message("STEP 10C COMPLETED SUCCESSFULLY")
message("Main report: ", REPORT_FILE)

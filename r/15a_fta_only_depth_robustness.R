# ============================================================
# AIID DTA–GPR PROJECT
# STEP 15A — FTA-ONLY DEPTH ROBUSTNESS
#
# Purpose:
# Re-estimate the DTA-depth interaction only among observations
# for which an FTA was already active in the previous year.
#
# This removes the no-agreement comparison and asks:
#   Among active FTA relationships, is greater legally
#   enforceable depth associated with a different response
#   to global geopolitical risk?
#
# Models:
# 1. Trade-value PPML
# 2. Trade-link survival LPM without lagged link size
# 3. Trade-link survival LPM with lagged link size
#
# Fixed effects:
#   pair-HS2
#   exporter-year
#   importer-year
#   HS2-year
#
# Inference:
#   unordered pair
#   unordered pair + year
# ============================================================


# ------------------------------------------------------------
# 0. CLEAN SESSION
# ------------------------------------------------------------
rm(list = ls(all.names = TRUE))
invisible(gc(full = TRUE))


# ------------------------------------------------------------
# 1. PATHS
# ------------------------------------------------------------
PROJECT_ROOT <- "H:/AIID_DTA_GPR"

TRADE_FILE <- file.path(
  PROJECT_ROOT,
  "data",
  "processed",
  "estimation_hs2_ppml_compact.parquet"
)

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
  "step15a_fta_only_depth_report.txt"
)

SAMPLE_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step15a_fta_only_sample_audit.csv"
)

MODEL_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step15a_fta_only_model_audit.csv"
)

COEFFICIENT_FILE <- file.path(
  TABLE_DIR,
  "step15a_fta_only_depth_coefficients.csv"
)


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
  outcome_type,
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
    "test_statistic",
    "p_value"
  )

  target_term <- "gpr_x_depth_strict_l1_10"

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
  target$outcome_type <- outcome_type
  target$inference <- inference_name
  target$nobs <- stats::nobs(model)

  target$ci_low <- (
    target$estimate -
      1.96 * target$std_error
  )

  target$ci_high <- (
    target$estimate +
      1.96 * target$std_error
  )

  if (outcome_type == "trade_value_ppml") {
    target$effect_scale <- "percent"
    target$effect <- (
      100 * (exp(target$estimate) - 1)
    )
    target$ci_low_effect <- (
      100 * (exp(target$ci_low) - 1)
    )
    target$ci_high_effect <- (
      100 * (exp(target$ci_high) - 1)
    )
  } else {
    target$effect_scale <- "percentage_points"
    target$effect <- 100 * target$estimate
    target$ci_low_effect <- 100 * target$ci_low
    target$ci_high_effect <- 100 * target$ci_high
  }

  target[
    ,
    c(
      "model",
      "outcome_type",
      "inference",
      "term",
      "estimate",
      "std_error",
      "test_statistic",
      "p_value",
      "ci_low",
      "ci_high",
      "effect_scale",
      "effect",
      "ci_low_effect",
      "ci_high_effect",
      "nobs"
    )
  ]
}


run_model <- function(
  model_name,
  outcome_type,
  formula,
  data,
  estimator
) {
  message("")
  message(
    "Running FTA-only model: ",
    model_name,
    " | rows=",
    format(nrow(data), big.mark = ",")
  )

  elapsed <- system.time({
    if (estimator == "ppml") {
      model <- fixest::fepois(
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
    } else if (estimator == "lpm") {
      model <- fixest::feols(
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
    } else {
      stop(
        paste0("Unknown estimator: ", estimator),
        call. = FALSE
      )
    }
  })

  results <- rbindlist(
    list(
      extract_target(
        model = model,
        model_name = model_name,
        outcome_type = outcome_type,
        inference_name = "pair_cluster",
        vcov_spec = ~ unordered_pair_cluster_id
      ),
      extract_target(
        model = model,
        model_name = model_name,
        outcome_type = outcome_type,
        inference_name = "pair_plus_year_cluster",
        vcov_spec = ~ unordered_pair_cluster_id + year
      )
    ),
    fill = TRUE
  )

  audit <- data.table(
    model = model_name,
    outcome_type = outcome_type,
    input_rows = nrow(data),
    estimation_rows = stats::nobs(model),
    removed_rows = (
      nrow(data) -
        stats::nobs(model)
    ),
    elapsed_seconds = unname(
      elapsed[["elapsed"]]
    )
  )

  rm(model)
  invisible(gc(full = TRUE))

  list(
    results = results,
    audit = audit
  )
}


# ------------------------------------------------------------
# 4. READ TRADE DATA
# ------------------------------------------------------------
stop_if_missing(TRADE_FILE)
stop_if_missing(SURVIVAL_FILE)

message("Reading compact trade-value panel ...")

trade_columns <- c(
  "trade_value_musd",
  "year",
  "fta_active_l1",
  "depth_strict_l1_10",
  "gpr_x_depth_strict_l1_10",
  "pair_hs2_fe_id",
  "exporter_year_fe_id",
  "importer_year_fe_id",
  "hs2_year_fe_id",
  "unordered_pair_cluster_id"
)

trade_data <- as.data.table(
  arrow::read_parquet(
    TRADE_FILE,
    col_select = all_of(trade_columns),
    as_data_frame = TRUE
  )
)

trade_fta <- trade_data[
  fta_active_l1 == 1
]

rm(trade_data)
invisible(gc(full = TRUE))

if (nrow(trade_fta) == 0L) {
  stop(
    "FTA-only trade sample is empty.",
    call. = FALSE
  )
}

if (
  trade_fta[
    ,
    anyNA(.SD),
    .SDcols = trade_columns
  ]
) {
  stop(
    "Missing values detected in the FTA-only trade sample.",
    call. = FALSE
  )
}


# ------------------------------------------------------------
# 5. READ SURVIVAL DATA
# ------------------------------------------------------------
message("Reading trade-link survival panel ...")

survival_columns <- c(
  "survive_t",
  "year",
  "log1p_trade_value_l1_musd",
  "fta_active_l1",
  "depth_strict_l1_10",
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
    col_select = all_of(survival_columns),
    as_data_frame = TRUE
  )
)

survival_fta <- survival_data[
  fta_active_l1 == 1
]

rm(survival_data)
invisible(gc(full = TRUE))

if (nrow(survival_fta) == 0L) {
  stop(
    "FTA-only survival sample is empty.",
    call. = FALSE
  )
}

if (
  survival_fta[
    ,
    anyNA(.SD),
    .SDcols = survival_columns
  ]
) {
  stop(
    "Missing values detected in the FTA-only survival sample.",
    call. = FALSE
  )
}


# ------------------------------------------------------------
# 6. SUPPORT AUDIT
# ------------------------------------------------------------
trade_pair_depth_changes <- trade_fta[
  ,
  .(
    depth_values = uniqueN(
      depth_strict_l1_10
    )
  ),
  by = unordered_pair_cluster_id
][
  depth_values > 1,
  .N
]

survival_pair_depth_changes <- survival_fta[
  ,
  .(
    depth_values = uniqueN(
      depth_strict_l1_10
    )
  ),
  by = unordered_pair_cluster_id
][
  depth_values > 1,
  .N
]

sample_audit <- rbindlist(
  list(
    data.table(
      panel = "trade_value",
      rows = nrow(trade_fta),
      pair_hs2_groups = trade_fta[
        ,
        uniqueN(pair_hs2_fe_id)
      ],
      unordered_pair_clusters = trade_fta[
        ,
        uniqueN(unordered_pair_cluster_id)
      ],
      years = trade_fta[, uniqueN(year)],
      mean_depth_units = trade_fta[
        ,
        mean(depth_strict_l1_10)
      ],
      median_depth_units = trade_fta[
        ,
        median(depth_strict_l1_10)
      ],
      pairs_with_depth_change =
        trade_pair_depth_changes,
      outcome_mean = trade_fta[
        ,
        mean(trade_value_musd)
      ]
    ),
    data.table(
      panel = "link_survival",
      rows = nrow(survival_fta),
      pair_hs2_groups = survival_fta[
        ,
        uniqueN(pair_hs2_fe_id)
      ],
      unordered_pair_clusters = survival_fta[
        ,
        uniqueN(unordered_pair_cluster_id)
      ],
      years = survival_fta[, uniqueN(year)],
      mean_depth_units = survival_fta[
        ,
        mean(depth_strict_l1_10)
      ],
      median_depth_units = survival_fta[
        ,
        median(depth_strict_l1_10)
      ],
      pairs_with_depth_change =
        survival_pair_depth_changes,
      outcome_mean = survival_fta[
        ,
        mean(survive_t)
      ]
    )
  ),
  fill = TRUE
)

fwrite(
  sample_audit,
  SAMPLE_AUDIT_FILE
)


# ------------------------------------------------------------
# 7. RUN THREE MODELS
# ------------------------------------------------------------
results_list <- list()
audit_list <- list()

trade_fit <- run_model(
  model_name = "fta_only_trade_ppml",
  outcome_type = "trade_value_ppml",
  formula =
    trade_value_musd ~
      depth_strict_l1_10 +
      gpr_x_depth_strict_l1_10
    |
      pair_hs2_fe_id +
      exporter_year_fe_id +
      importer_year_fe_id +
      hs2_year_fe_id,
  data = trade_fta,
  estimator = "ppml"
)

results_list[[length(results_list) + 1L]] <-
  trade_fit$results

audit_list[[length(audit_list) + 1L]] <-
  trade_fit$audit

rm(trade_fit, trade_fta)
invisible(gc(full = TRUE))

survival_no_size_fit <- run_model(
  model_name = "fta_only_survival_no_size",
  outcome_type = "survival_lpm",
  formula =
    survive_t ~
      depth_strict_l1_10 +
      gpr_x_depth_strict_l1_10
    |
      pair_hs2_fe_id +
      exporter_year_fe_id +
      importer_year_fe_id +
      hs2_year_fe_id,
  data = survival_fta,
  estimator = "lpm"
)

results_list[[length(results_list) + 1L]] <-
  survival_no_size_fit$results

audit_list[[length(audit_list) + 1L]] <-
  survival_no_size_fit$audit

rm(survival_no_size_fit)
invisible(gc(full = TRUE))

survival_size_fit <- run_model(
  model_name = "fta_only_survival_size_adjusted",
  outcome_type = "survival_lpm",
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
  data = survival_fta,
  estimator = "lpm"
)

results_list[[length(results_list) + 1L]] <-
  survival_size_fit$results

audit_list[[length(audit_list) + 1L]] <-
  survival_size_fit$audit

rm(survival_size_fit, survival_fta)
invisible(gc(full = TRUE))


# ------------------------------------------------------------
# 8. EXPORT
# ------------------------------------------------------------
results <- rbindlist(
  results_list,
  fill = TRUE
)

model_audit <- rbindlist(
  audit_list,
  fill = TRUE
)

fwrite(
  results,
  COEFFICIENT_FILE
)

fwrite(
  model_audit,
  MODEL_AUDIT_FILE
)


# ------------------------------------------------------------
# 9. REPORT
# ------------------------------------------------------------
pair_results <- results[
  inference == "pair_cluster"
]

two_way_results <- results[
  inference == "pair_plus_year_cluster"
]

report_lines <- c(
  paste(rep("=", 104), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 15A FTA-ONLY DEPTH ROBUSTNESS",
  paste(rep("=", 104), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. IDENTIFICATION QUESTION",
  paste(rep("-", 104), collapse = ""),
  paste(
    "The sample contains only observations with an active",
    "FTA in the previous year. The interaction therefore",
    "compares shallower and deeper active agreements rather",
    "than agreement and non-agreement observations."
  ),
  "",
  "B. PAIR-CLUSTERED RESULTS",
  paste(rep("-", 104), collapse = "")
)

for (row_index in seq_len(nrow(pair_results))) {
  row <- pair_results[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$model,
      ": beta=",
      sprintf("%.6f", row$estimate),
      ", effect=",
      sprintf("%.4f", row$effect),
      " ",
      row$effect_scale,
      ", SE=",
      sprintf("%.6f", row$std_error),
      ", p=",
      sprintf("%.6f", row$p_value)
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "C. PAIR + YEAR CLUSTERED RESULTS",
  paste(rep("-", 104), collapse = "")
)

for (row_index in seq_len(nrow(two_way_results))) {
  row <- two_way_results[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$model,
      ": beta=",
      sprintf("%.6f", row$estimate),
      ", effect=",
      sprintf("%.4f", row$effect),
      " ",
      row$effect_scale,
      ", SE=",
      sprintf("%.6f", row$std_error),
      ", p=",
      sprintf("%.6f", row$p_value)
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "D. OUTPUT FILES",
  paste(rep("-", 104), collapse = ""),
  "outputs/audit/step15a_fta_only_depth_report.txt",
  "outputs/audit/step15a_fta_only_sample_audit.csv",
  "outputs/audit/step15a_fta_only_model_audit.csv",
  "outputs/tables/step15a_fta_only_depth_coefficients.csv",
  "",
  "E. NEXT ACTION",
  paste(rep("-", 104), collapse = ""),
  paste(
    "Send the report, sample-audit CSV, model-audit CSV",
    "and coefficient CSV to ChatGPT."
  )
)

writeLines(
  report_lines,
  REPORT_FILE,
  useBytes = TRUE
)

message("")
message("STEP 15A COMPLETED SUCCESSFULLY")
message("Main report: ", REPORT_FILE)

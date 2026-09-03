# ============================================================
# AIID DTA–GPR PROJECT
# STEP 15C — COUNTRY-SPECIFIC PAIR-GPR ROBUSTNESS
#
# Final robustness exercise.
#
# Restricted sample:
#   Both trading partners must have a country-specific GPR
#   series. This leaves 44 economies and 946 unordered pairs.
#
# Shock specifications:
#   1. Global GPR benchmark, re-estimated in the same restricted
#      country-GPR sample
#   2. Average exporter–importer country GPR
#   3. Maximum exporter–importer country GPR
#   4. Average log country GPR
#
# Outcomes:
#   1. Intermediate-goods trade value, PPML
#   2. Existing trade-link survival, size-adjusted LPM
#
# All models include:
#   FTA membership
#   legally enforceable DTA depth
#   shock × FTA
#   shock × DTA depth
#
# Fixed effects:
#   pair-HS2
#   exporter-year
#   importer-year
#   HS2-year
#
# Inference:
#   unordered-pair clustering
#   unordered-pair + year clustering
#
# The restricted global-GPR benchmark is essential because the
# country-GPR sample is highly selected. It separates changes
# caused by the shock measure from changes caused by the sample.
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
  "estimation_hs2_ppml_country_gpr.parquet"
)

SURVIVAL_FILE <- file.path(
  PROJECT_ROOT,
  "data",
  "processed",
  "estimation_hs2_survival_country_gpr.parquet"
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
  "step15c_country_gpr_report.txt"
)

INPUT_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step15c_country_gpr_input_audit.csv"
)

MODEL_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step15c_country_gpr_model_audit.csv"
)

COEFFICIENT_FILE <- file.path(
  TABLE_DIR,
  "step15c_country_gpr_coefficients.csv"
)

EXPECTED_TRADE_ROWS <- 2520781L
EXPECTED_SURVIVAL_ROWS <- 1885368L
EXPECTED_PAIR_CLUSTERS <- 946L


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


extract_interactions <- function(
  model,
  model_name,
  outcome_type,
  shock_name,
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

  target_terms <- c(
    "shock_x_fta",
    "shock_x_depth"
  )

  target <- coefficient_table[
    coefficient_table$term %in% target_terms,
    ,
    drop = FALSE
  ]

  if (nrow(target) != 2L) {
    stop(
      paste0(
        "Expected two interaction coefficients in ",
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
  target$shock <- shock_name
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
      "shock",
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


fit_model <- function(
  data,
  formula,
  estimator
) {
  if (estimator == "ppml") {
    return(
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
    )
  }

  if (estimator == "lpm") {
    return(
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
    )
  }

  stop(
    paste0("Unknown estimator: ", estimator),
    call. = FALSE
  )
}


run_model <- function(
  data,
  model_name,
  outcome_type,
  shock_name,
  estimator
) {
  message("")
  message(
    "Running ",
    model_name,
    " | rows=",
    format(nrow(data), big.mark = ",")
  )

  elapsed <- system.time({
    model <- fit_model(
      data = data,
      formula =
        outcome ~
          shock_main +
          fta_active_l1 +
          depth_strict_l1_10 +
          shock_x_fta +
          shock_x_depth
        |
          pair_hs2_fe_id +
          exporter_year_fe_id +
          importer_year_fe_id +
          hs2_year_fe_id,
      estimator = estimator
    )
  })

  results <- rbindlist(
    list(
      extract_interactions(
        model = model,
        model_name = model_name,
        outcome_type = outcome_type,
        shock_name = shock_name,
        inference_name = "pair_cluster",
        vcov_spec = ~ unordered_pair_cluster_id
      ),
      extract_interactions(
        model = model,
        model_name = model_name,
        outcome_type = outcome_type,
        shock_name = shock_name,
        inference_name = "pair_plus_year_cluster",
        vcov_spec = ~ unordered_pair_cluster_id + year
      )
    ),
    fill = TRUE
  )

  audit <- data.table(
    model = model_name,
    outcome_type = outcome_type,
    shock = shock_name,
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


prepare_shock <- function(
  data,
  shock_main_column,
  shock_fta_column,
  shock_depth_column
) {
  data[
    ,
    shock_main := get(shock_main_column)
  ]

  data[
    ,
    shock_x_fta := get(shock_fta_column)
  ]

  data[
    ,
    shock_x_depth := get(shock_depth_column)
  ]

  invisible(data)
}


# ------------------------------------------------------------
# 4. READ TRADE PANEL
# ------------------------------------------------------------
stop_if_missing(TRADE_FILE)
stop_if_missing(SURVIVAL_FILE)

message("Reading country-GPR trade-value panel ...")

trade_columns <- c(
  "trade_value_musd",
  "year",
  "fta_active_l1",
  "depth_strict_l1_10",
  "gpr_x_fta_l1",
  "gpr_x_depth_strict_l1_10",
  "pair_country_gpr_average_z",
  "pair_country_gpr_maximum_z",
  "pair_country_log_gpr_average_z",
  "pair_avg_gpr_x_fta_l1",
  "pair_avg_gpr_x_depth_l1_10",
  "pair_max_gpr_x_fta_l1",
  "pair_max_gpr_x_depth_l1_10",
  "pair_log_avg_gpr_x_fta_l1",
  "pair_log_avg_gpr_x_depth_l1_10",
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

trade_data[
  ,
  global_shock_absorbed := 0
]

if (nrow(trade_data) != EXPECTED_TRADE_ROWS) {
  stop(
    paste0(
      "Unexpected country-GPR trade row count: ",
      format(nrow(trade_data), big.mark = ",")
    ),
    call. = FALSE
  )
}


# ------------------------------------------------------------
# 5. READ SURVIVAL PANEL
# ------------------------------------------------------------
message("Reading country-GPR survival panel ...")

survival_columns <- c(
  "survive_t",
  "year",
  "log1p_trade_value_l1_musd",
  "fta_active_l1",
  "depth_strict_l1_10",
  "gpr_x_fta_l1",
  "gpr_x_depth_strict_l1_10",
  "pair_country_gpr_average_z",
  "pair_country_gpr_maximum_z",
  "pair_country_log_gpr_average_z",
  "pair_avg_gpr_x_fta_l1",
  "pair_avg_gpr_x_depth_l1_10",
  "pair_max_gpr_x_fta_l1",
  "pair_max_gpr_x_depth_l1_10",
  "pair_log_avg_gpr_x_fta_l1",
  "pair_log_avg_gpr_x_depth_l1_10",
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

survival_data[
  ,
  global_shock_absorbed := 0
]

if (nrow(survival_data) != EXPECTED_SURVIVAL_ROWS) {
  stop(
    paste0(
      "Unexpected country-GPR survival row count: ",
      format(nrow(survival_data), big.mark = ",")
    ),
    call. = FALSE
  )
}


# ------------------------------------------------------------
# 6. INPUT AUDIT
# ------------------------------------------------------------
required_trade_nonmissing <- trade_columns

required_survival_nonmissing <- survival_columns

if (
  trade_data[
    ,
    anyNA(.SD),
    .SDcols = required_trade_nonmissing
  ]
) {
  stop(
    "Missing values detected in the trade robustness panel.",
    call. = FALSE
  )
}

if (
  survival_data[
    ,
    anyNA(.SD),
    .SDcols = required_survival_nonmissing
  ]
) {
  stop(
    "Missing values detected in the survival robustness panel.",
    call. = FALSE
  )
}

if (
  trade_data[
    ,
    uniqueN(unordered_pair_cluster_id)
  ] != EXPECTED_PAIR_CLUSTERS
) {
  stop(
    "Unexpected trade-panel pair-cluster count.",
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
    "Unexpected survival-panel pair-cluster count.",
    call. = FALSE
  )
}

input_audit <- rbindlist(
  list(
    data.table(
      panel = "trade_value",
      rows = nrow(trade_data),
      pair_hs2_groups = trade_data[
        ,
        uniqueN(pair_hs2_fe_id)
      ],
      unordered_pair_clusters = trade_data[
        ,
        uniqueN(unordered_pair_cluster_id)
      ],
      years = trade_data[, uniqueN(year)],
      outcome_mean = trade_data[
        ,
        mean(trade_value_musd)
      ],
      mean_depth_units = trade_data[
        fta_active_l1 == 1,
        mean(depth_strict_l1_10)
      ],
      median_depth_units = trade_data[
        fta_active_l1 == 1,
        median(depth_strict_l1_10)
      ]
    ),
    data.table(
      panel = "link_survival",
      rows = nrow(survival_data),
      pair_hs2_groups = survival_data[
        ,
        uniqueN(pair_hs2_fe_id)
      ],
      unordered_pair_clusters = survival_data[
        ,
        uniqueN(unordered_pair_cluster_id)
      ],
      years = survival_data[, uniqueN(year)],
      outcome_mean = survival_data[
        ,
        mean(survive_t)
      ],
      mean_depth_units = survival_data[
        fta_active_l1 == 1,
        mean(depth_strict_l1_10)
      ],
      median_depth_units = survival_data[
        fta_active_l1 == 1,
        median(depth_strict_l1_10)
      ]
    )
  ),
  fill = TRUE
)

fwrite(
  input_audit,
  INPUT_AUDIT_FILE
)


# ------------------------------------------------------------
# 7. SHOCK SPECIFICATIONS
# ------------------------------------------------------------
shock_specs <- list(
  list(
    name = "restricted_global_gpr",
    main = "global_shock_absorbed",
    fta = "gpr_x_fta_l1",
    depth = "gpr_x_depth_strict_l1_10"
  ),
  list(
    name = "pair_average_country_gpr",
    main = "pair_country_gpr_average_z",
    fta = "pair_avg_gpr_x_fta_l1",
    depth = "pair_avg_gpr_x_depth_l1_10"
  ),
  list(
    name = "pair_maximum_country_gpr",
    main = "pair_country_gpr_maximum_z",
    fta = "pair_max_gpr_x_fta_l1",
    depth = "pair_max_gpr_x_depth_l1_10"
  ),
  list(
    name = "pair_log_average_country_gpr",
    main = "pair_country_log_gpr_average_z",
    fta = "pair_log_avg_gpr_x_fta_l1",
    depth = "pair_log_avg_gpr_x_depth_l1_10"
  )
)

results_list <- list()
audit_list <- list()


# ------------------------------------------------------------
# 8. TRADE-VALUE MODELS
# ------------------------------------------------------------
trade_data[
  ,
  outcome := trade_value_musd
]

for (spec in shock_specs) {
  prepare_shock(
    data = trade_data,
    shock_main_column = spec$main,
    shock_fta_column = spec$fta,
    shock_depth_column = spec$depth
  )

  fitted <- run_model(
    data = trade_data,
    model_name = paste0(
      "trade_",
      spec$name
    ),
    outcome_type = "trade_value_ppml",
    shock_name = spec$name,
    estimator = "ppml"
  )

  results_list[[length(results_list) + 1L]] <-
    fitted$results

  audit_list[[length(audit_list) + 1L]] <-
    fitted$audit

  rm(fitted)
  invisible(gc(full = TRUE))
}

rm(trade_data)
invisible(gc(full = TRUE))


# ------------------------------------------------------------
# 9. LINK-SURVIVAL MODELS
# ------------------------------------------------------------
survival_data[
  ,
  outcome := survive_t
]

# The lagged-size control is included in every survival model.
# It is added as a generic regressor so that the same run_model
# helper can be used for all shock definitions.
survival_data[
  ,
  lagged_size_control :=
    log1p_trade_value_l1_musd
]

run_survival_model <- function(
  data,
  model_name,
  shock_name
) {
  message("")
  message(
    "Running ",
    model_name,
    " | rows=",
    format(nrow(data), big.mark = ",")
  )

  elapsed <- system.time({
    model <- fixest::feols(
      outcome ~
        lagged_size_control +
        shock_main +
        fta_active_l1 +
        depth_strict_l1_10 +
        shock_x_fta +
        shock_x_depth
      |
        pair_hs2_fe_id +
        exporter_year_fe_id +
        importer_year_fe_id +
        hs2_year_fe_id,
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
  })

  results <- rbindlist(
    list(
      extract_interactions(
        model = model,
        model_name = model_name,
        outcome_type = "survival_lpm",
        shock_name = shock_name,
        inference_name = "pair_cluster",
        vcov_spec = ~ unordered_pair_cluster_id
      ),
      extract_interactions(
        model = model,
        model_name = model_name,
        outcome_type = "survival_lpm",
        shock_name = shock_name,
        inference_name = "pair_plus_year_cluster",
        vcov_spec = ~ unordered_pair_cluster_id + year
      )
    ),
    fill = TRUE
  )

  audit <- data.table(
    model = model_name,
    outcome_type = "survival_lpm",
    shock = shock_name,
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

for (spec in shock_specs) {
  prepare_shock(
    data = survival_data,
    shock_main_column = spec$main,
    shock_fta_column = spec$fta,
    shock_depth_column = spec$depth
  )

  fitted <- run_survival_model(
    data = survival_data,
    model_name = paste0(
      "survival_",
      spec$name
    ),
    shock_name = spec$name
  )

  results_list[[length(results_list) + 1L]] <-
    fitted$results

  audit_list[[length(audit_list) + 1L]] <-
    fitted$audit

  rm(fitted)
  invisible(gc(full = TRUE))
}

rm(survival_data)
invisible(gc(full = TRUE))


# ------------------------------------------------------------
# 10. EXPORT
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
# 11. REPORT
# ------------------------------------------------------------
pair_results <- results[
  inference == "pair_cluster"
][order(outcome_type, shock, term)]

two_way_results <- results[
  inference == "pair_plus_year_cluster"
][order(outcome_type, shock, term)]

report_lines <- c(
  paste(rep("=", 112), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 15C COUNTRY-SPECIFIC PAIR-GPR ROBUSTNESS",
  paste(rep("=", 112), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. RESTRICTED SAMPLE",
  paste(rep("-", 112), collapse = ""),
  paste0(
    "Trade-value rows: ",
    format(EXPECTED_TRADE_ROWS, big.mark = ",")
  ),
  paste0(
    "Link-survival rows: ",
    format(EXPECTED_SURVIVAL_ROWS, big.mark = ",")
  ),
  paste0(
    "Unordered-pair clusters: ",
    EXPECTED_PAIR_CLUSTERS
  ),
  paste(
    "The global-GPR benchmark is re-estimated in exactly",
    "the same restricted sample before country-GPR results",
    "are compared."
  ),
  "",
  "B. PAIR-CLUSTERED RESULTS",
  paste(rep("-", 112), collapse = "")
)

for (row_index in seq_len(nrow(pair_results))) {
  row <- pair_results[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$outcome_type,
      " | ",
      row$shock,
      " | ",
      row$term,
      ": beta=",
      sprintf("%.6f", row$estimate),
      ", effect=",
      sprintf("%.4f", row$effect),
      " ",
      row$effect_scale,
      ", p=",
      sprintf("%.6f", row$p_value)
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "C. PAIR + YEAR CLUSTERED RESULTS",
  paste(rep("-", 112), collapse = "")
)

for (row_index in seq_len(nrow(two_way_results))) {
  row <- two_way_results[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$outcome_type,
      " | ",
      row$shock,
      " | ",
      row$term,
      ": beta=",
      sprintf("%.6f", row$estimate),
      ", effect=",
      sprintf("%.4f", row$effect),
      " ",
      row$effect_scale,
      ", p=",
      sprintf("%.6f", row$p_value)
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "D. INTERPRETATION RULE",
  paste(rep("-", 112), collapse = ""),
  paste(
    "First compare the restricted global-GPR benchmark with",
    "the full-sample baseline. Then compare country-specific",
    "pair-GPR estimates with that restricted benchmark."
  ),
  paste(
    "A change that already occurs in the restricted global",
    "benchmark reflects sample composition, not necessarily",
    "the alternative country-specific shock measure."
  ),
  paste(
    "One depth unit equals ten legally enforceable DTA",
    "policy areas."
  ),
  "",
  "E. OUTPUT FILES",
  paste(rep("-", 112), collapse = ""),
  "outputs/audit/step15c_country_gpr_report.txt",
  "outputs/audit/step15c_country_gpr_input_audit.csv",
  "outputs/audit/step15c_country_gpr_model_audit.csv",
  "outputs/tables/step15c_country_gpr_coefficients.csv",
  "",
  "F. NEXT ACTION",
  paste(rep("-", 112), collapse = ""),
  paste(
    "Send the report, input-audit CSV, model-audit CSV and",
    "coefficient CSV to ChatGPT. No additional empirical",
    "specifications should be added after this step."
  )
)

writeLines(
  report_lines,
  REPORT_FILE,
  useBytes = TRUE
)

message("")
message("STEP 15C COMPLETED SUCCESSFULLY")
message("Main report: ", REPORT_FILE)

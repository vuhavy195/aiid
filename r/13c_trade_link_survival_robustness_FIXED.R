# ============================================================
# AIID DTA–GPR PROJECT
# STEP 13C — TRADE-LINK SURVIVAL ROBUSTNESS
#
# Robustness checks for the joint size-adjusted survival LPM:
# 1. Alternative GPR measures:
#    - log annual mean
#    - threat component
#    - act component
#    - annual peak
# 2. Established-link risk sets:
#    - lagged trade >= USD 100,000
#    - lagged trade >= USD 1 million
# 3. Leave-one-year-out estimates for every year 2008–2023
#
# All models contain:
#   lagged link size
#   FTA membership
#   DTA depth
#   GPR × FTA
#   GPR × DTA depth
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
  "step13c_survival_robustness_report.txt"
)

SHOCK_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step13c_reconstructed_gpr_audit.csv"
)

MODEL_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step13c_survival_robustness_model_audit.csv"
)

COEFFICIENT_FILE <- file.path(
  TABLE_DIR,
  "step13c_survival_robustness_coefficients.csv"
)

LEAVE_ONE_YEAR_FILE <- file.path(
  TABLE_DIR,
  "step13c_survival_leave_one_year_out.csv"
)

EXPECTED_ROWS <- 8219579L
EXPECTED_YEARS <- 16L


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


extract_targets <- function(
  model,
  model_name,
  shock_name,
  sample_name,
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
    "t_value",
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
  target$shock <- shock_name
  target$sample <- sample_name
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

  target$effect_percentage_points <- (
    100 * target$estimate
  )

  target$ci_low_percentage_points <- (
    100 * target$ci_low
  )

  target$ci_high_percentage_points <- (
    100 * target$ci_high
  )

  target[
    ,
    c(
      "model",
      "shock",
      "sample",
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
      "nobs"
    )
  ]
}


run_joint_model <- function(
  data,
  model_name,
  shock_name,
  sample_name,
  subset_vector = NULL
) {
  if (is.null(subset_vector)) {
    input_rows <- nrow(data)
  } else {
    input_rows <- sum(subset_vector)
  }

  message("")
  message(
    "Running ",
    model_name,
    " | shock=",
    shock_name,
    " | sample=",
    sample_name,
    " | input rows=",
    format(input_rows, big.mark = ",")
  )

  elapsed <- system.time({
    model <- fixest::feols(
      survive_t ~
        log1p_trade_value_l1_musd +
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
  })

  results <- rbindlist(
    list(
      extract_targets(
        model = model,
        model_name = model_name,
        shock_name = shock_name,
        sample_name = sample_name,
        inference_name = "pair_cluster",
        vcov_spec = ~ unordered_pair_cluster_id
      ),
      extract_targets(
        model = model,
        model_name = model_name,
        shock_name = shock_name,
        sample_name = sample_name,
        inference_name = "pair_plus_year_cluster",
        vcov_spec = ~ unordered_pair_cluster_id + year
      )
    ),
    fill = TRUE
  )

  audit <- data.table(
    model = model_name,
    shock = shock_name,
    sample = sample_name,
    input_rows = input_rows,
    estimation_rows = stats::nobs(model),
    removed_rows = (
      input_rows -
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


reconstruct_year_shock <- function(
  data,
  interaction_column,
  output_name,
  tolerance = 1e-8
) {
  reconstruction <- data[
    abs(depth_strict_l1_10) > 1e-12,
    .(
      reconstructed_value = median(
        get(interaction_column)
        / depth_strict_l1_10,
        na.rm = TRUE
      ),
      minimum_ratio = min(
        get(interaction_column)
        / depth_strict_l1_10,
        na.rm = TRUE
      ),
      maximum_ratio = max(
        get(interaction_column)
        / depth_strict_l1_10,
        na.rm = TRUE
      ),
      source_rows = .N
    ),
    by = year
  ]

  if (nrow(reconstruction) != EXPECTED_YEARS) {
    stop(
      paste0(
        "Could not reconstruct ",
        output_name,
        " for all years."
      ),
      call. = FALSE
    )
  }

  reconstruction[
    ,
    within_year_spread :=
      maximum_ratio -
      minimum_ratio
  ]

  if (
    reconstruction[
      ,
      max(within_year_spread)
    ] > tolerance
  ) {
    stop(
      paste0(
        "Reconstructed ",
        output_name,
        " is not constant within year. ",
        "Maximum spread=",
        reconstruction[
          ,
          max(within_year_spread)
        ]
      ),
      call. = FALSE
    )
  }

  setnames(
    reconstruction,
    "reconstructed_value",
    output_name
  )

  reconstruction
}


# ------------------------------------------------------------
# 4. READ DATA
# ------------------------------------------------------------
stop_if_missing(SURVIVAL_FILE)

message("Reading HS2 survival panel ...")

required_columns <- c(
  "survive_t",
  "year",
  "trade_value_l1_musd",
  "log1p_trade_value_l1_musd",
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

survival_data <- as.data.table(
  arrow::read_parquet(
    SURVIVAL_FILE,
    col_select = all_of(required_columns),
    as_data_frame = TRUE
  )
)

integer_columns <- c(
  "survive_t",
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
    survival_data,
    j = column,
    value = as.integer(
      survival_data[[column]]
    )
  )
}

if (nrow(survival_data) != EXPECTED_ROWS) {
  stop(
    "Unexpected survival-panel row count.",
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
    "Unexpected survival-panel year count.",
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
    "Missing values detected in required columns.",
    call. = FALSE
  )
}


# ------------------------------------------------------------
# 5. RECONSTRUCT ALTERNATIVE ANNUAL GPR SERIES
#
# Existing alternative interactions equal:
# alternative_GPR_year × depth_strict_l1_10
#
# For nonzero-depth observations, dividing by depth recovers the
# annual shock. It must be identical across all pair-HS2 rows in
# the same year.
# ------------------------------------------------------------
shock_specs <- data.table(
  shock = c(
    "mean_gpr",
    "log_mean_gpr",
    "threat_gpr",
    "act_gpr",
    "peak_gpr"
  ),
  source_interaction = c(
    "gpr_x_depth_strict_l1_10",
    "log_gpr_x_depth_strict_l1_10",
    "threat_gpr_x_depth_strict_l1_10",
    "act_gpr_x_depth_strict_l1_10",
    "max_gpr_x_depth_strict_l1_10"
  ),
  annual_shock_column = c(
    "shock_mean",
    "shock_log_mean",
    "shock_threat",
    "shock_act",
    "shock_peak"
  )
)

shock_audit_list <- list()

for (row_index in seq_len(nrow(shock_specs))) {
  spec <- shock_specs[row_index]

  reconstructed <- reconstruct_year_shock(
    data = survival_data,
    interaction_column = spec$source_interaction,
    output_name = spec$annual_shock_column
  )

  reconstructed[
    ,
    shock := spec$shock
  ]

  shock_audit_list[[row_index]] <- copy(
    reconstructed
  )

  survival_data <- merge(
    survival_data,
    reconstructed[
      ,
      c(
        "year",
        spec$annual_shock_column
      ),
      with = FALSE
    ],
    by = "year",
    all.x = TRUE,
    sort = FALSE
  )
}

shock_audit <- rbindlist(
  shock_audit_list,
  fill = TRUE
)

fwrite(
  shock_audit,
  SHOCK_AUDIT_FILE
)


# ------------------------------------------------------------
# 6. RUN ALTERNATIVE-SHOCK MODELS
# ------------------------------------------------------------
results_list <- list()
audit_list <- list()

for (row_index in seq_len(nrow(shock_specs))) {
  spec <- shock_specs[row_index]

  survival_data[
    ,
    shock_x_fta :=
      get(spec$annual_shock_column)
      * fta_active_l1
  ]

  survival_data[
    ,
    shock_x_depth :=
      get(spec$annual_shock_column)
      * depth_strict_l1_10
  ]

  fitted <- run_joint_model(
    data = survival_data,
    model_name = paste0(
      "joint_",
      spec$shock
    ),
    shock_name = spec$shock,
    sample_name = "full_2008_2023"
  )

  results_list[[length(results_list) + 1L]] <-
    fitted$results

  audit_list[[length(audit_list) + 1L]] <-
    fitted$audit

  rm(fitted)
  invisible(gc(full = TRUE))
}


# ------------------------------------------------------------
# 7. ESTABLISHED-LINK RISK SETS
# ------------------------------------------------------------
survival_data[
  ,
  shock_x_fta :=
    shock_mean * fta_active_l1
]

survival_data[
  ,
  shock_x_depth :=
    shock_mean * depth_strict_l1_10
]

established_samples <- list(
  lagged_trade_at_least_100k =
    survival_data$trade_value_l1_musd >= 0.1,
  lagged_trade_at_least_1m =
    survival_data$trade_value_l1_musd >= 1.0
)

for (sample_name in names(established_samples)) {
  fitted <- run_joint_model(
    data = survival_data,
    model_name = paste0(
      "joint_mean_gpr_",
      sample_name
    ),
    shock_name = "mean_gpr",
    sample_name = sample_name,
    subset_vector = established_samples[[sample_name]]
  )

  results_list[[length(results_list) + 1L]] <-
    fitted$results

  audit_list[[length(audit_list) + 1L]] <-
    fitted$audit

  rm(fitted)
  invisible(gc(full = TRUE))
}


# ------------------------------------------------------------
# 8. LEAVE-ONE-YEAR-OUT MODELS
# ------------------------------------------------------------
leave_one_year_results <- list()

for (excluded_year in sort(unique(survival_data$year))) {
  sample_name <- paste0(
    "exclude_",
    excluded_year
  )

  fitted <- run_joint_model(
    data = survival_data,
    model_name = paste0(
      "joint_mean_gpr_",
      sample_name
    ),
    shock_name = "mean_gpr",
    sample_name = sample_name,
    subset_vector = survival_data$year != excluded_year
  )

  results_list[[length(results_list) + 1L]] <-
    fitted$results

  audit_list[[length(audit_list) + 1L]] <-
    fitted$audit

  leave_one_year_results[[length(leave_one_year_results) + 1L]] <-
    copy(fitted$results)[
      ,
      excluded_year := excluded_year
    ]

  rm(fitted)
  invisible(gc(full = TRUE))
}


# ------------------------------------------------------------
# 9. EXPORT
# ------------------------------------------------------------
all_results <- rbindlist(
  results_list,
  fill = TRUE
)

model_audit <- rbindlist(
  audit_list,
  fill = TRUE
)

leave_one_year <- rbindlist(
  leave_one_year_results,
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

fwrite(
  leave_one_year,
  LEAVE_ONE_YEAR_FILE
)


# ------------------------------------------------------------
# 10. REPORT
# ------------------------------------------------------------
alternative_pair <- all_results[
  sample == "full_2008_2023"
  & inference == "pair_cluster"
][order(shock, term)]

alternative_two_way <- all_results[
  sample == "full_2008_2023"
  & inference == "pair_plus_year_cluster"
][order(shock, term)]

established_pair <- all_results[
  sample %in% names(established_samples)
  & inference == "pair_cluster"
][order(sample, term)]

loo_pair <- leave_one_year[
  inference == "pair_cluster"
]

loo_two_way <- leave_one_year[
  inference == "pair_plus_year_cluster"
]

loo_summary <- rbindlist(
  list(
    loo_pair[
      ,
      .(
        inference = "pair_cluster",
        minimum_estimate = min(estimate),
        maximum_estimate = max(estimate),
        positive_estimates = sum(estimate > 0),
        negative_estimates = sum(estimate < 0),
        significant_5pct = sum(p_value < 0.05),
        significant_10pct = sum(p_value < 0.10)
      ),
      by = term
    ],
    loo_two_way[
      ,
      .(
        inference = "pair_plus_year_cluster",
        minimum_estimate = min(estimate),
        maximum_estimate = max(estimate),
        positive_estimates = sum(estimate > 0),
        negative_estimates = sum(estimate < 0),
        significant_5pct = sum(p_value < 0.05),
        significant_10pct = sum(p_value < 0.10)
      ),
      by = term
    ]
  ),
  fill = TRUE
)

report_lines <- c(
  paste(rep("=", 106), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 13C TRADE-LINK SURVIVAL ROBUSTNESS",
  paste(rep("=", 106), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. ALTERNATIVE GPR — PAIR CLUSTERED",
  paste(rep("-", 106), collapse = "")
)

for (row_index in seq_len(nrow(alternative_pair))) {
  row <- alternative_pair[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$shock,
      " | ",
      row$term,
      ": beta=",
      sprintf("%.6f", row$estimate),
      ", effect=",
      sprintf(
        "%.4f pp",
        row$effect_percentage_points
      ),
      ", p=",
      sprintf("%.6f", row$p_value)
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "B. ALTERNATIVE GPR — PAIR + YEAR CLUSTERED",
  paste(rep("-", 106), collapse = "")
)

for (row_index in seq_len(nrow(alternative_two_way))) {
  row <- alternative_two_way[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$shock,
      " | ",
      row$term,
      ": beta=",
      sprintf("%.6f", row$estimate),
      ", p=",
      sprintf("%.6f", row$p_value)
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "C. ESTABLISHED-LINK SAMPLES — PAIR CLUSTERED",
  paste(rep("-", 106), collapse = "")
)

for (row_index in seq_len(nrow(established_pair))) {
  row <- established_pair[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$sample,
      " | ",
      row$term,
      ": beta=",
      sprintf("%.6f", row$estimate),
      ", effect=",
      sprintf(
        "%.4f pp",
        row$effect_percentage_points
      ),
      ", p=",
      sprintf("%.6f", row$p_value)
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "D. LEAVE-ONE-YEAR-OUT SUMMARY",
  paste(rep("-", 106), collapse = "")
)

for (row_index in seq_len(nrow(loo_summary))) {
  row <- loo_summary[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$inference,
      " | ",
      row$term,
      ": range=[",
      sprintf("%.6f", row$minimum_estimate),
      ", ",
      sprintf("%.6f", row$maximum_estimate),
      "], positive=",
      row$positive_estimates,
      ", negative=",
      row$negative_estimates,
      ", p<0.05 in ",
      row$significant_5pct,
      "/16, p<0.10 in ",
      row$significant_10pct,
      "/16"
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "E. INTERPRETATION RULE",
  paste(rep("-", 106), collapse = ""),
  paste(
    "The joint FTA coefficient is the interaction effect",
    "when DTA depth equals zero. The total interaction for",
    "an FTA with D depth units is beta_FTA + D*beta_depth."
  ),
  paste(
    "One depth unit equals ten legally enforceable policy",
    "areas. Do not interpret the FTA coefficient alone as",
    "the effect for a typical deep agreement."
  ),
  "",
  "F. OUTPUT FILES",
  paste(rep("-", 106), collapse = ""),
  "outputs/audit/step13c_survival_robustness_report.txt",
  "outputs/audit/step13c_reconstructed_gpr_audit.csv",
  "outputs/audit/step13c_survival_robustness_model_audit.csv",
  "outputs/tables/step13c_survival_robustness_coefficients.csv",
  "outputs/tables/step13c_survival_leave_one_year_out.csv",
  "",
  "G. NEXT ACTION",
  paste(rep("-", 106), collapse = ""),
  paste(
    "Send the report, coefficient CSV, leave-one-year-out",
    "CSV and model-audit CSV to ChatGPT before moving to",
    "recovery dynamics."
  )
)

writeLines(
  report_lines,
  REPORT_FILE,
  useBytes = TRUE
)

message("")
message("STEP 13C COMPLETED SUCCESSFULLY")
message("Main report: ", REPORT_FILE)

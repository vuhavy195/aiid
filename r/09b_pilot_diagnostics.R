# ============================================================
# AIID DTA–GPR PROJECT
# STEP 9B — PILOT PPML DIAGNOSTICS
#
# Purpose:
# 1. Check whether scaling the trade outcome changes slopes.
# 2. Recalculate inference with pair + year two-way clustering.
# 3. Test alternative GPR measures.
# 4. Test sensitivity to 2007 coverage, COVID-2020, and the
#    extreme 2022 geopolitical-risk year.
#
# This script still does NOT run the 16.75-million-row HS2 model.
# ============================================================


# ------------------------------------------------------------
# 0. PROJECT PATHS
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

ORIGINAL_COEFFICIENT_FILE <- file.path(
  PROJECT_ROOT,
  "outputs",
  "tables",
  "step9_pilot_coefficients.csv"
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

MODEL_DIR <- file.path(
  PROJECT_ROOT,
  "outputs",
  "models"
)

dir.create(AUDIT_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(TABLE_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(MODEL_DIR, recursive = TRUE, showWarnings = FALSE)


# ------------------------------------------------------------
# 1. PACKAGES
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

if (length(missing_packages) > 0) {
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
# 2. HELPERS
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


extract_result <- function(
  model,
  model_name,
  target_term,
  vcov_spec = ~ unordered_pair_id,
  inference_name = "pair_cluster"
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

  if (nrow(target) != 1) {
    stop(
      paste0(
        "Could not find exactly one coefficient named ",
        target_term,
        " in model ",
        model_name,
        "."
      ),
      call. = FALSE
    )
  }

  target$model <- model_name
  target$inference <- inference_name
  target$nobs <- nobs(model)

  model_loglik <- suppressWarnings(
    as.numeric(logLik(model))
  )

  target$log_likelihood <- model_loglik
  target$percent_effect <- 100 * (
    exp(target$estimate) - 1
  )
  target$ci_low <- target$estimate -
    1.96 * target$std_error
  target$ci_high <- target$estimate +
    1.96 * target$std_error
  target$percent_effect_ci_low <- 100 * (
    exp(target$ci_low) - 1
  )
  target$percent_effect_ci_high <- 100 * (
    exp(target$ci_high) - 1
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
      "percent_effect",
      "ci_low",
      "ci_high",
      "percent_effect_ci_low",
      "percent_effect_ci_high",
      "nobs",
      "log_likelihood"
    )
  ]
}


fit_pair_depth <- function(
  data,
  interaction_variable,
  model_name
) {
  formula_text <- paste0(
    "trade_value_musd ~ ",
    "depth_strict_l1_10 + ",
    interaction_variable,
    " | directed_pair_id + ",
    "exporter_year_id + importer_year_id"
  )

  fixest::fepois(
    as.formula(formula_text),
    data = data,
    vcov = ~ unordered_pair_id,
    notes = TRUE,
    warn = TRUE
  )
}


fit_ddd_depth <- function(
  data,
  triple_interaction_variable,
  model_name
) {
  formula_text <- paste0(
    "trade_value_musd ~ ",
    "depth_intermediate + ",
    triple_interaction_variable,
    " | directed_pair_year_id + ",
    "pair_enduse_id + enduse_year_id"
  )

  fixest::fepois(
    as.formula(formula_text),
    data = data,
    vcov = ~ unordered_pair_id,
    notes = TRUE,
    warn = TRUE
  )
}


# ------------------------------------------------------------
# 3. LOAD AND PREPARE DATA
# ------------------------------------------------------------
stop_if_missing(
  c(
    PAIR_YEAR_FILE,
    DDD_FILE,
    ORIGINAL_COEFFICIENT_FILE
  )
)

message("Reading pair-year panel ...")

pair_year <- as.data.table(
  arrow::read_parquet(
    PAIR_YEAR_FILE,
    as_data_frame = TRUE
  )
)

message("Reading DDD panel ...")

ddd <- as.data.table(
  arrow::read_parquet(
    DDD_FILE,
    as_data_frame = TRUE
  )
)

pair_year[
  ,
  baseline_depth_available :=
    as.logical(baseline_depth_available)
]

ddd[
  ,
  baseline_depth_available :=
    as.logical(baseline_depth_available)
]

pair_year[
  ,
  unordered_pair_id :=
    make_unordered_pair_id(
      exporter_iso3,
      importer_iso3
    )
]

ddd[
  ,
  unordered_pair_id :=
    make_unordered_pair_id(
      exporter_iso3,
      importer_iso3
    )
]

# Divide thousand USD by 1,000 to obtain million USD.
# Multiplying the dependent variable by a positive constant should
# alter absorbed intercept/fixed effects, not the slope coefficients.
pair_year[
  ,
  trade_value_musd :=
    trade_value_1000usd / 1000
]

ddd[
  ,
  trade_value_musd :=
    trade_value_1000usd / 1000
]

pair_baseline <- pair_year[
  baseline_depth_available == TRUE
]

ddd_baseline <- ddd[
  baseline_depth_available == TRUE
]

# Alternative triple interactions for DDD.
ddd_baseline[
  ,
  ddd_log_gpr_depth :=
    log_gpr_x_depth_strict_l1_10 *
    intermediate_good
]

ddd_baseline[
  ,
  ddd_threat_gpr_depth :=
    threat_gpr_x_depth_strict_l1_10 *
    intermediate_good
]

ddd_baseline[
  ,
  ddd_act_gpr_depth :=
    act_gpr_x_depth_strict_l1_10 *
    intermediate_good
]

ddd_baseline[
  ,
  ddd_max_gpr_depth :=
    max_gpr_x_depth_strict_l1_10 *
    intermediate_good
]


# ------------------------------------------------------------
# 4. TREATMENT-SUPPORT DIAGNOSTICS
# ------------------------------------------------------------
treatment_support <- data.table(
  statistic = c(
    "pair_year_baseline_rows",
    "ddd_baseline_rows",
    "raw_corr_fta_depth",
    "unique_unordered_pairs",
    "unordered_pairs_with_any_fta_change",
    "unordered_pairs_with_any_depth_change",
    "years",
    "minimum_depth",
    "median_depth",
    "mean_depth",
    "maximum_depth"
  ),
  value = c(
    nrow(pair_baseline),
    nrow(ddd_baseline),
    pair_baseline[
      ,
      cor(
        fta_active_l1,
        depth_strict_l1_10,
        use = "complete.obs"
      )
    ],
    pair_baseline[
      ,
      uniqueN(unordered_pair_id)
    ],
    pair_baseline[
      ,
      .(
        changed = uniqueN(
          fta_active_l1
        ) > 1
      ),
      by = unordered_pair_id
    ][changed == TRUE, .N],
    pair_baseline[
      ,
      .(
        changed = uniqueN(
          depth_strict_l1_10
        ) > 1
      ),
      by = unordered_pair_id
    ][changed == TRUE, .N],
    pair_baseline[, uniqueN(year)],
    pair_baseline[
      ,
      min(
        depth_strict_l1_10,
        na.rm = TRUE
      )
    ],
    pair_baseline[
      ,
      median(
        depth_strict_l1_10,
        na.rm = TRUE
      )
    ],
    pair_baseline[
      ,
      mean(
        depth_strict_l1_10,
        na.rm = TRUE
      )
    ],
    pair_baseline[
      ,
      max(
        depth_strict_l1_10,
        na.rm = TRUE
      )
    ]
  )
)

fwrite(
  treatment_support,
  file.path(
    AUDIT_DIR,
    "step9b_treatment_support.csv"
  )
)


# ------------------------------------------------------------
# 5. OUTCOME-SCALING CHECK
# ------------------------------------------------------------
message("Scaling check 1/5: pair FTA model ...")

scaled_pair_fta <- fixest::fepois(
  trade_value_musd ~
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

message("Scaling check 2/5: pair depth model ...")

scaled_pair_depth <- fit_pair_depth(
  pair_baseline,
  "gpr_x_depth_strict_l1_10",
  "scaled_pair_depth"
)

message("Scaling check 3/5: pair FTA + depth model ...")

scaled_pair_both <- fixest::fepois(
  trade_value_musd ~
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

message("Scaling check 4/5: DDD FTA model ...")

ddd_baseline[
  ,
  fta_intermediate :=
    fta_active_l1 * intermediate_good
]

scaled_ddd_fta <- fixest::fepois(
  trade_value_musd ~
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

message("Scaling check 5/5: DDD depth model ...")

scaled_ddd_depth <- fit_ddd_depth(
  ddd_baseline,
  "ddd_gpr_depth_intermediate",
  "scaled_ddd_depth"
)

scaled_results <- rbindlist(
  list(
    extract_result(
      scaled_pair_fta,
      "pair_fta",
      "gpr_x_fta_l1"
    ),
    extract_result(
      scaled_pair_depth,
      "pair_depth",
      "gpr_x_depth_strict_l1_10"
    ),
    extract_result(
      scaled_pair_both,
      "pair_both_fta",
      "gpr_x_fta_l1"
    ),
    extract_result(
      scaled_pair_both,
      "pair_both_depth",
      "gpr_x_depth_strict_l1_10"
    ),
    extract_result(
      scaled_ddd_fta,
      "ddd_fta",
      "ddd_gpr_fta_intermediate"
    ),
    extract_result(
      scaled_ddd_depth,
      "ddd_depth",
      "ddd_gpr_depth_intermediate"
    )
  ),
  fill = TRUE
)

original_results <- fread(
  ORIGINAL_COEFFICIENT_FILE
)

original_key <- original_results[
  ,
  .(
    model = fifelse(
      model == "pair_both" &
        term == "gpr_x_fta_l1",
      "pair_both_fta",
      fifelse(
        model == "pair_both" &
          term ==
            "gpr_x_depth_strict_l1_10",
        "pair_both_depth",
        model
      )
    ),
    term,
    original_estimate = estimate,
    original_std_error = std_error,
    original_p_value = p_value
  )
]

scaling_comparison <- merge(
  scaled_results,
  original_key,
  by = c("model", "term"),
  all.x = TRUE
)

scaling_comparison[
  ,
  estimate_difference :=
    estimate - original_estimate
]

scaling_comparison[
  ,
  absolute_estimate_difference :=
    abs(estimate_difference)
]

fwrite(
  scaling_comparison,
  file.path(
    TABLE_DIR,
    "step9b_outcome_scaling_check.csv"
  )
)


# ------------------------------------------------------------
# 6. TWO-WAY CLUSTERING SENSITIVITY
# ------------------------------------------------------------
message("Calculating pair + year clustered standard errors ...")

vcov_sensitivity <- rbindlist(
  list(
    extract_result(
      scaled_pair_fta,
      "pair_fta",
      "gpr_x_fta_l1",
      ~ unordered_pair_id,
      "pair_cluster"
    ),
    extract_result(
      scaled_pair_fta,
      "pair_fta",
      "gpr_x_fta_l1",
      ~ unordered_pair_id + year,
      "pair_plus_year_cluster"
    ),
    extract_result(
      scaled_pair_depth,
      "pair_depth",
      "gpr_x_depth_strict_l1_10",
      ~ unordered_pair_id,
      "pair_cluster"
    ),
    extract_result(
      scaled_pair_depth,
      "pair_depth",
      "gpr_x_depth_strict_l1_10",
      ~ unordered_pair_id + year,
      "pair_plus_year_cluster"
    ),
    extract_result(
      scaled_pair_both,
      "pair_both_fta",
      "gpr_x_fta_l1",
      ~ unordered_pair_id,
      "pair_cluster"
    ),
    extract_result(
      scaled_pair_both,
      "pair_both_fta",
      "gpr_x_fta_l1",
      ~ unordered_pair_id + year,
      "pair_plus_year_cluster"
    ),
    extract_result(
      scaled_pair_both,
      "pair_both_depth",
      "gpr_x_depth_strict_l1_10",
      ~ unordered_pair_id,
      "pair_cluster"
    ),
    extract_result(
      scaled_pair_both,
      "pair_both_depth",
      "gpr_x_depth_strict_l1_10",
      ~ unordered_pair_id + year,
      "pair_plus_year_cluster"
    ),
    extract_result(
      scaled_ddd_fta,
      "ddd_fta",
      "ddd_gpr_fta_intermediate",
      ~ unordered_pair_id,
      "pair_cluster"
    ),
    extract_result(
      scaled_ddd_fta,
      "ddd_fta",
      "ddd_gpr_fta_intermediate",
      ~ unordered_pair_id + year,
      "pair_plus_year_cluster"
    ),
    extract_result(
      scaled_ddd_depth,
      "ddd_depth",
      "ddd_gpr_depth_intermediate",
      ~ unordered_pair_id,
      "pair_cluster"
    ),
    extract_result(
      scaled_ddd_depth,
      "ddd_depth",
      "ddd_gpr_depth_intermediate",
      ~ unordered_pair_id + year,
      "pair_plus_year_cluster"
    )
  ),
  fill = TRUE
)

fwrite(
  vcov_sensitivity,
  file.path(
    TABLE_DIR,
    "step9b_vcov_sensitivity.csv"
  )
)


# ------------------------------------------------------------
# 7. ALTERNATIVE GPR MEASURES
# ------------------------------------------------------------
pair_shock_specs <- data.table(
  shock = c(
    "annual_mean",
    "log_annual_mean",
    "threat_component",
    "act_component",
    "annual_peak"
  ),
  interaction = c(
    "gpr_x_depth_strict_l1_10",
    "log_gpr_x_depth_strict_l1_10",
    "threat_gpr_x_depth_strict_l1_10",
    "act_gpr_x_depth_strict_l1_10",
    "max_gpr_x_depth_strict_l1_10"
  )
)

ddd_shock_specs <- data.table(
  shock = c(
    "annual_mean",
    "log_annual_mean",
    "threat_component",
    "act_component",
    "annual_peak"
  ),
  interaction = c(
    "ddd_gpr_depth_intermediate",
    "ddd_log_gpr_depth",
    "ddd_threat_gpr_depth",
    "ddd_act_gpr_depth",
    "ddd_max_gpr_depth"
  )
)

shock_results <- list()

for (row_index in seq_len(nrow(pair_shock_specs))) {
  specification <- pair_shock_specs[row_index]

  message(
    "Pair shock sensitivity: ",
    specification$shock
  )

  model <- fit_pair_depth(
    pair_baseline,
    specification$interaction,
    paste0(
      "pair_",
      specification$shock
    )
  )

  result <- extract_result(
    model,
    paste0(
      "pair_",
      specification$shock
    ),
    specification$interaction
  )

  result$shock <- specification$shock
  result$panel <- "pair_year"

  shock_results[[length(shock_results) + 1]] <- result
}

for (row_index in seq_len(nrow(ddd_shock_specs))) {
  specification <- ddd_shock_specs[row_index]

  message(
    "DDD shock sensitivity: ",
    specification$shock
  )

  model <- fit_ddd_depth(
    ddd_baseline,
    specification$interaction,
    paste0(
      "ddd_",
      specification$shock
    )
  )

  result <- extract_result(
    model,
    paste0(
      "ddd_",
      specification$shock
    ),
    specification$interaction
  )

  result$shock <- specification$shock
  result$panel <- "ddd"

  shock_results[[length(shock_results) + 1]] <- result
}

shock_sensitivity <- rbindlist(
  shock_results,
  fill = TRUE
)

fwrite(
  shock_sensitivity,
  file.path(
    TABLE_DIR,
    "step9b_shock_sensitivity.csv"
  )
)


# ------------------------------------------------------------
# 8. SAMPLE SENSITIVITY
# ------------------------------------------------------------
sample_specs <- list(
  full_2007_2023 = function(data) data,
  start_2008 = function(data) data[year >= 2008],
  exclude_2020 = function(data) data[year != 2020],
  exclude_2022 = function(data) data[year != 2022]
)

sample_results <- list()

for (sample_name in names(sample_specs)) {
  message(
    "Sample sensitivity, pair-year: ",
    sample_name
  )

  pair_sample <- sample_specs[[sample_name]](
    pair_baseline
  )

  pair_model <- fit_pair_depth(
    pair_sample,
    "gpr_x_depth_strict_l1_10",
    paste0(
      "pair_",
      sample_name
    )
  )

  pair_result <- extract_result(
    pair_model,
    paste0(
      "pair_",
      sample_name
    ),
    "gpr_x_depth_strict_l1_10"
  )

  pair_result$sample <- sample_name
  pair_result$panel <- "pair_year"

  sample_results[[length(sample_results) + 1]] <- pair_result

  message(
    "Sample sensitivity, DDD: ",
    sample_name
  )

  ddd_sample <- sample_specs[[sample_name]](
    ddd_baseline
  )

  ddd_model <- fit_ddd_depth(
    ddd_sample,
    "ddd_gpr_depth_intermediate",
    paste0(
      "ddd_",
      sample_name
    )
  )

  ddd_result <- extract_result(
    ddd_model,
    paste0(
      "ddd_",
      sample_name
    ),
    "ddd_gpr_depth_intermediate"
  )

  ddd_result$sample <- sample_name
  ddd_result$panel <- "ddd"

  sample_results[[length(sample_results) + 1]] <- ddd_result
}

sample_sensitivity <- rbindlist(
  sample_results,
  fill = TRUE
)

fwrite(
  sample_sensitivity,
  file.path(
    TABLE_DIR,
    "step9b_sample_sensitivity.csv"
  )
)


# ------------------------------------------------------------
# 9. SAVE DIAGNOSTIC MODELS
# ------------------------------------------------------------
saveRDS(
  list(
    scaled_pair_fta = scaled_pair_fta,
    scaled_pair_depth = scaled_pair_depth,
    scaled_pair_both = scaled_pair_both,
    scaled_ddd_fta = scaled_ddd_fta,
    scaled_ddd_depth = scaled_ddd_depth
  ),
  file.path(
    MODEL_DIR,
    "step9b_scaled_pilot_models.rds"
  )
)


# ------------------------------------------------------------
# 10. REPORT
# ------------------------------------------------------------
maximum_scaling_difference <- max(
  scaling_comparison[
    ,
    absolute_estimate_difference
  ],
  na.rm = TRUE
)

pair_depth_two_way <- vcov_sensitivity[
  model == "pair_depth" &
    inference == "pair_plus_year_cluster"
]

ddd_depth_two_way <- vcov_sensitivity[
  model == "ddd_depth" &
    inference == "pair_plus_year_cluster"
]

pair_exclude_2022 <- sample_sensitivity[
  panel == "pair_year" &
    sample == "exclude_2022"
]

ddd_exclude_2022 <- sample_sensitivity[
  panel == "ddd" &
    sample == "exclude_2022"
]

report_lines <- c(
  paste(rep("=", 96), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 9B PILOT DIAGNOSTICS",
  paste(rep("=", 96), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. OUTCOME-SCALING CHECK",
  paste(rep("-", 96), collapse = ""),
  paste0(
    "Maximum absolute slope difference after converting ",
    "trade from thousand USD to million USD: ",
    sprintf("%.12f", maximum_scaling_difference)
  ),
  paste0(
    "Scaled pair-depth model log-likelihood: ",
    sprintf(
      "%.4f",
      as.numeric(logLik(scaled_pair_depth))
    )
  ),
  paste(
    "A near-zero coefficient difference confirms that",
    "outcome scaling does not change the substantive slopes."
  ),
  "",
  "B. COMMON-SHOCK INFERENCE CHECK",
  paste(rep("-", 96), collapse = ""),
  paste0(
    "Pair-depth, pair + year clustered: beta=",
    sprintf("%.6f", pair_depth_two_way$estimate),
    ", SE=",
    sprintf("%.6f", pair_depth_two_way$std_error),
    ", p=",
    sprintf("%.6f", pair_depth_two_way$p_value)
  ),
  paste0(
    "DDD-depth, pair + year clustered: beta=",
    sprintf("%.6f", ddd_depth_two_way$estimate),
    ", SE=",
    sprintf("%.6f", ddd_depth_two_way$std_error),
    ", p=",
    sprintf("%.6f", ddd_depth_two_way$p_value)
  ),
  paste(
    "Because global GPR is common across countries and only",
    "17 years are available, year-cluster sensitivity is",
    "important but should not be treated as definitive."
  ),
  "",
  "C. EXTREME-YEAR CHECK",
  paste(rep("-", 96), collapse = ""),
  paste0(
    "Pair-depth excluding 2022: beta=",
    sprintf("%.6f", pair_exclude_2022$estimate),
    ", p=",
    sprintf("%.6f", pair_exclude_2022$p_value)
  ),
  paste0(
    "DDD-depth excluding 2022: beta=",
    sprintf("%.6f", ddd_exclude_2022$estimate),
    ", p=",
    sprintf("%.6f", ddd_exclude_2022$p_value)
  ),
  "",
  "D. OUTPUT FILES",
  paste(rep("-", 96), collapse = ""),
  "outputs/audit/step9b_diagnostic_report.txt",
  "outputs/audit/step9b_treatment_support.csv",
  "outputs/tables/step9b_outcome_scaling_check.csv",
  "outputs/tables/step9b_vcov_sensitivity.csv",
  "outputs/tables/step9b_shock_sensitivity.csv",
  "outputs/tables/step9b_sample_sensitivity.csv",
  "outputs/models/step9b_scaled_pilot_models.rds",
  "",
  "E. NEXT ACTION",
  paste(rep("-", 96), collapse = ""),
  paste(
    "Send the diagnostic report and the five CSV outputs",
    "to ChatGPT before running the full HS2 PPML."
  )
)

writeLines(
  report_lines,
  file.path(
    AUDIT_DIR,
    "step9b_diagnostic_report.txt"
  ),
  useBytes = TRUE
)

message("")
message("STEP 9B COMPLETED SUCCESSFULLY")
message(
  "Main report: ",
  file.path(
    AUDIT_DIR,
    "step9b_diagnostic_report.txt"
  )
)

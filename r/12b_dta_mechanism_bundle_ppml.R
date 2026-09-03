# ============================================================
# AIID DTA–GPR PROJECT
# STEP 12B — HS2 DTA MECHANISM-BUNDLE PPML
#
# Five pre-specified DTA provision bundles:
# 1. Border coordination
# 2. Investment and production integration
# 3. Digital and knowledge governance
# 4. Services and public procurement
# 5. Environmental provisions
#
# For each bundle, estimate:
# A. Standalone model: total bundle association
# B. FTA-conditional model: incremental bundle composition
#    effect beyond simple FTA membership
#
# Do NOT put all five bundles in one regression: their pair-year
# correlations are high and would make the coefficients unstable.
#
# Each target coefficient is reported with:
# - unordered-pair clustered standard errors
# - unordered-pair + year two-way clustered standard errors
# - Benjamini-Hochberg FDR-adjusted p-values across five bundles
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

MECHANISM_FILE <- file.path(
  PROJECT_ROOT,
  "data",
  "processed",
  "estimation_hs2_ppml_mechanisms.parquet"
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
  "step12b_mechanism_bundle_report.txt"
)

MODEL_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step12b_mechanism_bundle_model_audit.csv"
)

COEFFICIENT_FILE <- file.path(
  TABLE_DIR,
  "step12b_mechanism_bundle_coefficients.csv"
)

EXPECTED_ROWS <- 16752461L
EXPECTED_CLUSTERS <- 12454L
EXPECTED_YEARS <- 17L


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
# 3. PRE-SPECIFIED BUNDLES
# ------------------------------------------------------------
bundle_lookup <- data.table(
  bundle_id = 1:5,
  bundle = c(
    "border_coordination",
    "investment_production",
    "digital_knowledge",
    "services_procurement",
    "environmental"
  ),
  bundle_label = c(
    "Border coordination",
    "Investment and production",
    "Digital and knowledge",
    "Services and procurement",
    "Environmental provisions"
  ),
  number_of_components = c(
    3L,
    4L,
    6L,
    2L,
    1L
  )
)


# ------------------------------------------------------------
# 4. HELPERS
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
  bundle_id,
  bundle,
  bundle_label,
  model_spec,
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
        model_spec,
        " model for ",
        bundle,
        "; found ",
        nrow(target),
        "."
      ),
      call. = FALSE
    )
  }

  target$bundle_id <- bundle_id
  target$bundle <- bundle
  target$bundle_label <- bundle_label
  target$model_spec <- model_spec
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

  target$percent_effect_full_bundle <- (
    100 * (exp(target$estimate) - 1)
  )

  target$percent_effect_10pp_bundle <- (
    100 * (exp(0.1 * target$estimate) - 1)
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
      "bundle_id",
      "bundle",
      "bundle_label",
      "model_spec",
      "inference",
      "term",
      "estimate",
      "std_error",
      "z_value",
      "p_value",
      "ci_low",
      "ci_high",
      "percent_effect_full_bundle",
      "percent_effect_10pp_bundle",
      "percent_effect_ci_low",
      "percent_effect_ci_high",
      "nobs"
    )
  ]
}


fit_model <- function(
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


run_bundle_model <- function(
  bundle_row,
  model_spec,
  formula,
  target_term,
  data
) {
  message("")
  message(
    "Running ",
    model_spec,
    " model for ",
    bundle_row$bundle_label,
    " ..."
  )

  elapsed <- system.time({
    model <- fit_model(
      formula = formula,
      data = data
    )
  })

  results <- rbindlist(
    list(
      extract_target(
        model = model,
        bundle_id = bundle_row$bundle_id,
        bundle = bundle_row$bundle,
        bundle_label = bundle_row$bundle_label,
        model_spec = model_spec,
        target_term = target_term,
        inference_name = "pair_cluster",
        vcov_spec = ~ unordered_pair_cluster_id
      ),
      extract_target(
        model = model,
        bundle_id = bundle_row$bundle_id,
        bundle = bundle_row$bundle,
        bundle_label = bundle_row$bundle_label,
        model_spec = model_spec,
        target_term = target_term,
        inference_name = "pair_plus_year_cluster",
        vcov_spec = ~ unordered_pair_cluster_id + year
      )
    ),
    fill = TRUE
  )

  audit <- data.table(
    bundle_id = bundle_row$bundle_id,
    bundle = bundle_row$bundle,
    bundle_label = bundle_row$bundle_label,
    model_spec = model_spec,
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
# 5. READ DATA
# ------------------------------------------------------------
stop_if_missing(MECHANISM_FILE)

message("Reading HS2 mechanism panel ...")

bundle_share_columns <- paste0(
  bundle_lookup$bundle,
  "_share_l1"
)

bundle_interaction_columns <- paste0(
  "gpr_x_",
  bundle_lookup$bundle,
  "_share_l1"
)

required_columns <- c(
  "trade_value_musd",
  "year",
  "fta_active_l1",
  "gpr_x_fta_l1",
  bundle_share_columns,
  bundle_interaction_columns,
  "pair_hs2_fe_id",
  "exporter_year_fe_id",
  "importer_year_fe_id",
  "hs2_year_fe_id",
  "unordered_pair_cluster_id"
)

mechanism_data <- as.data.table(
  arrow::read_parquet(
    MECHANISM_FILE,
    col_select = all_of(required_columns),
    as_data_frame = TRUE
  )
)

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
    mechanism_data,
    j = column,
    value = as.integer(
      mechanism_data[[column]]
    )
  )
}


# ------------------------------------------------------------
# 6. INPUT AUDIT
# ------------------------------------------------------------
if (nrow(mechanism_data) != EXPECTED_ROWS) {
  stop(
    paste0(
      "Unexpected row count: ",
      format(
        nrow(mechanism_data),
        big.mark = ","
      )
    ),
    call. = FALSE
  )
}

if (
  mechanism_data[
    ,
    uniqueN(unordered_pair_cluster_id)
  ] != EXPECTED_CLUSTERS
) {
  stop(
    "Unexpected number of unordered-pair clusters.",
    call. = FALSE
  )
}

if (
  mechanism_data[
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
  mechanism_data[
    ,
    anyNA(.SD),
    .SDcols = required_columns
  ]
) {
  stop(
    "Missing values detected in required mechanism variables.",
    call. = FALSE
  )
}


# ------------------------------------------------------------
# 7. RUN 10 SEQUENTIAL MODELS
# ------------------------------------------------------------
results_list <- list()
audit_list <- list()

for (row_index in seq_len(nrow(bundle_lookup))) {
  bundle_row <- bundle_lookup[row_index]

  share_variable <- paste0(
    bundle_row$bundle,
    "_share_l1"
  )

  interaction_variable <- paste0(
    "gpr_x_",
    bundle_row$bundle,
    "_share_l1"
  )

  standalone_formula <- as.formula(
    paste0(
      "trade_value_musd ~ ",
      share_variable,
      " + ",
      interaction_variable,
      " | pair_hs2_fe_id + ",
      "exporter_year_fe_id + ",
      "importer_year_fe_id + ",
      "hs2_year_fe_id"
    )
  )

  standalone_fit <- run_bundle_model(
    bundle_row = bundle_row,
    model_spec = "standalone_bundle",
    formula = standalone_formula,
    target_term = interaction_variable,
    data = mechanism_data
  )

  results_list[[length(results_list) + 1L]] <-
    standalone_fit$results

  audit_list[[length(audit_list) + 1L]] <-
    standalone_fit$audit

  rm(standalone_fit)
  invisible(gc(full = TRUE))

  conditional_formula <- as.formula(
    paste0(
      "trade_value_musd ~ ",
      "fta_active_l1 + ",
      share_variable,
      " + ",
      "gpr_x_fta_l1 + ",
      interaction_variable,
      " | pair_hs2_fe_id + ",
      "exporter_year_fe_id + ",
      "importer_year_fe_id + ",
      "hs2_year_fe_id"
    )
  )

  conditional_fit <- run_bundle_model(
    bundle_row = bundle_row,
    model_spec = "conditional_on_fta",
    formula = conditional_formula,
    target_term = interaction_variable,
    data = mechanism_data
  )

  results_list[[length(results_list) + 1L]] <-
    conditional_fit$results

  audit_list[[length(audit_list) + 1L]] <-
    conditional_fit$audit

  rm(conditional_fit)
  invisible(gc(full = TRUE))
}


# ------------------------------------------------------------
# 8. MULTIPLE-TESTING ADJUSTMENT
# ------------------------------------------------------------
all_results <- rbindlist(
  results_list,
  fill = TRUE
)

model_audit <- rbindlist(
  audit_list,
  fill = TRUE
)

all_results[
  ,
  p_value_fdr_bh := p.adjust(
    p_value,
    method = "BH"
  ),
  by = .(
    model_spec,
    inference
  )
]

all_results[
  ,
  significant_5pct_raw :=
    p_value < 0.05
]

all_results[
  ,
  significant_10pct_raw :=
    p_value < 0.10
]

all_results[
  ,
  significant_5pct_fdr :=
    p_value_fdr_bh < 0.05
]

all_results[
  ,
  significant_10pct_fdr :=
    p_value_fdr_bh < 0.10
]

fwrite(
  all_results,
  COEFFICIENT_FILE
)

fwrite(
  model_audit,
  MODEL_AUDIT_FILE
)


# ------------------------------------------------------------
# 9. HUMAN-READABLE REPORT
# ------------------------------------------------------------
pair_results <- all_results[
  inference == "pair_cluster"
][order(model_spec, estimate)]

two_way_results <- all_results[
  inference == "pair_plus_year_cluster"
][order(model_spec, estimate)]

report_lines <- c(
  paste(rep("=", 104), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 12B DTA MECHANISM-BUNDLE PPML",
  paste(rep("=", 104), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. MODEL DESIGN",
  paste(rep("-", 104), collapse = ""),
  paste(
    "Standalone models estimate the total association of",
    "each provision bundle with the GPR response."
  ),
  paste(
    "FTA-conditional models include FTA membership and its",
    "GPR interaction, so the bundle coefficient measures",
    "incremental agreement composition beyond membership."
  ),
  paste(
    "All five bundles are NOT entered jointly because the",
    "bundle correlations are high."
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
      row$model_spec,
      " | ",
      row$bundle_label,
      ": beta=",
      sprintf("%.6f", row$estimate),
      ", full-bundle effect=",
      sprintf(
        "%.3f%%",
        row$percent_effect_full_bundle
      ),
      ", 10pp effect=",
      sprintf(
        "%.3f%%",
        row$percent_effect_10pp_bundle
      ),
      ", p=",
      sprintf("%.6f", row$p_value),
      ", BH-FDR p=",
      sprintf("%.6f", row$p_value_fdr_bh)
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
      row$model_spec,
      " | ",
      row$bundle_label,
      ": beta=",
      sprintf("%.6f", row$estimate),
      ", p=",
      sprintf("%.6f", row$p_value),
      ", BH-FDR p=",
      sprintf("%.6f", row$p_value_fdr_bh)
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "D. INTERPRETATION RULE",
  paste(rep("-", 104), collapse = ""),
  paste(
    "Emphasize a mechanism only when its direction is stable",
    "across both clustering methods and it survives BH-FDR",
    "adjustment in the FTA-conditional specification."
  ),
  paste(
    "A positive interaction indicates a potential buffering",
    "channel; a negative interaction indicates greater",
    "sensitivity under higher GPR."
  ),
  "",
  "E. OUTPUT FILES",
  paste(rep("-", 104), collapse = ""),
  "outputs/audit/step12b_mechanism_bundle_report.txt",
  "outputs/audit/step12b_mechanism_bundle_model_audit.csv",
  "outputs/tables/step12b_mechanism_bundle_coefficients.csv",
  "",
  "F. NEXT ACTION",
  paste(rep("-", 104), collapse = ""),
  paste(
    "Send the report, coefficient CSV and model-audit CSV",
    "to ChatGPT before running individual-provision tests."
  )
)

writeLines(
  report_lines,
  REPORT_FILE,
  useBytes = TRUE
)

message("")
message("STEP 12B COMPLETED SUCCESSFULLY")
message("Main report: ", REPORT_FILE)

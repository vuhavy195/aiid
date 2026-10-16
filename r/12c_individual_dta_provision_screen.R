# ============================================================
# AIID DTA–GPR PROJECT
# STEP 12C — INDIVIDUAL DTA PROVISION SCREEN
#
# Purpose:
# Estimate the incremental GPR interaction of individual,
# legally enforceable DTA provisions conditional on:
#   - FTA membership
#   - GPR × FTA
#
# Only provisions with support in at least 500 unordered pairs
# are included in the confirmatory screen. InformationSociety
# and InnovationPolicies are excluded because their support is
# too sparse (287 and 29 pairs, respectively).
#
# Benjamini-Hochberg FDR correction is applied across the
# fourteen provision tests separately for each clustering rule.
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
  "step12c_individual_provision_report.txt"
)

MODEL_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step12c_individual_provision_model_audit.csv"
)

COEFFICIENT_FILE <- file.path(
  TABLE_DIR,
  "step12c_individual_provision_coefficients.csv"
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
# 3. PRE-SPECIFIED PROVISIONS
# ------------------------------------------------------------
provision_lookup <- data.table(
  provision_id = 1:14,
  provision = c(
    "Customs",
    "SPS",
    "TBT",
    "PublicProcurement",
    "TRIMs",
    "GATS",
    "TRIPs",
    "CompetitionPolicy",
    "EnvironmentalLaws",
    "IPR",
    "Investment",
    "DataProtection",
    "ResearchandTechnology",
    "MovementofCapital"
  ),
  provision_label = c(
    "Customs",
    "Sanitary and phytosanitary measures",
    "Technical barriers to trade",
    "Public procurement",
    "Trade-related investment measures",
    "Trade in services",
    "Trade-related intellectual property",
    "Competition policy",
    "Environmental laws",
    "Intellectual property rights",
    "Investment",
    "Data protection",
    "Research and technology",
    "Movement of capital"
  ),
  expected_minimum_clusters = c(
    3268L,
    2210L,
    2466L,
    1725L,
    887L,
    2416L,
    2189L,
    1609L,
    855L,
    2030L,
    1589L,
    930L,
    518L,
    2561L
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
  provision_row,
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

  target_term <- paste0(
    "gpr_x_strict_",
    provision_row$provision,
    "_l1"
  )

  target <- coefficient_table[
    coefficient_table$term == target_term,
    ,
    drop = FALSE
  ]

  if (nrow(target) != 1L) {
    stop(
      paste0(
        "Expected exactly one coefficient named ",
        target_term,
        "; found ",
        nrow(target),
        "."
      ),
      call. = FALSE
    )
  }

  target$provision_id <- provision_row$provision_id
  target$provision <- provision_row$provision
  target$provision_label <- provision_row$provision_label
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
      "provision_id",
      "provision",
      "provision_label",
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


run_provision_model <- function(
  provision_row,
  data
) {
  provision_variable <- paste0(
    "strict_",
    provision_row$provision,
    "_l1"
  )

  interaction_variable <- paste0(
    "gpr_x_strict_",
    provision_row$provision,
    "_l1"
  )

  formula_text <- paste0(
    "trade_value_musd ~ ",
    "fta_active_l1 + ",
    provision_variable,
    " + gpr_x_fta_l1 + ",
    interaction_variable,
    " | pair_hs2_fe_id + ",
    "exporter_year_fe_id + ",
    "importer_year_fe_id + ",
    "hs2_year_fe_id"
  )

  message("")
  message(
    "Running provision ",
    provision_row$provision_id,
    " of ",
    nrow(provision_lookup),
    ": ",
    provision_row$provision_label
  )

  elapsed <- system.time({
    model <- fixest::fepois(
      as.formula(formula_text),
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
      extract_target(
        model = model,
        provision_row = provision_row,
        inference_name = "pair_cluster",
        vcov_spec = ~ unordered_pair_cluster_id
      ),
      extract_target(
        model = model,
        provision_row = provision_row,
        inference_name = "pair_plus_year_cluster",
        vcov_spec = ~ unordered_pair_cluster_id + year
      )
    ),
    fill = TRUE
  )

  audit <- data.table(
    provision_id = provision_row$provision_id,
    provision = provision_row$provision,
    provision_label = provision_row$provision_label,
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

provision_columns <- paste0(
  "strict_",
  provision_lookup$provision,
  "_l1"
)

interaction_columns <- paste0(
  "gpr_x_strict_",
  provision_lookup$provision,
  "_l1"
)

required_columns <- c(
  "trade_value_musd",
  "year",
  "fta_active_l1",
  "gpr_x_fta_l1",
  provision_columns,
  interaction_columns,
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
  provision_columns,
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
# 6. INPUT AND SUPPORT AUDIT
# ------------------------------------------------------------
if (nrow(mechanism_data) != EXPECTED_ROWS) {
  stop(
    "Unexpected mechanism-panel row count.",
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
    "Unexpected unordered-pair cluster count.",
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
    "Unexpected year count.",
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
    "Missing values detected in required variables.",
    call. = FALSE
  )
}

support_rows <- list()

for (row_index in seq_len(nrow(provision_lookup))) {
  provision_row <- provision_lookup[row_index]

  provision_variable <- paste0(
    "strict_",
    provision_row$provision,
    "_l1"
  )

  clusters_with_provision <- mechanism_data[
    get(provision_variable) == 1L,
    uniqueN(unordered_pair_cluster_id)
  ]

  support_rows[[row_index]] <- data.table(
    provision_id = provision_row$provision_id,
    provision = provision_row$provision,
    provision_label = provision_row$provision_label,
    clusters_with_provision = clusters_with_provision,
    support_threshold = 500L,
    passes_support_threshold =
      clusters_with_provision >= 500L
  )
}

support_audit <- rbindlist(
  support_rows,
  fill = TRUE
)

if (
  support_audit[
    passes_support_threshold == FALSE,
    .N
  ] > 0L
) {
  stop(
    paste0(
      "At least one selected provision failed the ",
      "500-cluster support threshold."
    ),
    call. = FALSE
  )
}

fwrite(
  support_audit,
  file.path(
    AUDIT_DIR,
    "step12c_individual_provision_support.csv"
  )
)


# ------------------------------------------------------------
# 7. RUN FOURTEEN SEQUENTIAL MODELS
# ------------------------------------------------------------
results_list <- list()
audit_list <- list()

for (row_index in seq_len(nrow(provision_lookup))) {
  fitted <- run_provision_model(
    provision_row = provision_lookup[row_index],
    data = mechanism_data
  )

  results_list[[length(results_list) + 1L]] <-
    fitted$results

  audit_list[[length(audit_list) + 1L]] <-
    fitted$audit

  rm(fitted)
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
  by = inference
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
][order(estimate)]

two_way_results <- all_results[
  inference == "pair_plus_year_cluster"
][order(estimate)]

pair_survivors <- pair_results[
  significant_10pct_fdr == TRUE
]

two_way_survivors <- two_way_results[
  significant_10pct_fdr == TRUE
]

stable_survivors <- merge(
  pair_survivors[
    ,
    .(
      provision,
      pair_estimate = estimate,
      pair_fdr = p_value_fdr_bh
    )
  ],
  two_way_survivors[
    ,
    .(
      provision,
      two_way_estimate = estimate,
      two_way_fdr = p_value_fdr_bh
    )
  ],
  by = "provision"
)

stable_survivors <- stable_survivors[
  sign(pair_estimate) == sign(two_way_estimate)
]

report_lines <- c(
  paste(rep("=", 106), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 12C INDIVIDUAL DTA PROVISION SCREEN",
  paste(rep("=", 106), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. DESIGN",
  paste(rep("-", 106), collapse = ""),
  paste(
    "Fourteen legally enforceable provisions are tested",
    "separately, conditional on FTA membership and GPR × FTA."
  ),
  paste(
    "InformationSociety and InnovationPolicies are excluded",
    "from the confirmatory screen because they occur in only",
    "287 and 29 unordered pairs, respectively."
  ),
  paste(
    "BH-FDR correction is applied across fourteen tests",
    "separately for each clustering method."
  ),
  "",
  "B. PAIR-CLUSTERED RESULTS",
  paste(rep("-", 106), collapse = "")
)

for (row_index in seq_len(nrow(pair_results))) {
  row <- pair_results[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$provision_label,
      ": beta=",
      sprintf("%.6f", row$estimate),
      ", effect=",
      sprintf("%.3f%%", row$percent_effect),
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
  paste(rep("-", 106), collapse = "")
)

for (row_index in seq_len(nrow(two_way_results))) {
  row <- two_way_results[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$provision_label,
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
  "D. MULTIPLE-TESTING SUMMARY",
  paste(rep("-", 106), collapse = ""),
  paste0(
    "Pair-cluster FDR survivors at 10%: ",
    nrow(pair_survivors)
  ),
  paste0(
    "Pair + year FDR survivors at 10%: ",
    nrow(two_way_survivors)
  ),
  paste0(
    "Stable survivors across both clustering rules: ",
    nrow(stable_survivors)
  ),
  paste(
    "Only stable FDR survivors should be described as",
    "credible provision-level channels. Other coefficients",
    "remain exploratory."
  ),
  "",
  "E. OUTPUT FILES",
  paste(rep("-", 106), collapse = ""),
  "outputs/audit/step12c_individual_provision_report.txt",
  "outputs/audit/step12c_individual_provision_support.csv",
  "outputs/audit/step12c_individual_provision_model_audit.csv",
  "outputs/tables/step12c_individual_provision_coefficients.csv",
  "",
  "F. NEXT ACTION",
  paste(rep("-", 106), collapse = ""),
  paste(
    "Send the report, coefficient CSV, support CSV and",
    "model-audit CSV to ChatGPT. After this screen, stop",
    "searching DTA composition and move to resilience outcomes."
  )
)

writeLines(
  report_lines,
  REPORT_FILE,
  useBytes = TRUE
)

message("")
message("STEP 12C COMPLETED SUCCESSFULLY")
message("Main report: ", REPORT_FILE)

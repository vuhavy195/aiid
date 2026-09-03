# ============================================================
# AIID DTA–GPR PROJECT
# STEP 11 — HS2 SECTOR HETEROGENEITY PPML
#
# Purpose:
# - Identify which broad intermediate-goods sectors drive the
#   negative GPR × FTA result.
# - Test whether legally enforceable DTA depth buffers shocks
#   in any specific sector even though the aggregate effect is
#   statistically insignificant.
#
# Ten pre-specified broad sectors are used. Models are estimated
# sequentially to limit RAM use. Benjamini-Hochberg FDR-adjusted
# p-values are reported across the ten sector tests.
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
  "step11_hs2_sector_heterogeneity_report.txt"
)

SECTOR_SUMMARY_FILE <- file.path(
  AUDIT_DIR,
  "step11_hs2_sector_summary.csv"
)

MODEL_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step11_hs2_sector_model_audit.csv"
)

COEFFICIENT_FILE <- file.path(
  TABLE_DIR,
  "step11_hs2_sector_coefficients.csv"
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


assign_sector_id <- function(hs2) {
  fifelse(
    hs2 >= 1L & hs2 <= 24L,
    1L,
    fifelse(
      hs2 >= 25L & hs2 <= 27L,
      2L,
      fifelse(
        hs2 >= 28L & hs2 <= 38L,
        3L,
        fifelse(
          hs2 >= 39L & hs2 <= 43L,
          4L,
          fifelse(
            hs2 >= 44L & hs2 <= 49L,
            5L,
            fifelse(
              hs2 >= 50L & hs2 <= 67L,
              6L,
              fifelse(
                hs2 >= 68L & hs2 <= 83L,
                7L,
                fifelse(
                  hs2 >= 84L & hs2 <= 85L,
                  8L,
                  fifelse(
                    hs2 >= 86L & hs2 <= 89L,
                    9L,
                    10L
                  )
                )
              )
            )
          )
        )
      )
    )
  )
}


extract_target <- function(
  model,
  model_name,
  target_term,
  inference_name,
  vcov_spec,
  sector_id,
  sector_name
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

  target$sector_id <- sector_id
  target$sector_name <- sector_name
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
      "sector_id",
      "sector_name",
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


fit_sector_model <- function(
  formula,
  data,
  subset_vector
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


run_sector_model <- function(
  sector_id,
  sector_name,
  model_name,
  formula,
  target_term,
  data
) {
  subset_vector <- data$sector_id == sector_id
  input_rows <- sum(subset_vector)

  message(
    "Running ",
    model_name,
    " for sector ",
    sector_id,
    ": ",
    sector_name,
    " (",
    format(input_rows, big.mark = ","),
    " rows)"
  )

  elapsed <- system.time({
    model <- fit_sector_model(
      formula = formula,
      data = data,
      subset_vector = subset_vector
    )
  })

  results <- rbindlist(
    list(
      extract_target(
        model = model,
        model_name = model_name,
        target_term = target_term,
        inference_name = "pair_cluster",
        vcov_spec = ~ unordered_pair_cluster_id,
        sector_id = sector_id,
        sector_name = sector_name
      ),
      extract_target(
        model = model,
        model_name = model_name,
        target_term = target_term,
        inference_name = "pair_plus_year_cluster",
        vcov_spec = ~ unordered_pair_cluster_id + year,
        sector_id = sector_id,
        sector_name = sector_name
      )
    ),
    fill = TRUE
  )

  audit <- data.table(
    sector_id = sector_id,
    sector_name = sector_name,
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
    results = results,
    audit = audit
  )
}


# ------------------------------------------------------------
# 4. READ DATA
# ------------------------------------------------------------
stop_if_missing(COMPACT_FILE)

message("Reading compact HS2 data ...")

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

hs2_data[
  ,
  sector_id := assign_sector_id(hs2)
]

sector_lookup <- data.table(
  sector_id = 1:10,
  sector_name = c(
    "Agro-food inputs",
    "Minerals and fuels",
    "Chemicals",
    "Plastics, rubber and leather",
    "Wood, pulp and paper",
    "Textiles and footwear",
    "Stone, glass and base metals",
    "Machinery and electronics",
    "Transport equipment",
    "Precision and other manufactures"
  ),
  hs2_range = c(
    "01–24",
    "25–27",
    "28–38",
    "39–43",
    "44–49",
    "50–67",
    "68–83",
    "84–85",
    "86–89",
    "90–99"
  )
)

hs2_data <- sector_lookup[
  hs2_data,
  on = "sector_id"
]

if (hs2_data[is.na(sector_name), .N] != 0L) {
  stop(
    "At least one HS2 observation was not assigned to a sector.",
    call. = FALSE
  )
}


# ------------------------------------------------------------
# 5. SECTOR DATA SUMMARY
# ------------------------------------------------------------
sector_summary <- hs2_data[
  ,
  .(
    panel_rows = .N,
    distinct_hs2 = uniqueN(hs2),
    pair_hs2_fe_groups = uniqueN(pair_hs2_fe_id),
    unordered_pair_clusters =
      uniqueN(unordered_pair_cluster_id),
    positive_rows = sum(trade_value_musd > 0),
    zero_rows = sum(trade_value_musd == 0),
    zero_share = mean(trade_value_musd == 0),
    trade_value_musd = sum(trade_value_musd)
  ),
  by = .(
    sector_id,
    sector_name,
    hs2_range
  )
][order(sector_id)]

if (sum(sector_summary$panel_rows) != nrow(hs2_data)) {
  stop(
    "Sector row totals do not sum to the full HS2 panel.",
    call. = FALSE
  )
}

fwrite(
  sector_summary,
  SECTOR_SUMMARY_FILE
)


# ------------------------------------------------------------
# 6. RUN 20 SEQUENTIAL MODELS
# ------------------------------------------------------------
results_list <- list()
audit_list <- list()

for (sector_index in seq_len(nrow(sector_lookup))) {
  current_id <- sector_lookup$sector_id[sector_index]
  current_name <- sector_lookup$sector_name[sector_index]

  fta_fit <- run_sector_model(
    sector_id = current_id,
    sector_name = current_name,
    model_name = "fta",
    formula =
      trade_value_musd ~
        fta_active_l1 +
        gpr_x_fta_l1
      |
        pair_hs2_fe_id +
        exporter_year_fe_id +
        importer_year_fe_id +
        hs2_year_fe_id,
    target_term = "gpr_x_fta_l1",
    data = hs2_data
  )

  results_list[[length(results_list) + 1L]] <-
    fta_fit$results

  audit_list[[length(audit_list) + 1L]] <-
    fta_fit$audit

  rm(fta_fit)
  invisible(gc(full = TRUE))

  depth_fit <- run_sector_model(
    sector_id = current_id,
    sector_name = current_name,
    model_name = "depth",
    formula =
      trade_value_musd ~
        depth_strict_l1_10 +
        gpr_x_depth_strict_l1_10
      |
        pair_hs2_fe_id +
        exporter_year_fe_id +
        importer_year_fe_id +
        hs2_year_fe_id,
    target_term = "gpr_x_depth_strict_l1_10",
    data = hs2_data
  )

  results_list[[length(results_list) + 1L]] <-
    depth_fit$results

  audit_list[[length(audit_list) + 1L]] <-
    depth_fit$audit

  rm(depth_fit)
  invisible(gc(full = TRUE))
}


# ------------------------------------------------------------
# 7. MULTIPLE-TESTING ADJUSTMENT
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
    model,
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
# 8. REPORT
# ------------------------------------------------------------
pair_cluster_results <- all_results[
  inference == "pair_cluster"
]

fta_pair <- pair_cluster_results[
  model == "fta"
][order(estimate)]

depth_pair <- pair_cluster_results[
  model == "depth"
][order(estimate)]

fta_fdr <- fta_pair[
  significant_10pct_fdr == TRUE
]

depth_fdr <- depth_pair[
  significant_10pct_fdr == TRUE
]

report_lines <- c(
  paste(rep("=", 102), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 11 HS2 SECTOR HETEROGENEITY",
  paste(rep("=", 102), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. PRE-SPECIFIED SECTORS",
  paste(rep("-", 102), collapse = "")
)

for (row_index in seq_len(nrow(sector_lookup))) {
  row <- sector_lookup[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$sector_id,
      ". ",
      row$sector_name,
      " — HS ",
      row$hs2_range
    )
  )
}

report_lines <- c(
  report_lines,
  "",
  "B. GPR × FTA — PAIR-CLUSTERED",
  paste(rep("-", 102), collapse = "")
)

for (row_index in seq_len(nrow(fta_pair))) {
  row <- fta_pair[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$sector_name,
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
  "C. GPR × DTA DEPTH — PAIR-CLUSTERED",
  paste(rep("-", 102), collapse = "")
)

for (row_index in seq_len(nrow(depth_pair))) {
  row <- depth_pair[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$sector_name,
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
  "D. MULTIPLE-TESTING SUMMARY",
  paste(rep("-", 102), collapse = ""),
  paste0(
    "FTA sectors significant at BH-FDR 10%: ",
    nrow(fta_fdr)
  ),
  paste0(
    "Depth sectors significant at BH-FDR 10%: ",
    nrow(depth_fdr)
  ),
  paste(
    "Raw p-values are exploratory. Sector findings should",
    "be emphasized only when they survive BH-FDR adjustment",
    "and remain directionally stable under pair + year clustering."
  ),
  "",
  "E. OUTPUT FILES",
  paste(rep("-", 102), collapse = ""),
  "outputs/audit/step11_hs2_sector_heterogeneity_report.txt",
  "outputs/audit/step11_hs2_sector_summary.csv",
  "outputs/audit/step11_hs2_sector_model_audit.csv",
  "outputs/tables/step11_hs2_sector_coefficients.csv",
  "",
  "F. NEXT ACTION",
  paste(rep("-", 102), collapse = ""),
  paste(
    "Send the report, coefficient CSV, sector-summary CSV",
    "and model-audit CSV to ChatGPT before interpreting",
    "sector-specific resilience or vulnerability."
  )
)

writeLines(
  report_lines,
  REPORT_FILE,
  useBytes = TRUE
)

message("")
message("STEP 11 COMPLETED SUCCESSFULLY")
message("Main report: ", REPORT_FILE)

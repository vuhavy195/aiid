# ============================================================
# AIID DTA–GPR PROJECT
# STEP 14B — POST-EXIT RECOVERY LPM
#
# Outcomes:
# 1. Re-entry within one year
# 2. Re-entry within two years
# 3. Full recovery within one year
# 4. Full recovery within two years
#
# Main specification:
#   pre-exit link size
#   FTA membership
#   legally enforceable DTA depth
#   GPR × FTA
#   GPR × DTA depth
#
# Baseline fixed effects:
#   directed-pair FE
#   exporter–exit-year FE
#   importer–exit-year FE
#   HS2–exit-year FE
#
# Stringent robustness:
#   pair–HS2 FE replaces directed-pair FE
#
# Inference:
#   unordered-pair clustering
#   unordered-pair + exit-year clustering
#
# The script also calculates the total GPR interaction for
# agreements with 0, 10, 20 and 30 enforceable policy areas:
#
#   beta_total(D) = beta_FTA + D * beta_depth
#
# where D is depth measured in tens of provisions.
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

RECOVERY_FILE <- file.path(
  PROJECT_ROOT,
  "data",
  "processed",
  "estimation_hs2_post_exit_recovery.parquet"
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
  "step14b_recovery_report.txt"
)

INPUT_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step14b_recovery_input_audit.csv"
)

MODEL_AUDIT_FILE <- file.path(
  AUDIT_DIR,
  "step14b_recovery_model_audit.csv"
)

INTERACTION_FILE <- file.path(
  TABLE_DIR,
  "step14b_recovery_interactions.csv"
)

NET_EFFECT_FILE <- file.path(
  TABLE_DIR,
  "step14b_recovery_net_effects.csv"
)

EXPECTED_EVENTS <- 1237520L
EXPECTED_CLUSTERS <- 12431L


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
  outcome,
  fe_spec,
  inference,
  vcov_spec
) {
  table <- as.data.frame(
    fixest::coeftable(
      model,
      vcov = vcov_spec
    )
  )

  table$term <- rownames(table)
  rownames(table) <- NULL

  names(table)[1:4] <- c(
    "estimate",
    "std_error",
    "t_value",
    "p_value"
  )

  target_terms <- c(
    "gpr_x_fta_l1",
    "gpr_x_depth_strict_l1_10"
  )

  target <- table[
    table$term %in% target_terms,
    ,
    drop = FALSE
  ]

  if (nrow(target) != 2L) {
    stop(
      paste0(
        "Expected two interaction coefficients for ",
        outcome,
        " / ",
        fe_spec,
        "; found ",
        nrow(target),
        "."
      ),
      call. = FALSE
    )
  }

  target$outcome <- outcome
  target$fe_spec <- fe_spec
  target$inference <- inference
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
      "outcome",
      "fe_spec",
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


calculate_net_effects <- function(
  model,
  outcome,
  fe_spec,
  inference,
  vcov_spec,
  depth_values,
  cluster_df
) {
  coefficients <- stats::coef(model)

  if (
    !all(
      c(
        "gpr_x_fta_l1",
        "gpr_x_depth_strict_l1_10"
      ) %in% names(coefficients)
    )
  ) {
    stop(
      paste0(
        "Joint interaction coefficients missing for ",
        outcome,
        " / ",
        fe_spec,
        "."
      ),
      call. = FALSE
    )
  }

  covariance <- stats::vcov(
    model,
    vcov = vcov_spec
  )

  beta_fta <- coefficients[
    "gpr_x_fta_l1"
  ]

  beta_depth <- coefficients[
    "gpr_x_depth_strict_l1_10"
  ]

  variance_fta <- covariance[
    "gpr_x_fta_l1",
    "gpr_x_fta_l1"
  ]

  variance_depth <- covariance[
    "gpr_x_depth_strict_l1_10",
    "gpr_x_depth_strict_l1_10"
  ]

  covariance_terms <- covariance[
    "gpr_x_fta_l1",
    "gpr_x_depth_strict_l1_10"
  ]

  rows <- lapply(
    depth_values,
    function(depth_value) {
      estimate <- (
        beta_fta +
          depth_value * beta_depth
      )

      variance <- (
        variance_fta +
          depth_value^2 * variance_depth +
          2 * depth_value * covariance_terms
      )

      standard_error <- sqrt(
        max(variance, 0)
      )

      t_value <- estimate / standard_error

      p_value <- (
        2
        * stats::pt(
          abs(t_value),
          df = cluster_df,
          lower.tail = FALSE
        )
      )

      data.table(
        outcome = outcome,
        fe_spec = fe_spec,
        inference = inference,
        depth_units = depth_value,
        enforceable_provisions = 10 * depth_value,
        estimate = estimate,
        std_error = standard_error,
        t_value = t_value,
        p_value = p_value,
        ci_low = (
          estimate -
            1.96 * standard_error
        ),
        ci_high = (
          estimate +
            1.96 * standard_error
        ),
        effect_percentage_points = (
          100 * estimate
        ),
        ci_low_percentage_points = (
          100 * (
            estimate -
              1.96 * standard_error
          )
        ),
        ci_high_percentage_points = (
          100 * (
            estimate +
              1.96 * standard_error
          )
        ),
        nobs = stats::nobs(model)
      )
    }
  )

  rbindlist(rows, fill = TRUE)
}


fit_recovery_model <- function(
  formula,
  data,
  subset_vector
) {
  fixest::feols(
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


run_recovery_model <- function(
  outcome,
  fe_spec,
  formula,
  subset_vector,
  data,
  depth_values
) {
  input_rows <- sum(subset_vector)

  message("")
  message(
    "Running recovery model: outcome=",
    outcome,
    " | FE=",
    fe_spec,
    " | input rows=",
    format(input_rows, big.mark = ",")
  )

  elapsed <- system.time({
    model <- fit_recovery_model(
      formula = formula,
      data = data,
      subset_vector = subset_vector
    )
  })

  pair_results <- extract_interactions(
    model = model,
    outcome = outcome,
    fe_spec = fe_spec,
    inference = "pair_cluster",
    vcov_spec = ~ unordered_pair_cluster_id
  )

  two_way_results <- extract_interactions(
    model = model,
    outcome = outcome,
    fe_spec = fe_spec,
    inference = "pair_plus_year_cluster",
    vcov_spec = ~ unordered_pair_cluster_id + exit_year
  )

  pair_df <- max(
    data[
      subset_vector,
      uniqueN(unordered_pair_cluster_id)
    ] - 1L,
    1L
  )

  year_df <- max(
    data[
      subset_vector,
      uniqueN(exit_year)
    ] - 1L,
    1L
  )

  pair_net <- calculate_net_effects(
    model = model,
    outcome = outcome,
    fe_spec = fe_spec,
    inference = "pair_cluster",
    vcov_spec = ~ unordered_pair_cluster_id,
    depth_values = depth_values,
    cluster_df = pair_df
  )

  two_way_net <- calculate_net_effects(
    model = model,
    outcome = outcome,
    fe_spec = fe_spec,
    inference = "pair_plus_year_cluster",
    vcov_spec = ~ unordered_pair_cluster_id + exit_year,
    depth_values = depth_values,
    cluster_df = min(pair_df, year_df)
  )

  audit <- data.table(
    outcome = outcome,
    fe_spec = fe_spec,
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
    interactions = rbindlist(
      list(
        pair_results,
        two_way_results
      ),
      fill = TRUE
    ),
    net_effects = rbindlist(
      list(
        pair_net,
        two_way_net
      ),
      fill = TRUE
    ),
    audit = audit
  )
}


# ------------------------------------------------------------
# 4. READ DATA
# ------------------------------------------------------------
stop_if_missing(RECOVERY_FILE)

message("Reading post-exit recovery panel ...")

required_columns <- c(
  "exit_year",
  "reentry_1y_available",
  "reenter_1y",
  "reentry_2y_available",
  "reenter_within_2y",
  "full_recovery_1y",
  "full_recovery_within_2y",
  "log1p_pre_exit_trade_musd",
  "fta_active_l1",
  "depth_strict_l1_10",
  "gpr_x_fta_l1",
  "gpr_x_depth_strict_l1_10",
  "pair_hs2_fe_id",
  "exporter_exit_year_fe_id",
  "importer_exit_year_fe_id",
  "hs2_exit_year_fe_id",
  "unordered_pair_cluster_id"
)

recovery_data <- as.data.table(
  arrow::read_parquet(
    RECOVERY_FILE,
    col_select = all_of(required_columns),
    as_data_frame = TRUE
  )
)

integer_columns <- c(
  "exit_year",
  "reentry_1y_available",
  "reenter_1y",
  "reentry_2y_available",
  "reenter_within_2y",
  "full_recovery_1y",
  "full_recovery_within_2y",
  "fta_active_l1",
  "pair_hs2_fe_id",
  "exporter_exit_year_fe_id",
  "importer_exit_year_fe_id",
  "hs2_exit_year_fe_id",
  "unordered_pair_cluster_id"
)

for (column in integer_columns) {
  set(
    recovery_data,
    j = column,
    value = as.integer(
      recovery_data[[column]]
    )
  )
}

# pair_hs2_fe_id was constructed as pair_index * 100 + hs2.
recovery_data[
  ,
  directed_pair_fe_id :=
    as.integer(
      pair_hs2_fe_id %/% 100
    )
]


# ------------------------------------------------------------
# 5. INPUT AUDIT
# ------------------------------------------------------------
if (nrow(recovery_data) != EXPECTED_EVENTS) {
  stop(
    paste0(
      "Unexpected recovery-event count: ",
      format(nrow(recovery_data), big.mark = ",")
    ),
    call. = FALSE
  )
}

if (
  recovery_data[
    ,
    uniqueN(unordered_pair_cluster_id)
  ] != EXPECTED_CLUSTERS
) {
  stop(
    "Unexpected unordered-pair cluster count.",
    call. = FALSE
  )
}

core_columns <- c(
  "exit_year",
  "log1p_pre_exit_trade_musd",
  "fta_active_l1",
  "depth_strict_l1_10",
  "gpr_x_fta_l1",
  "gpr_x_depth_strict_l1_10",
  "pair_hs2_fe_id",
  "directed_pair_fe_id",
  "exporter_exit_year_fe_id",
  "importer_exit_year_fe_id",
  "hs2_exit_year_fe_id",
  "unordered_pair_cluster_id"
)

if (
  recovery_data[
    ,
    anyNA(.SD),
    .SDcols = core_columns
  ]
) {
  stop(
    "Missing values detected in core recovery variables.",
    call. = FALSE
  )
}

mean_active_depth <- recovery_data[
  fta_active_l1 == 1,
  mean(depth_strict_l1_10)
]

median_active_depth <- recovery_data[
  fta_active_l1 == 1,
  median(depth_strict_l1_10)
]

input_audit <- data.table(
  statistic = c(
    "exit_events",
    "one_year_available_events",
    "two_year_available_events",
    "directed_pair_fe_groups",
    "pair_hs2_fe_groups",
    "unordered_pair_clusters",
    "exit_years",
    "mean_active_fta_depth_units",
    "median_active_fta_depth_units",
    "mean_active_fta_provisions",
    "median_active_fta_provisions"
  ),
  value = c(
    nrow(recovery_data),
    recovery_data[
      reentry_1y_available == 1L,
      .N
    ],
    recovery_data[
      reentry_2y_available == 1L,
      .N
    ],
    recovery_data[, uniqueN(directed_pair_fe_id)],
    recovery_data[, uniqueN(pair_hs2_fe_id)],
    recovery_data[
      ,
      uniqueN(unordered_pair_cluster_id)
    ],
    recovery_data[, uniqueN(exit_year)],
    mean_active_depth,
    median_active_depth,
    10 * mean_active_depth,
    10 * median_active_depth
  )
)

fwrite(
  input_audit,
  INPUT_AUDIT_FILE
)


# ------------------------------------------------------------
# 6. OUTCOME AND FE SPECIFICATIONS
# ------------------------------------------------------------
outcome_specs <- list(
  list(
    outcome = "reenter_1y",
    availability = (
      recovery_data$reentry_1y_available == 1L
    )
  ),
  list(
    outcome = "reenter_within_2y",
    availability = (
      recovery_data$reentry_2y_available == 1L
    )
  ),
  list(
    outcome = "full_recovery_1y",
    availability = (
      recovery_data$reentry_1y_available == 1L
    )
  ),
  list(
    outcome = "full_recovery_within_2y",
    availability = (
      recovery_data$reentry_2y_available == 1L
    )
  )
)

depth_values <- sort(
  unique(
    c(
      0,
      1,
      2,
      3,
      mean_active_depth,
      median_active_depth
    )
  )
)

interaction_results <- list()
net_effect_results <- list()
model_audits <- list()


# ------------------------------------------------------------
# 7. RUN EIGHT SEQUENTIAL MODELS
# ------------------------------------------------------------
for (spec in outcome_specs) {
  outcome <- spec$outcome
  subset_vector <- spec$availability

  baseline_formula <- as.formula(
    paste0(
      outcome,
      " ~ log1p_pre_exit_trade_musd + ",
      "fta_active_l1 + ",
      "depth_strict_l1_10 + ",
      "gpr_x_fta_l1 + ",
      "gpr_x_depth_strict_l1_10",
      " | directed_pair_fe_id + ",
      "exporter_exit_year_fe_id + ",
      "importer_exit_year_fe_id + ",
      "hs2_exit_year_fe_id"
    )
  )

  baseline_fit <- run_recovery_model(
    outcome = outcome,
    fe_spec = "directed_pair_fe",
    formula = baseline_formula,
    subset_vector = subset_vector,
    data = recovery_data,
    depth_values = depth_values
  )

  interaction_results[[length(interaction_results) + 1L]] <-
    baseline_fit$interactions

  net_effect_results[[length(net_effect_results) + 1L]] <-
    baseline_fit$net_effects

  model_audits[[length(model_audits) + 1L]] <-
    baseline_fit$audit

  rm(baseline_fit)
  invisible(gc(full = TRUE))

  stringent_formula <- as.formula(
    paste0(
      outcome,
      " ~ log1p_pre_exit_trade_musd + ",
      "fta_active_l1 + ",
      "depth_strict_l1_10 + ",
      "gpr_x_fta_l1 + ",
      "gpr_x_depth_strict_l1_10",
      " | pair_hs2_fe_id + ",
      "exporter_exit_year_fe_id + ",
      "importer_exit_year_fe_id + ",
      "hs2_exit_year_fe_id"
    )
  )

  stringent_fit <- run_recovery_model(
    outcome = outcome,
    fe_spec = "pair_hs2_fe",
    formula = stringent_formula,
    subset_vector = subset_vector,
    data = recovery_data,
    depth_values = depth_values
  )

  interaction_results[[length(interaction_results) + 1L]] <-
    stringent_fit$interactions

  net_effect_results[[length(net_effect_results) + 1L]] <-
    stringent_fit$net_effects

  model_audits[[length(model_audits) + 1L]] <-
    stringent_fit$audit

  rm(stringent_fit)
  invisible(gc(full = TRUE))
}


# ------------------------------------------------------------
# 8. EXPORT
# ------------------------------------------------------------
interactions <- rbindlist(
  interaction_results,
  fill = TRUE
)

net_effects <- rbindlist(
  net_effect_results,
  fill = TRUE
)

model_audit <- rbindlist(
  model_audits,
  fill = TRUE
)

fwrite(
  interactions,
  INTERACTION_FILE
)

fwrite(
  net_effects,
  NET_EFFECT_FILE
)

fwrite(
  model_audit,
  MODEL_AUDIT_FILE
)


# ------------------------------------------------------------
# 9. REPORT
# ------------------------------------------------------------
primary_interactions <- interactions[
  fe_spec == "directed_pair_fe"
  & inference == "pair_plus_year_cluster"
][order(outcome, term)]

primary_net <- net_effects[
  fe_spec == "directed_pair_fe"
  & inference == "pair_plus_year_cluster"
  & enforceable_provisions %in% c(0, 10, 20, 30)
][order(outcome, enforceable_provisions)]

report_lines <- c(
  paste(rep("=", 108), collapse = ""),
  "AIID DTA–GPR PROJECT — STEP 14B POST-EXIT RECOVERY LPM",
  paste(rep("=", 108), collapse = ""),
  paste0("Project root: ", PROJECT_ROOT),
  "",
  "A. SAMPLE",
  paste(rep("-", 108), collapse = ""),
  paste0(
    "Exit events: ",
    format(nrow(recovery_data), big.mark = ",")
  ),
  paste0(
    "One-year follow-up events: ",
    format(
      recovery_data[
        reentry_1y_available == 1L,
        .N
      ],
      big.mark = ","
    )
  ),
  paste0(
    "Two-year follow-up events: ",
    format(
      recovery_data[
        reentry_2y_available == 1L,
        .N
      ],
      big.mark = ","
    )
  ),
  paste0(
    "Mean active-FTA depth: ",
    sprintf(
      "%.3f provisions",
      10 * mean_active_depth
    )
  ),
  paste0(
    "Median active-FTA depth: ",
    sprintf(
      "%.3f provisions",
      10 * median_active_depth
    )
  ),
  "",
  "B. PRIMARY DIRECTED-PAIR FE INTERACTIONS",
  "   PAIR + EXIT-YEAR CLUSTERED",
  paste(rep("-", 108), collapse = "")
)

for (row_index in seq_len(nrow(primary_interactions))) {
  row <- primary_interactions[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$outcome,
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
  "C. NET GPR INTERACTION BY AGREEMENT DEPTH",
  "   DIRECTED-PAIR FE, PAIR + EXIT-YEAR CLUSTERED",
  paste(rep("-", 108), collapse = "")
)

for (row_index in seq_len(nrow(primary_net))) {
  row <- primary_net[row_index]

  report_lines <- c(
    report_lines,
    paste0(
      row$outcome,
      " | ",
      sprintf(
        "%.0f provisions",
        row$enforceable_provisions
      ),
      ": effect=",
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
  "D. FIXED-EFFECT ROBUSTNESS",
  paste(rep("-", 108), collapse = ""),
  paste(
    "The directed-pair FE model is the primary recovery",
    "specification because many pair-HS2 links exit only once."
  ),
  paste(
    "The pair-HS2 FE model is a stringent robustness check",
    "identified only from links with repeated exit events and",
    "within-link variation in recovery outcomes."
  ),
  "",
  "E. OUTPUT FILES",
  paste(rep("-", 108), collapse = ""),
  "outputs/audit/step14b_recovery_report.txt",
  "outputs/audit/step14b_recovery_input_audit.csv",
  "outputs/audit/step14b_recovery_model_audit.csv",
  "outputs/tables/step14b_recovery_interactions.csv",
  "outputs/tables/step14b_recovery_net_effects.csv",
  "",
  "F. NEXT ACTION",
  paste(rep("-", 108), collapse = ""),
  paste(
    "Send the report, interaction CSV, net-effect CSV and",
    "model-audit CSV to ChatGPT before running recovery",
    "robustness or drafting the final empirical narrative."
  )
)

writeLines(
  report_lines,
  REPORT_FILE,
  useBytes = TRUE
)

message("")
message("STEP 14B COMPLETED SUCCESSFULLY")
message("Main report: ", REPORT_FILE)

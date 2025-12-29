# ==============================================================================
# Two-Step MR Mediation Analysis
# Implements the methods section: product-of-effects mediation, delta-method
# inference, proportional scaling when multiple mediators exceed total effect 1,
# and FDR-based significance (≤ 0.05).
# ==============================================================================

# 1. Required Packages ---------------------------------------------------------
suppressPackageStartupMessages({
  library(dplyr)
  library(purrr)
  library(stats)
})

# 2. Delta-Method Helpers ------------------------------------------------------

# Delta-method variance for the product of two independent estimates.
delta_var_product <- function(beta_a, se_a, beta_b, se_b) {
  (beta_b^2 * se_a^2) + (beta_a^2 * se_b^2)
}

# Per-mediator raw indirect effect and uncertainty.
compute_raw_indirect <- function(df) {
  df %>%
    mutate(
      indirect_raw = beta_protein_mediator * beta_mediator_longevity,
      var_raw = delta_var_product(
        beta_a = beta_protein_mediator,
        se_a = se_protein_mediator,
        beta_b = beta_mediator_longevity,
        se_b = se_mediator_longevity
      ),
      se_raw = sqrt(var_raw),
      z_raw = indirect_raw / se_raw,
      p_raw = 2 * pnorm(-abs(z_raw))
    )
}

# 3. Proportional Scaling (when Σ|indirect_raw| > 1) ---------------------------

# Delta-method variance for scaled effects where the scaling factor depends on
# all mediators for a protein: scaled_i = raw_i / sum_j |raw_j|.
delta_var_scaled <- function(raw_effects, raw_vars) {
  total_abs <- sum(abs(raw_effects))
  if (total_abs <= 1) {
    return(raw_vars)
  }

  n <- length(raw_effects)
  scaled_vars <- numeric(n)

  for (i in seq_len(n)) {
    gradients <- numeric(n)
    for (j in seq_len(n)) {
      sign_j <- ifelse(raw_effects[j] >= 0, 1, -1)
      shared_term <- -(raw_effects[i] / (total_abs^2)) * sign_j
      gradients[j] <- if (i == j) (1 / total_abs) + shared_term else shared_term
    }
    scaled_vars[i] <- sum((gradients^2) * raw_vars)
  }

  scaled_vars
}

apply_scaling <- function(df) {
  df %>%
    group_by(protein_id) %>%
    group_modify(~{
      raw_effects <- .x$indirect_raw
      raw_vars <- .x$var_raw
      total_abs <- sum(abs(raw_effects))

      if (total_abs <= 1) {
        .x$indirect_scaled <- .x$indirect_raw
        .x$var_scaled <- .x$var_raw
      } else {
        scale_factor <- 1 / total_abs
        .x$indirect_scaled <- raw_effects * scale_factor
        .x$var_scaled <- delta_var_scaled(raw_effects, raw_vars)
      }

      .x$se_scaled <- sqrt(.x$var_scaled)
      .x$z_scaled <- .x$indirect_scaled / .x$se_scaled
      .x$p_scaled <- 2 * pnorm(-abs(.x$z_scaled))
      .x$total_abs_indirect <- total_abs
      .x
    }) %>%
    ungroup()
}

# 4. Reporting Scale (OR for binary outcomes, β for continuous) ----------------
add_report_scale <- function(df) {
  df %>%
    mutate(
      reported_effect = ifelse(outcome_type == "binary",
                               exp(indirect_scaled),
                               indirect_scaled),
      reported_se = ifelse(outcome_type == "binary",
                           exp(indirect_scaled) * se_scaled,
                           se_scaled),
      ci_lower = ifelse(outcome_type == "binary",
                        exp(indirect_scaled - 1.96 * se_scaled),
                        indirect_scaled - 1.96 * se_scaled),
      ci_upper = ifelse(outcome_type == "binary",
                        exp(indirect_scaled + 1.96 * se_scaled),
                        indirect_scaled + 1.96 * se_scaled),
      effect_label = ifelse(outcome_type == "binary", "OR", "beta")
    )
}

# 5. Main Workflow -------------------------------------------------------------
# Required columns:
#   protein_id                : identifier for the circulating protein
#   mediator_id               : mediator (disease or modifiable trait)
#   beta_protein_mediator     : causal effect (1 SD protein -> mediator)
#   se_protein_mediator       : standard error for beta_protein_mediator
#   beta_mediator_longevity   : causal effect (mediator -> longevity)
#   se_mediator_longevity     : standard error for beta_mediator_longevity
#   outcome_type              : "binary" or "continuous" for longevity
#
# Returns tidy tibble with raw and scaled indirect effects, delta-method
# variances, z-scores, p-values, FDR, and reported scale (OR / beta).
run_mediation_analysis <- function(df) {
  df %>%
    compute_raw_indirect() %>%
    apply_scaling() %>%
    add_report_scale() %>%
    mutate(
      fdr = p.adjust(p_scaled, method = "fdr"),
      significant = fdr <= 0.05
    ) %>%
    arrange(protein_id, mediator_id)
}

# 6. Example Usage -------------------------------------------------------------
# example_df <- tibble::tibble(
#   protein_id = c("P1", "P1", "P2"),
#   mediator_id = c("BMI", "T2D", "Smoking"),
#   beta_protein_mediator = c(0.10, 0.06, -0.08),
#   se_protein_mediator = c(0.02, 0.03, 0.025),
#   beta_mediator_longevity = c(-0.12, 0.20, 0.15),
#   se_mediator_longevity = c(0.04, 0.05, 0.06),
#   outcome_type = c("continuous", "binary", "binary")
# )
# mediation_results <- run_mediation_analysis(example_df)
# print(mediation_results)

# End of Mediation Analysis Implementation

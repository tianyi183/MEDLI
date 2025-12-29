# ==============================================================================
# Modeling Performance Validation
# Two-tier validation using clinical endpoints (mortality, disease incidence)
# and independent biomarkers of biological aging (KDM BA, PhenoAge) in a
# validation set (N = 3,264).
# ==============================================================================

suppressPackageStartupMessages({
  library(dplyr)
  library(purrr)
  library(survival)
  library(survminer)
  library(ggplot2)
  library(splines)
})

# 1. Clinical Endpoints: Survival and Incidence --------------------------------
# Diseases: ICD-10 categories with ≥200 prevalent cases in validation set:
# acute myocardial infarction, angina pectoris, chronic ischemic heart disease,
# chronic renal failure, obesity, type 2 diabetes mellitus.

compute_km_curves <- function(df, time_col = "follow_up_years", event_col = "event",
                              group_col = "health_potential_group") {
  fit <- survfit(Surv(.data[[time_col]], .data[[event_col]]) ~ .data[[group_col]], data = df)
  ggsurvplot(fit, data = df, risk.table = TRUE, pval = TRUE, conf.int = TRUE)
}

compute_cumulative_incidence <- function(df, time_col = "follow_up_years",
                                         event_col = "event",
                                         group_col = "health_potential_group") {
  # For cause-specific incidence, treat event=1 as incidence; competing risks not specified.
  fit <- survfit(Surv(.data[[time_col]], .data[[event_col]]) ~ .data[[group_col]], data = df)
  ggsurvplot(fit, data = df, fun = "event", risk.table = TRUE, pval = TRUE, conf.int = TRUE)
}

prepare_validation_groups <- function(df, score_col = "health_potential", n_groups = 5) {
  df %>%
    mutate(health_potential_group = ntile(.data[[score_col]], n_groups))
}

# 2. Biological Aging Metrics ---------------------------------------------------
# KDM BA: inverse-variance weighted regression of biomarkers to chronological age.
compute_kdm_ba <- function(df, biomarker_cols, age_col = "chron_age") {
  # weights = 1/var(biomarker), per KDM specification.
  biomarker_vars <- sapply(df[biomarker_cols], var, na.rm = TRUE)
  weights <- 1 / biomarker_vars

  # Weighted regression age ~ biomarkers
  fit <- lm(
    reformulate(termlabels = biomarker_cols, response = age_col),
    data = df,
    weights = weights[colnames(model.matrix(~ ., df[biomarker_cols]))[-1]]
  )
  predict(fit, newdata = df)
}

# PhenoAge: using published coefficients (to be supplied as named numeric vector).
compute_phenoage <- function(df, biomarker_cols, coefficients, intercept) {
  linpred <- as.matrix(df[biomarker_cols]) %*% coefficients + intercept
  # Mortality-based transformation per published formula:
  141.5 + exp(linpred)  # placeholder transformation; replace with published form if needed.
}

# 3. Associations Between Model Score and Aging Biomarkers ---------------------
analyze_score_vs_aging <- function(df, score_col = "health_potential", ba_col = "kdm_ba") {
  cor_pearson <- cor(df[[score_col]], df[[ba_col]], use = "complete.obs")
  spline_fit <- lm(
    df[[ba_col]] ~ ns(df[[score_col]], df = 3)
  )
  list(
    pearson = cor_pearson,
    spline_fit = spline_fit
  )
}

# 4. End-to-end Validation Pipeline -------------------------------------------
run_validation <- function(df_survival,
                           df_disease_list,
                           aging_df,
                           kdm_biomarkers,
                           pheno_biomarkers,
                           pheno_coefficients,
                           pheno_intercept) {
  # Group by health-potential score
  df_surv_grp <- prepare_validation_groups(df_survival)

  km_plot <- compute_km_curves(df_surv_grp)
  incidence_plots <- map(df_disease_list, ~ compute_cumulative_incidence(.x))

  # Aging metrics
  aging_df <- aging_df %>%
    mutate(
      kdm_ba = compute_kdm_ba(., biomarker_cols = kdm_biomarkers, age_col = "chron_age"),
      phenoage = compute_phenoage(., biomarker_cols = pheno_biomarkers,
                                  coefficients = pheno_coefficients,
                                  intercept = pheno_intercept)
    )

  kdm_assoc <- analyze_score_vs_aging(aging_df, ba_col = "kdm_ba")
  pheno_assoc <- analyze_score_vs_aging(aging_df, ba_col = "phenoage")

  list(
    km_plot = km_plot,
    incidence_plots = incidence_plots,
    kdm_association = kdm_assoc,
    pheno_association = pheno_assoc
  )
}

# 5. Notes ---------------------------------------------------------------------
# - df_survival: columns follow_up_years, event (1/0), health_potential.
# - df_disease_list: list of data frames per ICD-10 disease category (>=200 cases), with same columns.
# - Aging biomarkers:
#     KDM: systolic BP, FEV1, HbA1c, cholesterol, creatinine, urea, CRP, albumin.
#     PhenoAge: albumin, creatinine, glucose, CRP, lymphocyte %, MCV, RDW, ALP, WBC.
# - Pearson correlations and spline models relate health-potential score to aging biomarkers.
# - Replace placeholder PhenoAge transform with the exact published mortality-based formula when applying.

# End of Modeling Performance Validation

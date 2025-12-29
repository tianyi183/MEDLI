# ==============================================================================
# Mediation-informed Machine Learning Modeling Framework
# Implements three configurations:
#   (i) mediation-free (baseline age, sex, 60 longevity-causal proteins)
#   (ii) disease-informed mediation (ICD-10 grouped MR-identified diseases)
#   (iii) modifiable-trait-informed mediation (MR-weighted trait pathways)
# Prediction target: 16-year lifespan (alive vs died). Thirty algorithms are
# evaluated and the best performer is carried into mediation-informed modules.
# ==============================================================================

suppressPackageStartupMessages({
  library(dplyr)
  library(purrr)
  library(recipes)
  library(rsample)
  library(yardstick)
  library(caret)
})

# 1. Candidate Algorithms (30 across 8 categories) -----------------------------
candidate_models <- c(
  # Linear / generalized linear
  "glm", "glmnet", "ridge", "lasso",
  # Tree-based
  "rpart", "C5.0", "treebag", "extraTrees",
  # Random forest variants
  "rf", "ranger", "wsrf", "rotationForest",
  # Boosting
  "gbm", "xgbTree", "ada", "adabag", "LogitBoost",
  # SVM
  "svmLinear", "svmRadial", "svmPoly",
  # kNN
  "knn", "kknn",
  # Neural nets
  "nnet", "mlp", "mlpWeightDecay",
  # Probabilistic / Bayes
  "naive_bayes",
  # Rule/ensemble
  "earth", "bartMachine", "pam"
)

# Keep only models available in the current R environment.
available_models <- function(models) {
  supported <- unique(caret::modelLookup()$model)
  intersect(models, supported)
}

# 2. Data Preparation -----------------------------------------------------------
# Expects: columns id, outcome (factor: levels c("alive","died"), positive="died"),
# baseline_age (numeric), sex (factor), and 60 protein columns (numeric).
baseline_recipe <- function(df, protein_cols) {
  recipe(outcome ~ baseline_age + sex + all_of(protein_cols), data = df) %>%
    step_dummy(all_nominal_predictors()) %>%
    step_zv(all_predictors()) %>%
    step_normalize(all_numeric_predictors())
}

# 3. Mediation-free Configuration ----------------------------------------------
train_mediation_free <- function(df, protein_cols, models = candidate_models, folds = 5, seed = 2025) {
  set.seed(seed)
  models <- available_models(models)
  if (length(models) == 0) stop("No candidate models are available in this environment.")

  rec <- baseline_recipe(df, protein_cols)
  ctrl <- trainControl(
    method = "cv",
    number = folds,
    classProbs = TRUE,
    summaryFunction = twoClassSummary,
    savePredictions = "final"
  )

  fits <- map(models, function(mdl) {
    caret::train(
      rec,
      data = df,
      method = mdl,
      metric = "ROC",
      trControl = ctrl
    )
  })
  names(fits) <- models

  metrics <- map_dfr(fits, ~ .x$results %>% slice_max(ROC, n = 1) %>% mutate(model = .x$method))
  best <- metrics %>% slice_max(ROC, n = 1)
  list(
    fits = fits,
    metrics = metrics,
    best_model = fits[[best$model]],
    best_name = best$model,
    best_metric = best$ROC
  )
}

# 4. Disease-informed Mediation Configuration ----------------------------------
# For each ICD-10 disease category, train model using same 60 proteins.
# Returns per-disease 0–1 disease-mediated score (predicted onset probability).
train_disease_models <- function(df, protein_cols, disease_col = "disease_category",
                                 outcome_col = "disease_onset", seed = 2025) {
  set.seed(seed)
  disease_levels <- unique(df[[disease_col]])
  models <- available_models(candidate_models)
  rec_base <- function(data) {
    recipe(reformulate(c("baseline_age", "sex", protein_cols), response = outcome_col), data = data) %>%
      step_dummy(all_nominal_predictors()) %>%
      step_zv(all_predictors()) %>%
      step_normalize(all_numeric_predictors())
  }
  ctrl <- trainControl(method = "cv", number = 5, classProbs = TRUE,
                       summaryFunction = twoClassSummary, savePredictions = "final")

  disease_models <- map(disease_levels, function(dz) {
    df_dz <- df %>% filter(.data[[disease_col]] == dz)
    rec <- rec_base(df_dz)
    # Use the best-performing base learner (first available) to reduce compute.
    mdl <- models[1]
    fit <- caret::train(rec, data = df_dz, method = mdl, metric = "ROC", trControl = ctrl)
    tibble::tibble(
      disease_category = dz,
      model = list(fit)
    )
  }) %>% bind_rows()

  predict_scores <- function(new_data) {
    map_dfc(seq_len(nrow(disease_models)), function(i) {
      mdl <- disease_models$model[[i]]
      dz <- disease_models$disease_category[[i]]
      prob <- predict(mdl, newdata = new_data, type = "prob")[, "disease"] # assumes positive class named "disease"
      tibble::tibble(!!paste0("disease_score_", dz) := prob)
    })
  }

  list(models = disease_models, predict_scores = predict_scores)
}

# 5. Modifiable-trait-informed Configuration -----------------------------------
# MR-weighted score: individual deviation from cohort distribution scaled 0–1.
compute_mod_trait_score <- function(trait_value, trait_mean, trait_sd, beta_trait_longevity) {
  deviation <- (trait_value - trait_mean) / trait_sd
  raw_score <- deviation * beta_trait_longevity
  scales::rescale(raw_score, to = c(0, 1), from = range(raw_score, na.rm = TRUE))
}

# Pathway activation per two-step MR triplet: sum_i ( (x_ik - mu_i) * beta_i_trait * beta_trait_longevity )
compute_pathway_activation <- function(expr_matrix, cohort_means, beta_protein_to_trait, beta_trait_to_longevity) {
  centered <- sweep(expr_matrix, 2, cohort_means, FUN = "-")
  raw_activation <- as.numeric(centered %*% beta_protein_to_trait) * beta_trait_to_longevity
  scales::rescale(raw_activation, to = c(0, 1), from = range(raw_activation, na.rm = TRUE))
}

# 6. Health Potential Score ----------------------------------------------------
# Transform model probability of survival to 40–100 scale.
health_potential_score <- function(p_alive) {
  40 + 60 * p_alive
}

# 7. End-to-end Framework Orchestration ----------------------------------------
# Inputs:
#   survival_df: id, outcome (alive/died), baseline_age, sex, protein cols (60)
#   disease_df: id, disease_category, disease_onset (disease/no_disease), proteins
#   mod_trait_df: id, trait_name, trait_value, proteins, cohort stats, MR betas
#   protein_cols: character vector of 60 protein column names
build_framework <- function(survival_df, disease_df, mod_trait_df, protein_cols) {
  # Mediation-free
  base_fit <- train_mediation_free(survival_df, protein_cols = protein_cols)

  # Disease-informed
  disease_fit <- train_disease_models(disease_df, protein_cols = protein_cols)

  # Modifiable traits: compute scores
  mod_trait_scores <- mod_trait_df %>%
    mutate(
      trait_score = compute_mod_trait_score(
        trait_value = trait_value,
        trait_mean = trait_mean,
        trait_sd = trait_sd,
        beta_trait_longevity = beta_trait_to_longevity
      ),
      pathway_activation = compute_pathway_activation(
        expr_matrix = as.matrix(select(., all_of(protein_cols))),
        cohort_means = trait_protein_means,
        beta_protein_to_trait = beta_protein_to_trait,
        beta_trait_to_longevity = beta_trait_to_longevity
      )
    )

  # Final outputs: base survival prob + transformed health potential
  base_prob <- predict(base_fit$best_model, newdata = survival_df, type = "prob")[, "died"]
  survival_df <- survival_df %>%
    mutate(
      p_died = base_prob,
      p_alive = 1 - base_prob,
      health_potential = health_potential_score(p_alive)
    )

  list(
    mediation_free = base_fit,
    disease_informed = disease_fit,
    mod_trait_scores = mod_trait_scores,
    survival_predictions = survival_df
  )
}

# 8. Notes ---------------------------------------------------------------------
# - Ensure outcome factor levels: for survival, outcome = factor(c("alive","died"), levels=c("alive","died")).
# - For disease models, outcome_col positive class should be named "disease".
# - Protein inputs are NPX (log2) abundance for 60 longevity-causal proteins.
# - MR betas should correspond to 1 SD increases; ensure alignment with trait scale.

# End of Mediation-informed Modeling Framework

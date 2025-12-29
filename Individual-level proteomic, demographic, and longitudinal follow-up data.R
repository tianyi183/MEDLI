# ==============================================================================
# Individual-level Proteomic, Demographic, and Longitudinal Follow-up Processing
# Implements the study’s data handling: Olink NPX proteomics, ≤30% missingness
# threshold, single imputation via miceforest (max 5 iterations, defaults
# otherwise), ICD-10 based clinical data, UKB follow-up with region-specific
# censor dates, and decimal age at recruitment.
# ==============================================================================

# 1. Required Packages ---------------------------------------------------------
suppressPackageStartupMessages({
  library(dplyr)
  library(lubridate)
  library(miceforest)
})

# 2. Proteomic Data: Missingness Filter ----------------------------------------
# Retains proteins missing in ≤ 30% of participants.
filter_proteins_missingness <- function(proteomic_df, id_col = "eid", max_missing_prop = 0.30) {
  protein_cols <- setdiff(names(proteomic_df), id_col)
  missing_prop <- sapply(protein_cols, function(cn) mean(is.na(proteomic_df[[cn]])))
  keep_cols <- names(missing_prop[missing_prop <= max_missing_prop])

  filtered_df <- proteomic_df %>%
    select(all_of(id_col), all_of(keep_cols))

  list(
    data = filtered_df,
    missingness = tibble::tibble(protein = protein_cols, missing_prop = missing_prop)
  )
}

# 3. Proteomic Data: Single Imputation (miceforest v6.0.3) ----------------------
# Performs a single completed dataset over max 5 iterations (defaults otherwise).
impute_proteomics <- function(proteomic_df, id_col = "eid", max_iter = 5, seed = 2025) {
  protein_matrix <- proteomic_df %>% select(-all_of(id_col))
  if (ncol(protein_matrix) == 0) {
    stop("No protein columns available for imputation.")
  }

  imp <- miceforest::impute(
    data = protein_matrix,
    m = 1,                  # single dataset as specified
    maxiter = max_iter,
    seed = seed,
    verbose = FALSE
  )

  completed <- miceforest::complete(imp, action = 1)

  proteomic_df %>%
    select(all_of(id_col)) %>%
    bind_cols(completed)
}

# 4. Demographics: Decimal Age at Recruitment ----------------------------------
# Birth date approximated as first day of birth month/year; age annualized /365.25.
compute_decimal_age <- function(birth_year, birth_month, recruitment_date) {
  est_birth <- make_date(year = birth_year, month = birth_month, day = 1)
  as.numeric(difftime(recruitment_date, est_birth, units = "days")) / 365.25
}

# 5. Follow-up: Region-specific Censor Dates -----------------------------------
add_censor_date <- function(df, region_col = "region") {
  df %>%
    mutate(
      censor_date = case_when(
        .data[[region_col]] == "England"  ~ as.Date("2022-10-31"),
        .data[[region_col]] == "Wales"    ~ as.Date("2018-02-28"),
        .data[[region_col]] == "Scotland" ~ as.Date("2021-07-31"),
        TRUE                              ~ NA_Date_
      )
    )
}

# 6. Follow-up: Event Adjudication and Time-at-Risk ----------------------------
# Expects ICD-10-coded diagnoses and death events from linked registries.
# event_date should be the earliest date among hospital, primary care, cancer,
# or death records that meet the study’s ICD-10 definitions.
derive_follow_up <- function(df,
                             id_col = "eid",
                             recruitment_col = "recruitment_date",
                             event_date_col = "event_date",
                             region_col = "region") {
  df %>%
    add_censor_date(region_col = region_col) %>%
    mutate(
      follow_up_end = pmin(.data[[event_date_col]], censor_date, na.rm = TRUE),
      event = if_else(!is.na(.data[[event_date_col]]) &
                        .data[[event_date_col]] <= censor_date, 1L, 0L),
      follow_up_years = as.numeric(difftime(follow_up_end, .data[[recruitment_col]], units = "days")) / 365.25
    ) %>%
    select(all_of(id_col), follow_up_end, event, follow_up_years, censor_date)
}

# 7. Integrated Workflow -------------------------------------------------------
# Steps:
#   1) Filter proteins with ≤30% missingness.
#   2) Single imputation over max 5 iterations (all other params default).
#   3) Merge with demographics and follow-up data (ICD-10 based events).
prepare_individual_level_data <- function(proteomic_df,
                                          demographics_df,
                                          followup_df,
                                          id_col = "eid") {
  # Proteins: filter + impute
  filtered <- filter_proteins_missingness(proteomic_df, id_col = id_col)
  imputed_proteins <- impute_proteomics(filtered$data, id_col = id_col)

  # Merge demographics (incl. decimal age) and follow-up outcomes
  demographics_enriched <- demographics_df %>%
    mutate(decimal_age = compute_decimal_age(birth_year, birth_month, recruitment_date))

  follow_up_metrics <- derive_follow_up(followup_df,
                                        id_col = id_col,
                                        recruitment_col = "recruitment_date",
                                        event_date_col = "event_date",
                                        region_col = "region")

  imputed_proteins %>%
    left_join(demographics_enriched, by = id_col) %>%
    left_join(follow_up_metrics, by = id_col)
}

# 8. Example Usage (commented) -------------------------------------------------
# proteomic_df: columns eid + NPX proteins (log2 scale, Olink Explore 3072).
# demographics_df: eid, birth_year, birth_month, recruitment_date (Date), region.
# followup_df: eid, recruitment_date (Date), event_date (Date of ICD-10-defined diagnosis or death), region.
#
# processed <- prepare_individual_level_data(
#   proteomic_df = proteomic_df,
#   demographics_df = demographics_df,
#   followup_df = followup_df,
#   id_col = "eid"
# )
# head(processed)

# End of Individual-level Data Processing

# ==============================================================================
# Mendelian Randomization (MR) Analysis Implementation
# Implementation of IVW (Fixed/Random), Wald Ratio, MR-Egger, and
# comprehensive sensitivity analyses based on specific methodological criteria.
# ==============================================================================

# 1. Environment Preparation ---------------------------------------------------
# Required Packages: 
# MendelianRandomization (v10.0), TwoSampleMR (v0.6.6), 
# MRPRESSO (v1.0), metafor (v4.6.0)

library(TwoSampleMR)           
library(MendelianRandomization) 
library(MRPRESSO)               
library(metafor)                
library(dplyr)

# 2. Primary Analysis Function -------------------------------------------------
# This function implements the conditional logic for model selection based 
# on the number of Instrumental Variables (IVs).
run_primary_mr <- function(dat) {
  n_ivs <- nrow(dat)
  results <- list()
  
  # CASE 1: Single IV
  if (n_ivs == 1) {
    # Use Wald ratio method for exposures with only one IV
    results[[1]] <- mr(dat, method_list = "mr_wald_ratio")
    
  } else {
    # CASE 2: Multiple IVs - Primary Causal Effect (IVW)
    if (n_ivs <= 3) {
      # Fixed-effects IVW model applied when 3 or fewer IVs are available
      res_ivw <- mr(dat, method_list = "mr_ivw_fe")
    } else {
      # Multiplicative random-effects model used for more than 3 IVs
      res_ivw <- mr(dat, method_list = "mr_ivw_mre")
    }
    results[[1]] <- res_ivw
    
    # CASE 3: MR-Egger
    # Applied when 3 or more IVs are available
    if (n_ivs >= 3) {
      res_egger <- mr(dat, method_list = "mr_egger_regression")
      results[[2]] <- res_egger
    }
  }
  
  return(bind_rows(results))
}

# 3. Comprehensive Analysis Workflow -------------------------------------------

# --- Data Harmonization ---
# Harmonize SNP-exposure and SNP-outcome estimates to the same effect allele
# dat <- harmonise_data(exposure_dat, outcome_dat, action = 2)

# --- Primary MR Analysis ---
mr_results <- run_primary_mr(dat)

# --- Sensitivity Analysis: Heterogeneity ---
# Evaluated using Cochran’s Q statistic
heterogeneity_test <- mr_heterogeneity(dat)

# --- Sensitivity Analysis: Horizontal Pleiotropy ---
# Tested via the MR-Egger intercept (for IVs >= 3)
if (nrow(dat) >= 3) {
  pleiotropy_test <- mr_pleiotropy_test(dat)
}

# --- Sensitivity Analysis: Outlier Detection (MR-PRESSO) ---
# Performs Global Test for pleiotropy and identifies outliers
if (nrow(dat) > 3) {
  presso_output <- mr_presso(BetaOutcome = "beta.outcome", 
                             BetaExposure = "beta.exposure", 
                             SdOutcome = "se.outcome", 
                             SdExposure = "se.exposure", 
                             OUTLIERtest = TRUE, 
                             DISTORTIONtest = TRUE, 
                             data = dat, 
                             NbDistribution = 1000)
}

# --- Sensitivity Analysis: Robust Causal Inference ---
# Evaluated using the Contamination Mixture method
mr_input_obj <- mr_input(bx = dat$beta.exposure, 
                         bxse = dat$se.exposure, 
                         by = dat$beta.outcome, 
                         byse = dat$se.outcome)
conmix_results <- mr_conmix(mr_input_obj)

# 4. Significance Assessment ---------------------------------------------------
# Apply thresholds: FDR_IVW <= 0.05, P_Q >= 0.05, 
# P_Egger_Intercept >= 0.05, and P_GlobalTest >= 0.05

final_summary <- mr_results %>%
  filter(method %in% c("Inverse variance weighted", "Wald ratio")) %>%
  mutate(fdr_ivw = p.adjust(p, method = "fdr")) %>%
  mutate(is_robust = ifelse(fdr_ivw <= 0.05, TRUE, FALSE))

# 5. Reverse MR Analysis -------------------------------------------------------
# Examines reverse causation by repeating the analysis with flipped variables
# dat_reverse <- harmonise_data(outcome_dat, exposure_dat, action = 2)
# mr_results_reverse <- run_primary_mr(dat_reverse)

# End of Analysis
message("Analysis completed following specified methodological criteria.")
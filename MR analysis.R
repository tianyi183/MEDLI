# ------------------------------------------------------------------------------
# Mendelian Randomization (MR) Master Script
# ------------------------------------------------------------------------------
# This file implements the full MR analysis pipeline used in our study. The goal
# is to iterate over a large catalog of exposure summary statistics, harmonize
# each exposure with a fixed outcome GWAS, and run the appropriate MR methods
# depending on how many valid instruments (SNPs) survive QC. The script includes
# verbose logging and comments throughout so that collaborators can navigate the
# workflow without referring back to the original notebook.
# ------------------------------------------------------------------------------

suppressPackageStartupMessages({
  # Core MR and utility packages
  library(ieugwasr)               # Convenience wrappers for IEU-format data
  library(TwoSampleMR)            # Harmonization + MR estimators
  library(MRPRESSO)               # (placeholder) MR-PRESSO outlier test support
  library(MendelianRandomization) # Additional estimators such as ConMix
  library(metafor)                # Used to calculate I² from single-SNP MR
  library(tidyverse)              # General data manipulation helpers
  library(data.table)             # Fast I/O for large GWAS files
  library(R.utils)                # Miscellaneous utilities (not heavily used)
  library(stringr)                # String manipulation; ensures regex clarity
  library(openxlsx)               # Exporting clean Excel workbooks
})

# ------------------------------------------------------------------------------
# Configuration block
# ------------------------------------------------------------------------------
# Keeping file paths and key parameters in a single list makes it easy to
# rerun the pipeline in a different environment or share it with collaborators.
config <- list(
  outcome_path = "90th_pregwas.txt",  # Outcome GWAS summary stats
  exposure_dir = "UKB_all_LD",                     # Directory containing exposure files
  output_dir = "MR",                               # Base directory for Excel outputs
  bonferroni_alpha = 0.05 / 3000,                     # Family-wise error threshold
  final_outcome_label = "99th"                        # Label used in downstream tables
)

# Ensure the output directory exists so write.xlsx() never fails with
# "No such file or directory".
dir.create(config$output_dir, showWarnings = FALSE, recursive = TRUE)

# ------------------------------------------------------------------------------
# Helper: format odds ratios consistently
# ------------------------------------------------------------------------------
# Takes an MR results table with OR columns and appends a human-readable string
# such as "1.12(1.03,1.21)" for easy scanning in Excel.
format_or_table <- function(res_table) {
  res_table %>%
    mutate(
      OR = str_c(
        round(or, 3),
        "(",
        round(or_lci95, 3),
        ",",
        round(or_uci95, 3),
        ")"
      )
    )
}

# ------------------------------------------------------------------------------
# Helper: contamination-mixture estimator
# ------------------------------------------------------------------------------
# TwoSampleMR exposes mr_conmix() through MendelianRandomization but expects an
# mr_input object. This wrapper runs ConMix and returns both the formatted OR
# string and the associated p-value.
run_conmix <- function(dat, exposure_label, outcome_label) {
  mr_input_obj <- mr_input(
    bx = dat$beta.exposure,
    bxse = dat$se.exposure,
    by = dat$beta.outcome,
    byse = dat$se.outcome,
    snps = dat$SNP,
    exposure = exposure_label,
    outcome = outcome_label,
    effect_allele = dat$effect_allele.exposure,
    other_allele = dat$other_allele.exposure,
    eaf = dat$eaf.exposure
  )

  conmix <- mr_conmix(
    mr_input_obj,
    psi = 0,
    CIMin = NA,
    CIMax = NA,
    CIStep = 0.01,
    alpha = 0.05
  )

  list(
    effect = str_c(
      round(conmix@Estimate, 3),
      "(",
      round(conmix@CILower, 3),
      ",",
      round(conmix@CIUpper, 3),
      ")"
    ),
    pval = conmix@Pvalue
  )
}

# ------------------------------------------------------------------------------
# Helper: calculate I² to quantify residual heterogeneity
# ------------------------------------------------------------------------------
# The approach mirrors what is shown in the TwoSampleMR documentation: retain
# SNPs flagged as "mr_keep", run single-SNP MR, filter to rsIDs, and use
# metafor::rma with inverse-variance weights to obtain I².
extract_i2 <- function(dat) {
  dat_keep <- subset(dat, mr_keep)
  if (nrow(dat_keep) < 2) return(NA_real_)

  single <- mr_singlesnp(dat_keep, all_method = "mr_ivw")
  single <- single[grep("^rs", single$SNP), ]
  if (!nrow(single)) return(NA_real_)

  meta <- metafor::rma(
    yi = single$b,
    sei = single$se,
    weights = 1 / dat_keep$se.outcome^2,
    data = single,
    method = "DL"
  )
  meta$I2
}

# ------------------------------------------------------------------------------
# Helper: pretty log banners
# ------------------------------------------------------------------------------
# Overkill for most scripts, but extremely helpful when a job loops over
# hundreds of exposures—these markers make it easy to follow the progress.
log_section <- function(title) {
  cat("\n", strrep("-", 80), "\n", title, "\n", strrep("-", 80), "\n", sep = "")
}

# ------------------------------------------------------------------------------
# Load outcome data once (common target for all exposures)
# ------------------------------------------------------------------------------
log_section("Loading outcome summary statistics")
outcome_dt <- fread(config$outcome_path)
colnames(outcome_dt) <- c(
  "CHR",
  "POS",
  "effect_allele.outcome",
  "other_allele.outcome",
  "SNP",
  "p.value",
  "Z_score",
  "beta.outcome",
  "se.outcome",
  "MAF"
)

# ------------------------------------------------------------------------------
# Enumerate exposure files
# ------------------------------------------------------------------------------
# Each file is assumed to contain harmonizable columns in the same order. We
# stop immediately if the folder is empty to avoid producing blank Excel sheets.
exposure_files <- list.files(config$exposure_dir, full.names = TRUE)
if (!length(exposure_files)) {
  stop("No exposure files detected in ", config$exposure_dir)
}
cat("Identified", length(exposure_files), "exposure datasets\n")

# ------------------------------------------------------------------------------
# Storage containers for cumulative results
# ------------------------------------------------------------------------------
# These data frames accumulate MR outputs grouped by instrument count; they are
# later written to Excel. Naming parallels the original workflow.
mr_single_variant    <- data.frame()
mr_two_to_three      <- data.frame()
mr_four_plus         <- data.frame()
mr_four_plus_details <- data.frame()

# ------------------------------------------------------------------------------
# Main loop over exposure files
# ------------------------------------------------------------------------------
for (idx in seq_along(exposure_files)) {
  exposure_file <- exposure_files[[idx]]
  exposure_label <- strsplit(basename(exposure_file), ".txt", fixed = TRUE)[[1]][1]
  cat(sprintf("\n[%03d/%03d] %s\n", idx, length(exposure_files), exposure_label))

  try({
    # --------------------
    # Load exposure data
    # --------------------
    exposure_dt <- fread(exposure_file)
    colnames(exposure_dt) <- c(
      "CHR",
      "POS",
      "other_allele.exposure",
      "effect_allele.exposure",
      "eaf",
      "beta.exposure",
      "se.exposure",
      "pvalue.exposure",
      "SNP"
    )

    # --------------------
    # Retain overlapping SNPs
    # --------------------
    overlap_outcome <- subset(outcome_dt, SNP %in% exposure_dt$SNP)
    overlap_outcome <- subset(overlap_outcome, p.value > 0.05)
    if (!nrow(overlap_outcome)) {
      cat("  No overlapping SNPs after p-value filtering; skipping\n")
      next
    }

    exposure_dt <- subset(exposure_dt, SNP %in% overlap_outcome$SNP)
    if (!nrow(exposure_dt)) {
      cat("  Overlap lost after filtering; skipping\n")
      next
    }

    # --------------------
    # Annotate with IDs used by TwoSampleMR
    # --------------------
    overlap_outcome$id.outcome <- config$final_outcome_label
    overlap_outcome$outcome <- config$final_outcome_label
    exposure_dt$id.exposure <- exposure_label
    exposure_dt$exposure <- exposure_label

    # --------------------
    # Harmonize alleles and effect directions
    # --------------------
    harmonised <- harmonise_data(exposure_dt, overlap_outcome)
    harmonised$se.outcome <- as.numeric(harmonised$se.outcome)

    if (!nrow(harmonised)) {
      cat("  Harmonization produced empty dataset; skipping\n")
      next
    }

    # --------------------
    # Branch logic based on number of instruments
    # --------------------
    if (nrow(harmonised) == 1) {
      # Single instrument -> Wald ratio
      res_wald <- mr(harmonised, method_list = "mr_wald_ratio")
      mr_single_variant <- bind_rows(mr_single_variant, generate_odds_ratios(res_wald))
      next
    }

    if (nrow(harmonised) <= 3) {
      # Small instrument set (2-3 SNPs) -> IVW (fixed effects) plus diagnostics
      res_ivw <- mr(harmonised, method_list = "mr_ivw_fe")
      or_table <- format_or_table(generate_odds_ratios(res_ivw))

      conmix <- run_conmix(harmonised, exposure_label, config$final_outcome_label)
      pleio <- mr_pleiotropy_test(harmonised)
      hetero <- mr_heterogeneity(harmonised)
      i2 <- extract_i2(harmonised)

      summary_row <- cbind(
        or_table[, c("exposure", "outcome", "nsnp", "b", "se", "pval", "OR")],
        conmix_effect = conmix$effect,
        conmix_pval = conmix$pval,
        egger_intercept = str_c(round(pleio$egger_intercept, 3), "(", pleio$pval, ")"),
        heterogeneity = str_c(round(hetero$Q[[1]], 3), "(", hetero$Q_pval[[1]], ")"),
        I2 = i2
      )
      mr_two_to_three <- bind_rows(mr_two_to_three, summary_row)
      next
    }

    # Larger instrument sets allow the full suite of estimators.
    res_ivw     <- mr(harmonised, method_list = "mr_ivw")
    res_wmedian <- mr(harmonised, method_list = "mr_weighted_median")
    res_egger   <- mr(harmonised, method_list = "mr_egger_regression")
    res_wmode   <- mr(harmonised, method_list = "mr_weighted_mode")

    or_ivw <- format_or_table(generate_odds_ratios(res_ivw))
    or_median <- generate_odds_ratios(res_wmedian)[, c("b", "se", "pval")]

    conmix <- run_conmix(harmonised, exposure_label, config$final_outcome_label)
    pleio  <- mr_pleiotropy_test(harmonised)
    hetero <- mr_heterogeneity(harmonised)
    i2     <- extract_i2(harmonised)

    mr_four_plus <- bind_rows(
      mr_four_plus,
      cbind(
        or_ivw[, c("exposure", "outcome", "nsnp", "b", "se", "pval", "OR")],
        egger_b = res_egger$b,
        egger_se = res_egger$se,
        egger_p = res_egger$pval,
        median_b = or_median$b,
        median_se = or_median$se,
        median_p = or_median$pval,
        mode_b = res_wmode$b,
        mode_se = res_wmode$se,
        mode_p = res_wmode$pval,
        mr_presso_beta = NA,
        mr_presso_se = NA,
        mr_presso_pval = NA,
        mr_presso_global = NA,
        conmix_effect = conmix$effect,
        conmix_pval = conmix$pval,
        egger_intercept = str_c(round(pleio$egger_intercept, 3), "(", pleio$pval, ")"),
        heterogeneity = str_c(
          round(hetero$Q[[1]], 3),
          "(",
          format(hetero$Q_pval[[1]], scientific = TRUE, digits = 4),
          ")"
        ),
        I2 = i2
      )
    )

    mr_four_plus_details <- bind_rows(
      mr_four_plus_details,
      cbind(
        or_ivw[, c("exposure", "outcome", "nsnp", "b", "se", "pval", "OR")],
        OR_with_p = str_c(
          sprintf("%.3f", or_ivw$or),
          "(",
          format(or_ivw$pval, scientific = TRUE, digits = 4),
          ")"
        ),
        heterogeneity_p = hetero$Q_pval[[1]]
      )
    )
  })
}

# ------------------------------------------------------------------------------
# Export results to Excel for downstream review
# ------------------------------------------------------------------------------
log_section("Writing results to Excel workbooks")
write.xlsx(mr_single_variant,    file.path(config$output_dir, "90th_UKBALL_twoMR_single_variant.xlsx"))
write.xlsx(mr_two_to_three,      file.path(config$output_dir, "90th_UKBALL_twoMR_two_to_three.xlsx"))
write.xlsx(mr_four_plus,         file.path(config$output_dir, "90th_UKBALL_twoMR_four_plus.xlsx"))
write.xlsx(mr_four_plus_details, file.path(config$output_dir, "90th_UKBALL_twoMR_four_plus_details.xlsx"))

# Highlight the most promising signals by Bonferroni threshold and sanity-check
# that Egger intercept p-values are acceptable (> 0.05 means no strong evidence
# of directional pleiotropy).
priority_hits <- subset(mr_four_plus, pval < config$bonferroni_alpha)
priority_hits$egger_p <- str_extract(priority_hits$egger_intercept, "(?<=\\().+?(?=\\))")
priority_hits <- subset(priority_hits, as.numeric(priority_hits$egger_p) > 0.05)

write.xlsx(priority_hits, file.path(config$output_dir, "90th_UKBALL_twoMR_priority_hits.xlsx"))
cat("\nPipeline completed successfully.\n")

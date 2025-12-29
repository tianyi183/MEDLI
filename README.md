# MEDLI

> **M**endelian Randomization → **E**xplainable Mediation → **D**isease & trait-wise ML → **L**ongevity score → **I**nteractive LLM guidance. A single repo that carries the project from raw Olink NPX proteomics through causal inference, model validation, and into a production-ready health advisory experience.

**Highlights**
- End-to-end reproducibility: R pipelines for data hygiene, MR, mediation, modeling, and validation live beside the Python/JS stack that serves predictions to end users.
- Evidence-grounded personalization: 1,686 MR-derived causal triplets feed both LightGBM ensembles and a retrieval-augmented LLM that cites DOI/PMID links.
- Ops-ready tooling: scripts cover PDF publishing, OCR cleanup, CLI/REST inference, user auth flows, and QLoRA-based model fine-tuning.

## System Blueprint

```text
┌──────────────┐   ┌───────────────────────┐   ┌─────────────────────┐   ┌──────────────────────┐   ┌───────────────────┐
│ Proteomics & │   │ MR + Mediation (R)    │   │ Mediation-aware ML  │   │ Validation + Scoring │   │ Advisory surfaces  │
│ Follow-up    │──▶│ (MR, delta, scaling)  │──▶│ (caret, LightGBM)   │──▶│ (survival, aging)    │──▶│ (LLM, web portal) │
└──────────────┘   └───────────────────────┘   └─────────────────────┘   └──────────────────────┘   └───────────────────┘
                                                             ▲
                                                             │
                                     Longevity scripts (Flask/Node/HTML/LLM utilities) bring the models to life.
```

## Repository Map

| Path | Purpose | Notes |
| --- | --- | --- |
| [`Individual-level proteomic, demographic, and longitudinal follow-up data.R`](<Individual-level proteomic, demographic, and longitudinal follow-up data.R>) | Cleans Olink NPX proteomics, imputes with `miceforest`, enriches with demographics + ICD-10 follow-up | Includes helper to compute decimal age, censoring by UK region, and `prepare_individual_level_data()` workflow |
| [`MR and sensitivity analysis.R`](<MR and sensitivity analysis.R>) | Core MR orchestration (IVW, Wald ratio, MR-Egger) + heterogeneity, pleiotropy, MR-PRESSO, contamination mixture | Assumes `TwoSampleMR`, `MRPRESSO`, `MendelianRandomization`, `metafor` |
| [`Mediation analysis.R`](<Mediation analysis.R>) | Two-step MR mediation with delta-method scaling, proportional adjustment when Σ|indirect|>1, FDR control | Returns tidy tibble with raw/scaled effects, CIs, and binary/continuous specific reporting |
| [`Mediation-informed machine learning modeling framework.R`](<Mediation-informed machine learning modeling framework.R>) | Trains 30 caret algorithms, disease-wise models, modifiable-trait pathways, and health-potential scores | Produces orchestrated list with best base learner, disease models, trait scores |
| [`Modeling performance validation.R`](<Modeling performance validation.R>) | Validates survival and incidence via KM curves plus biological-age correlations (KDM BA & PhenoAge) | Bundles plotting helpers and spline-based score-vs-age analysis |
| [`Personalized health advisory LLM system.py`](<Personalized health advisory LLM system.py>) | Retrieval-augmented generation: BM25 + monoT5 re-rank + weighted evidence feeding a Kimi-KK prompt builder | Provides `EvidenceFragment`, `KnowledgeBase`, and `generate_personalized_advice()` |
| [`Longevity 脚本/app(lightGBM使用原脚本).py`](<Longevity 脚本/app(lightGBM使用原脚本).py>) | Flask service for batch LightGBM inference across 17+ boosters with upload handling and summary stats | Handles CSV/Excel uploads, auto feature alignment, multi-model predictions |
| [`Longevity 脚本/predict_cli(调用lightGBM).py`](<Longevity 脚本/predict_cli(调用lightGBM).py>) | Thin CLI over `app.py` for offline inference + JSON output | Ideal for scripting / cron jobs |
| [`Longevity 脚本/server(后端).js`](<Longevity 脚本/server(后端).js>) | Node/Express backend (login, report orchestration, PDF generation, RAG triggers) | Integrates OpenAI/Moonshot APIs, MySQL auth, Multer uploads, PDF + LightGBM pipelines |
| [`Longevity 脚本/chat (对话界面).html`](<Longevity 脚本/chat (对话界面).html>), [`index(登录).html`](<Longevity 脚本/index(登录).html>), [`register(注册).html`](<Longevity 脚本/register(注册).html>) | Front-end assets: chat UI, login, registration pages themed for the Longevity portal | Designed to talk to the Express backend |
| [`Longevity 脚本/pdfGeneration (pdf生成).py`](<Longevity 脚本/pdfGeneration (pdf生成).py>) | Converts structured JSON into a polished health report via WeasyPrint with gradients, score tables, timelines | Includes fixed-layout HTML/CSS template |
| [`Longevity 脚本/data_cleaning_local_v2(微调数据清理脚本).py`](<Longevity 脚本/data_cleaning_local_v2(微调数据清理脚本).py>) | OCR-cleaning pipeline that calls a local Ollama LLM to redact noise and create structured reports | Requires `requests`, `tqdm`, and an accessible Ollama endpoint |
| [`Longevity 脚本/train_qlora(微调).py`](<Longevity 脚本/train_qlora(微调).py>) | QLoRA trainer with BitsAndBytes config, PEFT, chat-template preprocessing, multi-GPU support | Reads settings from `config.yaml`, uses HuggingFace datasets/transformers |
| [`Longevity 脚本/混淆实验报告.py`](<Longevity 脚本/混淆实验报告.py>) | Batch-converts “user feedback + dialogue” text files into Markdown reports via Moonshot/Kimi API | Accepts CLI args for folders, model choice, limits |
| [`LICENSE`](<LICENSE>) | MIT License | Applies to the whole repo |
| [`README.md`](<README.md>) | You're reading it | Serves as the GitHub landing page |

## Getting Started

### Prerequisites
- **R 4.3+** with packages: `dplyr`, `lubridate`, `miceforest`, `purrr`, `recipes`, `rsample`, `yardstick`, `caret`, `survival`, `survminer`, `ggplot2`, `splines`, `TwoSampleMR`, `MRPRESSO`, `MendelianRandomization`, `metafor`.
- **Python 3.10+** virtual environment with `pandas`, `lightgbm`, `flask`, `werkzeug`, `weasyprint`, `requests`, `tqdm`, `pyyaml`, `transformers`, `datasets`, `accelerate`, `bitsandbytes`, `peft`.
- **Node.js 18+** for `Longevity 脚本/server(后端).js` (`express`, `mysql2`, `dotenv`, `multer`, `axios`, `openai`, etc.).
- Access tokens: GitHub PAT (already configured), optional OpenAI + Moonshot (Kimi) keys, Ollama endpoint if running LLMs locally.

### R analytics quickstart

```r
# From repo root
renv::init(bare = TRUE)        # optional
install.packages(c("dplyr","lubridate","miceforest","caret","survival","TwoSampleMR","MRPRESSO"))

source("Individual-level proteomic, demographic, and longitudinal follow-up data.R")
source("Mediation analysis.R")
source("Mediation-informed machine learning modeling framework.R")

processed <- prepare_individual_level_data(proteomic_df, demographics_df, followup_df)
mediation_results <- run_mediation_analysis(mediation_input_df)
framework <- build_framework(survival_df, disease_df, mod_trait_df, protein_cols)
```

### Longevity web stack quickstart

```bash
# Python services
python -m venv .venv && .\.venv\Scripts\activate
pip install -r requirements.txt  # create one or install the libs mentioned above
python "Longevity 脚本/app(lightGBM使用原脚本).py" &
python "Longevity 脚本/pdfGeneration (pdf生成).py"  # to test template rendering

# Node backend
cd "Longevity 脚本"
npm install
node "server(后端).js"
```

Configure environment variables for the Node service (`OPENAI_API_KEY`, `KIMI_API_KEY`, `MYSQL_*`, `PDF_GENERATION_PATH`, etc.) before launching.

## Module Deep Dive & Usage Examples

### 1. Individual-level data pipeline (`Individual-level proteomic, demographic, and longitudinal follow-up data.R`)
- Filters NPX proteins to ≤30% missingness, performs single-imputation (`miceforest::impute`), and fuses demographic + follow-up data with region-aware censoring.
- Example:

```r
proteomic <- readr::read_csv("data/npx.csv")
demo <- readr::read_csv("data/demographics.csv") %>%
  mutate(recruitment_date = as.Date(recruitment_date))
follow_up <- readr::read_csv("data/follow_up.csv") %>%
  mutate(event_date = as.Date(event_date))

individual_df <- prepare_individual_level_data(proteomic, demo, follow_up)
```

### 2. MR + mediation analytics (`MR and sensitivity analysis.R`, `Mediation analysis.R`)
- `run_primary_mr()` automatically swaps Wald ratio / IVW FE / IVW RE depending on IV count, then attaches MR-Egger, heterogeneity, pleiotropy, MR-PRESSO, and contamination mixture outputs.
- `run_mediation_analysis()` returns scaled indirect effects with binary vs continuous reporting scales and FDR.

```r
harmonised <- harmonise_data(exposure_dat, outcome_dat, action = 2)
mr_summary <- run_primary_mr(harmonised)

mediators <- tibble::tibble(
  protein_id = c("P1","P1","P2"),
  mediator_id = c("BMI","T2D","Smoking"),
  beta_protein_mediator = c(0.10,0.06,-0.08),
  se_protein_mediator = c(0.02,0.03,0.025),
  beta_mediator_longevity = c(-0.12,0.20,0.15),
  se_mediator_longevity = c(0.04,0.05,0.06),
  outcome_type = c("continuous","binary","binary")
)
mediation_table <- run_mediation_analysis(mediators)
```

### 3. Mediation-informed ML & validation (`Mediation-informed machine learning modeling framework.R`, `Modeling performance validation.R`)
- Evaluates 30 caret learners, spins up per-disease classifiers, computes modifiable-trait pathway scores, and rescales survival probabilities to a 40–100 Health-Potential Score.
- Validation scripts render KM curves, incidence plots, and correlations vs KDM BA / PhenoAge.

```r
framework <- build_framework(survival_df, disease_df, mod_trait_df, protein_cols)
validation <- run_validation(
  df_survival = framework$survival_predictions,
  df_disease_list = disease_incidence_list,
  aging_df = aging_markers_df,
  kdm_biomarkers = c("sbp","fev1","crp"),
  pheno_biomarkers = c("albumin","creatinine","glucose","crp","wbc"),
  pheno_coefficients = pheno_coefs,
  pheno_intercept = pheno_intercept
)
```

### 4. Personalized advisory LLM (`Personalized health advisory LLM system.py`)
- Hybrid retrieval (BM25 + monoT5), evidence weighting, and a structured prompt builder for a three-stage constrained chain-of-thought.

```python
import importlib.util, pathlib

spec = importlib.util.spec_from_file_location(
    "medli_llm",
    pathlib.Path("Personalized health advisory LLM system.py")
)
medli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(medli)

fragments = [
    medli.EvidenceFragment("F1", "Protein X reduces T2D risk by 12%", "10.1001/jama.12345",
                           "PMID123", 2024, "prospective cohort", "randomized", 18.4,
                           "metabolic", "BMI")
]
kb = medli.KnowledgeBase(fragments)
kimi = medli.KimiKKClient(model_path="kimi-kk-local")

model_outputs = {
    "top_proteins": ["Protein X", "Protein Y"],
    "diseases": ["type 2 diabetes"],
    "modifiable_traits": ["BMI", "waist circumference"],
    "health_potential": 87.3
}
report = medli.generate_personalized_advice(
    individual_info={"age": 52, "sex": "female"},
    model_outputs=model_outputs,
    kb=kb,
    kimi_client=kimi
)
print(report)
```

### 5. Longevity services & UI (`Longevity 脚本/*`)
- **Inference**: `app(lightGBM使用原脚本).py` exposes `/api/login` for CSV/Excel uploads, applies LightGBM boosters, and streams per-model predictions plus a summary.
  ```bash
  python "Longevity 脚本/predict_cli(调用lightGBM).py" ./samples/proteins.xlsx > predictions.json
  ```
- **Backend glue**: `server(后端).js` orchestrates uploads, auth (bcrypt + MySQL), triggers LightGBM CLI, PDF generation, and calls remote RAG/LLM services. Configure `.env` with OpenAI or Moonshot keys and RAG script paths.
- **Front-end**: `index(登录).html`, `register(注册).html`, and `chat (对话界面).html` deliver login/registration forms and a polished conversation surface that consumes the Express APIs.
- **Document pipeline**: `pdfGeneration (pdf生成).py` transforms JSON payloads into A4 PDFs with gradients, score tables, and recommendations (requires WeasyPrint).
  ```bash
  python "Longevity 脚本/pdfGeneration (pdf生成).py" input.json output/report.pdf
  ```

### 6. Data/LLM utilities
- `data_cleaning_local_v2(微调数据清理脚本).py`: ingests OCR’d checkup text, calls an Ollama model (e.g., `qwen2.5:7b`), enforces anonymization, and writes JSONL.
- `train_qlora(微调).py`: loads config, tokenizes chat data, applies QLoRA (BitsAndBytes + PEFT), and launches training; run `python train_qlora(微调).py --config configs/qlora.yaml`.
- `混淆实验报告.py`: generates Markdown “confusion experiment” reports straight from user-feedback text sets using Moonshot’s chat API; accepts `--input-dir`, `--output-dir`, `--model`, `--limit`.

## Putting It All Together
1. **Data readiness** – run `prepare_individual_level_data()` on proteomics + demographics, then harmonize MR inputs and compute mediation tables.
2. **Model training** – call `build_framework()` to pick the best classifier, produce disease/trait scores, and export the Health-Potential Score distribution.
3. **Validation** – execute `run_validation()` to benchmark against survival endpoints and biological aging biomarkers.
4. **Advisory generation** – feed the modeling outputs into `generate_personalized_advice()` to obtain evidence-cited guidance.
5. **User delivery** – deploy the LightGBM Flask app, Express backend, HTML front end, PDF generator, and (optionally) the QLoRA fine-tuned advisor.

## License

Distributed under the MIT License (see `LICENSE`). Feel free to reuse individual modules—just retain attribution and mind any upstream dataset/LLM licensing.

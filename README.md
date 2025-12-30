# MEDLI: Longevity Analytics & Advisory Stack

MEDLI bundles the full workflow from proteomic data preparation through Mendelian randomization (MR), mediation-aware machine learning, validation, and a production-facing advisory stack (API + PDF + LLM). This README points to the current code under `D:\MR_code` with clickable links.

## Repository Structure

| Path | What it does |
| --- | --- |
| [`Individual-level proteomic, demographic, and longitudinal follow-up data.R`](Individual-level proteomic, demographic, and longitudinal follow-up data.R) | Cleans Olink NPX proteomics, merges demographics/follow-up, handles missingness. |
| [`MR analysis.R`](MR analysis.R) | MR orchestration (Wald ratio, IVW, Egger), heterogeneity, pleiotropy, I², contamination-mixture; main automated pipeline. |
| [`MR and sensitivity analysis.R`](MR and sensitivity analysis.R) | Additional MR routines with sensitivity tests and diagnostics. |
| [`Mediation analysis.R`](Mediation analysis.R) | Two-step MR mediation with scaling, FDR control, binary/continuous reporting. |
| [`Mediation-informed machine learning modeling framework.R`](Mediation-informed machine learning modeling framework.R) | Trains/evaluates multiple learners, disease-wise models, modifiable-trait pathways. |
| [`Modeling performance validation.R`](Modeling performance validation.R) | Survival/incidence validation, KM curves, biological-age correlations. |
| [`app_lightgbm_service.py`](app_lightgbm_service.py) | LightGBM inference service for batch scoring via REST. |
| [`predict_cli.py`](predict_cli.py) | CLI wrapper for LightGBM batch predictions. |
| [`pdf_generation.py`](pdf_generation.py) | Converts structured text to PDF health reports (WeasyPrint). |
| [`report_generator.py`](report_generator.py) | Utilities to assemble narrative reports from model outputs. |
| [`server_backend.js`](server_backend.js) | Node/Express backend for uploads, auth, report orchestration, PDF download. |
| [`Personalized health advisory LLM system.py`](Personalized health advisory LLM system.py) | Retrieval + prompt builder for personalized advice (Kimi/OpenAI compatible). |
| [`LICENSE`](LICENSE) | MIT License for the repository. |

## Prerequisites

- **R 4.3+** with: `TwoSampleMR`, `MRPRESSO`, `MendelianRandomization`, `metafor`, `caret`, `survival`, `ggplot2`, `tidyverse`, `data.table`, `openxlsx`.
- **Python 3.10+** with: `pandas`, `numpy`, `lightgbm`, `flask`, `weasyprint`, `requests`, `tqdm`, `pyyaml`, `transformers`, `datasets`, `accelerate`, `bitsandbytes`, `peft`.
- **Node.js 18+** with: `express`, `multer`, `mysql2`, `dotenv`, `axios`, `openai`/`moonshot` SDKs.
- Access to required API keys (OpenAI and/or Kimi) and a MySQL instance if you enable the backend.

## Quickstart (Analytics)

1. Clone/open the repo:
   ```bash
   cd D:/MR_code
   ```
2. Install R dependencies (example):
   ```r
   install.packages(c("TwoSampleMR","MRPRESSO","MendelianRandomization","metafor",
                      "caret","survival","ggplot2","tidyverse","data.table","openxlsx"))
   ```
3. Run the MR pipeline:
   ```r
   source("MR analysis.R")  # adjust config paths inside the script as needed
   ```
4. Run mediation and modeling:
   ```r
   source("Mediation analysis.R")
   source("Mediation-informed machine learning modeling framework.R")
   source("Modeling performance validation.R")
   ```

## Quickstart (Services)

### LightGBM inference (Python)
```bash
python -m venv .venv && .\.venv\Scripts\activate
pip install pandas numpy lightgbm flask weasyprint requests tqdm
python app_lightgbm_service.py        # REST service
python predict_cli.py input.csv > predictions.json   # CLI batch scoring
```

### PDF generation (Python)
```bash
python pdf_generation.py input.txt output/report.pdf
```

### Backend API (Node)
```bash
cd D:/MR_code
npm install
node server_backend.js
```
Set environment variables for `OPENAI_API_KEY`, `KIMI_API_KEY`, `MYSQL_*`, and any paths consumed by `server_backend.js`.

## Personalized Advisory LLM

Use [`Personalized health advisory LLM system.py`](Personalized health advisory LLM system.py) to build evidence-grounded prompts that combine model outputs with retrieved literature:
```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("medli_llm", pathlib.Path("Personalized health advisory LLM system.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
# Build knowledge base and generate advice (see script for full API)
```

## Data Notes

- Paths in the R scripts point to local drives (e.g., `D:/MR/...`, `X:/UKB_all_LD`). Update them to match your environment.
- Ensure proteomics/demographic/follow-up files conform to the column expectations described in the data-prep script.

## Output Artifacts

- MR/mediation/modeling results: written as Excel workbooks under `D:/MR` (see file names inside each script).
- Service outputs: JSON predictions (LightGBM CLI), PDF reports (`pdf_generation.py`), and HTTP responses from `server_backend.js`.

## License

This repository is distributed under the MIT License (see [`LICENSE`](LICENSE)). Be mindful of any upstream data or model licensing when deploying the services.

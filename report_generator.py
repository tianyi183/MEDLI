#!/usr/bin/env python3
"""Batch-generate personalized Markdown reports from feedback + dialog transcripts."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_MODEL = "kimi-k2-0905-preview"
DEFAULT_TEMPERATURE = 0.4
DEFAULT_MAX_TOKENS = 2000

DISEASE_CANDIDATES: List[str] = [
    "Thyroid toxicosis",
    "Type 1 diabetes mellitus",
    "Type 2 diabetes mellitus",
    "Obesity",
    "Electrolyte and acid-base imbalance",
    "Hypertensive heart disease",
    "Angina pectoris",
    "Acute myocardial infarction",
    "Chronic ischemic heart disease",
    "Other pulmonary heart disease",
    "Atherosclerosis",
    "Seropositive rheumatoid arthritis",
    "Systemic lupus erythematosus",
    "Other connective tissue disorders",
    "Chronic kidney failure",
    "Other male genital disorders",
    "Non-inflammatory uterine disorders",
]


def load_text_with_fallback(path: Path) -> str:
    """Read text using several encodings until one works."""
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return path.read_text(encoding="utf-8")


def split_sections(text: str) -> List[Tuple[str, str]]:
    """
    Split the document by the `===== SECTION =====` pattern.

    Returns a list of tuples (section_title, section_body).
    Titles are normalized to uppercase for easier matching.
    """
    parts = re.split(r"(===== .*? =====)", text)
    sections: List[Tuple[str, str]] = []
    for i in range(1, len(parts), 2):
        title = parts[i].strip("= ").strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections.append((title.upper(), body.strip()))
    return sections


def extract_required_chunks(sections: Sequence[Tuple[str, str]]) -> Tuple[str, str]:
    """
    Identify the "user feedback" and "patient dialog" sections.
    Falls back to the first two sections if explicit labels are missing.
    """
    feedback = ""
    dialog = ""
    for title, body in sections:
        if not feedback and ("FEEDBACK" in title or "USER" in title):
            feedback = body
        elif not dialog and ("DIALOG" in title or "CONVERSATION" in title):
            dialog = body
    if not feedback and sections:
        feedback = sections[0][1]
    if not dialog and len(sections) > 1:
        dialog = sections[1][1]
    if not feedback or not dialog:
        raise RuntimeError(
            "Unable to identify both feedback and dialog sections. "
            "Ensure the transcript contains at least two `===== SECTION =====` blocks."
        )
    return feedback, dialog


def ensure_unique_path(path: Path) -> Path:
    """Return a unique path by adding (n) suffixes when needed."""
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def resolve_base_url() -> str:
    """Prefer MOONSHOT_BASE_URL, otherwise default to the global endpoint."""
    return os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1").rstrip("/")


def http_post_json(
    endpoint: str,
    payload: Dict,
    api_key: str,
    timeout: int,
    debug: bool,
) -> Dict:
    """Send a JSON POST request and return the decoded response."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(endpoint, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if debug:
                print(f"[DEBUG] POST {endpoint} -> {getattr(response, 'status', 200)}")
                print(f"[DEBUG] Response preview: {raw[:1000]}")
            return json.loads(raw)
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTPError {exc.code}: {exc.reason}. Body={detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Unexpected error: {exc}") from exc


def call_kimi_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    timeout: int,
    debug: bool,
    max_tokens: int,
) -> str:
    """Invoke the Moonshot chat completion endpoint."""
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    obj = http_post_json(endpoint, payload, api_key, timeout, debug)
    try:
        return obj["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise RuntimeError(
            f"Malformed response: {json.dumps(obj, ensure_ascii=False)[:1000]}"
        ) from exc


SYSTEM_PROMPT_TEMPLATE = """You are a board-certified preventive-medicine physician.
Always reference only the provided user feedback, clinician conversation, and disease-risk candidates.
Current timestamp: {timestamp}.

Output layout:
- Title line: `Health Management Report - Generated at YYYY/MM/DD HH:MM:SS`
- Section order (Markdown headings must remain exactly as written):
  ## Personalized Health Management Report
  ### Overall Summary
  ### Detailed Analysis
  #### 1. Diet Habits Analysis
  #### 2. Exercise Habits Analysis
  ### Personalized Recommendations
  ### Summary and Encouragement

Detailed Analysis requirements:
- Reference the actual diet and exercise information found in the transcripts.
- Use concise prose, highlight key phrases with **bold** when necessary, and avoid invented numbers.
- Each subsection must end with a one-sentence synthesis such as
  "Considering your situation, ...".

Personalized Recommendations requirements:
- Create one subsection per medium- or high-risk disease.
- Heading format: `#### For {disease_name} (High Risk|Medium Risk)`
- First sentence inside each subsection must be `Your risk of {disease_name} is HIGH|MEDIUM`.
- Provide at least three actionable recommendations per disease.
- Each recommendation must follow `[n] Recommendation text; | Reasoning: brief justification`.

Summary and Encouragement:
- Encourage adherence, emphasize medical consultation when symptoms persist,
  and avoid diagnostic statements.
"""


def build_system_prompt(now_str: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(timestamp=now_str)


def build_user_prompt(
    disease_candidates: Sequence[str],
    feedback_text: str,
    dialog_text: str,
) -> str:
    candidate_block = "\n".join(f"- {name}" for name in disease_candidates)
    return f"""The source document contains two parts:
[USER_FEEDBACK]
{feedback_text}

[PATIENT_DIALOG]
{dialog_text}

Task:
1. Use only the information above to infer diet habits, exercise habits, and disease risks.
2. Limit the narrative to the disease list below; select all items whose risk is not negligible.
3. Produce the Markdown report described in the system instructions.

Disease candidates:
{candidate_block}

Validation rules before responding:
- The title line must match the timestamp provided by the system message.
- Every section and subsection listed in the layout must appear exactly once.
- Each personalized recommendation subsection must contain at least three
  `[n] Recommendation; | Reasoning: ...` entries.
"""


def generate_report_for_file(
    *,
    txt_path: Path,
    output_dir: Path,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float,
    debug: bool,
    max_tokens: int,
) -> Path:
    """Generate a Markdown report for a single transcript file."""
    raw_text = load_text_with_fallback(txt_path)
    sections = split_sections(raw_text)
    feedback, dialog = extract_required_chunks(sections)

    timestamp_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    system_prompt = build_system_prompt(timestamp_str)
    user_prompt = build_user_prompt(DISEASE_CANDIDATES, feedback, dialog)

    markdown = call_kimi_chat(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        timeout=120,
        debug=debug,
        max_tokens=max_tokens,
    )

    output_name = f"{txt_path.stem}_report.txt"
    output_path = ensure_unique_path(output_dir / output_name)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def natural_key(path: Path) -> int:
    """Sort helper: extract the first integer from the filename."""
    match = re.search(r"(\d+)", path.stem)
    return int(match.group(1)) if match else 10**9


def run_cli() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Markdown health reports from feedback + dialog transcripts."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing *_with_feedback.txt files.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where generated reports will be written.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=35,
        help="Maximum number of files to process (default: 35).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model identifier (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f"Generation temperature (default: {DEFAULT_TEMPERATURE}).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Maximum tokens per completion (default: {DEFAULT_MAX_TOKENS}).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug payloads and response previews.",
    )
    args = parser.parse_args()

    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        raise SystemExit(
            "Environment variable MOONSHOT_API_KEY is required. "
            "Set it to your Moonshot (Kimi) token."
        )

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    if not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    files = [p for p in input_dir.glob("*.txt") if not p.name.endswith("_report.txt")]
    files.sort(key=natural_key)
    if not files:
        raise SystemExit("No .txt files found in the input directory.")

    base_url = resolve_base_url()
    processed = 0
    for txt_file in files:
        if processed >= args.limit:
            break
        try:
            output_path = generate_report_for_file(
                txt_path=txt_file,
                output_dir=output_dir,
                base_url=base_url,
                api_key=api_key,
                model=args.model,
                temperature=args.temperature,
                debug=args.debug,
                max_tokens=args.max_tokens,
            )
            print(f"[OK] {txt_file.name} -> {output_path.name}")
            processed += 1
        except Exception as exc:
            print(f"[FAIL] {txt_file.name}: {exc}")

    print(f"Completed {processed} file(s); limit was {args.limit}.")


if __name__ == "__main__":
    run_cli()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量读取 “用户不适反馈 + 患者对话记录” 的文本，调用 Kimi 生成 Markdown 医疗报告。

输入：--input-dir  指向 *_with_feedback.txt 所在的文件夹
输出：--output-dir 指向报告输出文件夹（自动创建；不覆盖已有文件）
限制：--limit      最多处理多少个文件（默认 35）
模型：--model      默认 kimi-k2-0905-preview（OpenAI 兼容 /v1/chat/completions）

鉴权：
  必填环境变量：MOONSHOT_API_KEY
  可选环境变量：MOONSHOT_BASE_URL（默认 https://api.moonshot.ai/v1；中国区可设 https://api.moonshot.cn/v1）

示例（Windows PowerShell）：
  $env:MOONSHOT_API_KEY = "sk-xxxxxxxx"
  # （可选）$env:MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
  python gen_reports_from_feedback.py `
    --input-dir "D:\report_out_withfeedback" `
    --output-dir "D:\report_out_reports" `
    --limit 35 `
    --model kimi-k2-0905-preview `
    --temperature 0.4 `
    --debug

脚本不会使用本地兜底文案；若 API 失败会直接报错，方便你确认联通性。
"""
import os
import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DEFAULT_MODEL = "kimi-k2-0905-preview"

DISEASE_CANDIDATES = [
    "甲状腺毒症",
    "胰岛素依赖型糖尿病",
    "非胰岛素依赖型糖尿病",
    "肥胖症",
    "其他体液、电解质及酸碱平衡紊乱",
    "高血压性心脏病",
    "心绞痛",
    "急性心肌梗死",
    "慢性缺血性心脏病",
    "其他肺源性心脏病",
    "动脉粥样硬化",
    "血清阳性型类风湿性关节炎",
    "系统性红斑狼疮",
    "结缔组织其他系统性病变",
    "慢性肾功能衰竭",
    "男性生殖器官其他疾病",
    "子宫其他非炎症性病变（宫颈除外）",
]

def load_text_with_fallback(p: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return p.read_text(encoding=enc)
        except Exception:
            continue
    return p.read_text(encoding="utf-8")

def parse_sections(text: str) -> dict:
    """解析以 '===== 标题 =====' 分隔的两段：用户不适反馈 / 患者对话记录"""
    sections = {}
    parts = re.split(r"(===== .*? =====)", text)
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        content = parts[i+1] if i+1 < len(parts) else ""
        sections[title] = content.strip()
    return sections

def ensure_unique_path(p: Path) -> Path:
    """若目标已存在，则在文件名后追加 (1)、(2)… 防止覆盖"""
    if not p.exists():
        return p
    i = 1
    while True:
        cand = p.with_name(f"{p.stem}({i}){p.suffix}")
        if not cand.exists():
            return cand
        i += 1

def _resolve_base_url() -> str:
    return (
        os.getenv("MOONSHOT_BASE_URL")
        or "https://api.moonshot.cn/v1"
    )

def _http_post_json(endpoint: str, payload: dict, api_key: str, timeout: int = 90, debug: bool = False) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(endpoint, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if debug:
                print(f"[DEBUG] status={getattr(resp, 'status', '200')} length={len(raw)}")
                print(f"[DEBUG] body.head={raw[:2000]}")
            return json.loads(raw)
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTPError {e.code} {e.reason}; body={body}")
    except URLError as e:
        raise RuntimeError(f"URLError: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"UnknownError: {e}")

def call_kimi_chat(base_url: str, api_key: str, model: str,
                   system_prompt: str, user_prompt: str,
                   temperature: float = 0.4, timeout: int = 90,
                   debug: bool = False, max_tokens: int = 2000) -> str:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if debug:
        dbg = {**payload, "messages": [
            {"role": "system", "content": "[omitted system]"},
            {"role": "user", "content": (user_prompt[:400] + ("..." if len(user_prompt) > 400 else ""))}
        ]}
        print(f"[DEBUG] POST {endpoint}\n[DEBUG] payload={json.dumps(dbg, ensure_ascii=False)}")
    obj = _http_post_json(endpoint, payload, api_key, timeout=timeout, debug=debug)
    try:
        return obj["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise RuntimeError(f"BadResponse: {e}; obj={json.dumps(obj, ensure_ascii=False)[:1500]}")

def build_system_prompt(now_str: str) -> str:
    """把标题时间定死到 now_str，减少模型偏差"""
    return f"""你是一位具有医学专业知识背景的AI个人健康管理专家。请完全基于"患者资料 + 访谈问答 + 疾病风险结果"，生成一份Markdown格式的《个性化健康管理建议报告》。请严格遵循以下格式与解析约束：

【总结构与标题】
1) 第一行标题：`健康管理报告 - 生成时间: YYYY/MM/DD HH:MM:SS`（24小时制，补零）。
2) 其后按如下分节与层级输出（必须使用 Markdown 标题）：
   ## 个性化健康管理建议报告
   ### 整体概述
   ### 详细分析
   #### 1. 饮食习惯分析
   #### 2. 运动习惯分析
   ### 个性化建议
   ### 总结与鼓励

【内容与语气】
- 语言：简体中文；语气：专业、具体、可执行、鼓励。
- 不得臆造检测数据与诊断结论；非医疗诊断。
- 小节之间空一行，优先使用简短句，必要时使用**加粗**强调名词。

【"详细分析"分节】
在做以下两点分析时，切记要结合患者问答阶段含有的信息，报告要足够个性化。
为了体现个性化，请在所有输出里至少添加一句“考虑到您的情况”或“结合您现在的XX运动情况”，分析要因人而异结合对话内容！
- 饮食习惯分析：2–5条要点，可用**加粗**突出关键词。在此之后输出一个饮食习惯的总结。
- 运动习惯分析：说明频次/时长/类型，指出优点与短板，最后做一个整合回复一个运动情况总结。


【"个性化建议"分节】
1) 对高风险疾病必须输出独立小节；对中风险建议也输出独立小节。
   小节标题：`#### 针对{{疾病名}}（风险较高|风险中等|风险较低）`
2) 小节首行必须在行首输出精确短语：`您患{{疾病名}}的风险{{较高|中等|较低}}`。
3) 每个疾病给出≥3条建议，严格使用如下格式：
   [1] 建议句； | 推理: 一句话理由
   [2] 建议句； | 推理: 一句话理由
   [3] 建议句； | 推理: 一句话理由
4) 建议要具体可执行（频次/时长/剂量/复查周期）。

【禁止与边界】
- 禁止输出"文献支持/文献来源/DOI/PMID/链接"等字样。
- 禁止给出诊断性结论；若信息不足，不要编造具体数值。

【输出检查】
- 严格按标题层级与顺序输出所有分节。
- 每个"个性化建议"小节内，确认存在行首`您患{{疾病名}}的风险{{较高|中等|较低}}`与≥3条建议。
"""

def build_user_prompt(dis_candidates: list, feedback_text: str, dialog_text: str) -> str:
    diseases_block = "\n".join(f"- {d}" for d in dis_candidates)
    return f"""已知输入包含两部分文本：
[用户不适反馈]
{feedback_text}

[患者对话记录]
{dialog_text}

【任务】
- 仅根据上面两段内容（不虚构化验数据），从以下疾病候选中结合“不适反馈+对话”判断高/中/低风险，并据此生成完整报告：
{diseases_block}

【输出检查】
- 第一行标题的时间必须与系统给定一致；
- 严格按标题层级与顺序输出所有分节；
- 每个“个性化建议”小节需包含行首“您患…的风险…”和≥3条建议（含推理）。"""

def gen_report_for_file(txt_path: Path, out_dir: Path, base_url: str, api_key: str,
                        model: str, temperature: float, debug: bool, max_tokens: int) -> Path:
    text = load_text_with_fallback(txt_path)
    sections = parse_sections(text)

    feedback = sections.get("===== 用户不适反馈 =====", "").strip()
    dialog   = sections.get("===== 患者对话记录 =====", "").strip()
    if not feedback or not dialog:
        raise RuntimeError(f"[{txt_path.name}] 缺少‘用户不适反馈’或‘患者对话记录’段落。")

    # 生成“固定时间字符串”，确保标题行完全满足格式（24小时制，补零）
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    system_prompt = build_system_prompt(now_str)
    user_prompt   = build_user_prompt(DISEASE_CANDIDATES, feedback, dialog)

    md = call_kimi_chat(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        timeout=120,
        debug=debug,
        max_tokens=max_tokens
    )

    # 输出文件：原名 + _report.txt
    out_name = f"{txt_path.stem}_report.txt"
    out_path = ensure_unique_path(out_dir / out_name)
    out_path.write_text(md, encoding="utf-8")
    return out_path

def natural_key(p: Path):
    m = re.search(r"(\d+)", p.stem)
    return int(m.group(1)) if m else 10**9

def main():
    ap = argparse.ArgumentParser(description="从含‘不适反馈+对话’的文本批量生成 Markdown 健康管理报告")
    ap.add_argument("--input-dir", required=True, help="输入文件夹（包含 *_with_feedback.txt）")
    ap.add_argument("--output-dir", required=True, help="报告输出文件夹（自动创建；永不覆盖）")
    ap.add_argument("--limit", type=int, default=35, help="最多处理的文件数（默认 35）")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="模型名称（默认 kimi-k2-0905-preview）")
    ap.add_argument("--temperature", type=float, default=0.4, help="生成温度（默认 0.4）")
    ap.add_argument("--max-tokens", type=int, default=2000, help="最大输出 token（默认 2000）")
    ap.add_argument("--debug", action="store_true", help="打印调试信息（不会打印密钥）")
    args = ap.parse_args()

    base_url = _resolve_base_url()
    api_key  = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        raise SystemExit("请先设置环境变量：MOONSHOT_API_KEY")

    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    if not in_dir.exists() or not in_dir.is_dir():
        raise SystemExit(f"输入目录不存在或不是目录：{in_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 只处理 .txt，且跳过 *_report.txt，按数字自然序
    txt_files = [p for p in in_dir.glob("*.txt") if not p.name.endswith("_report.txt")]
    txt_files.sort(key=natural_key)
    if not txt_files:
        raise SystemExit("未找到任何 .txt 输入文件。")

    processed = 0
    for p in txt_files:
        if processed >= args.limit:
            break
        try:
            out_path = gen_report_for_file(
                txt_path=p,
                out_dir=out_dir,
                base_url=base_url,
                api_key=api_key,
                model=args.model,
                temperature=args.temperature,
                debug=args.debug,
                max_tokens=args.max_tokens
            )
            print(f"[OK] {p.name} -> {out_path}")
            processed += 1
        except Exception as e:
            print(f"[失败] {p.name}: {e}")

    print(f"完成。共处理 {processed} 个文件（上限 {args.limit}）。")

if __name__ == "__main__":
    main()

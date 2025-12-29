"""
医学报告OCR数据智能清洗脚本 - 按患者汇总版本（匿名）
使用本地LLM（如Ollama、vLLM等）进行数据清洗，成本为零

数据格式：一个患者 → 一条训练数据（完全匿名）
"""

import pandas as pd
import json
import re
from tqdm import tqdm
import requests

# 配置
INPUT_FILE = r'C:\Users\18515\Desktop\微调数据清洗\健康指导建议提取结果企业_chang2(1).xlsx'
OUTPUT_FILE = r'C:\Users\18515\Desktop\微调数据清洗\cleaned_medical_data.jsonl'
SAMPLE_OUTPUT = r'C:\Users\18515\Desktop\微调数据清洗\sample_cleaned_data.json'

# Ollama API配置
OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME = "qwen2.5:7b"  # 可替换为其他模型


SYSTEM_PROMPT = """你是一位经验丰富的医生，正在为患者撰写完整的体检报告分析。

任务：
1. 从OCR提取的文本中识别所有体检异常指标
2. 为每个异常指标提供：医学解释 + 医生建议
3. 生成一份结构化的完整医学报告
4. **重要**：只清理OCR噪音（如符号♦*！、标签!1、乱码等），不要改写或编造医学内容，保持原文准确性
5. **重要**：报告中不要包含任何患者个人信息（姓名、ID等），保持完全匿名

输出JSON格式：
{
  "abnormal_findings": ["异常1", "异常2", "异常3"],
  "medical_report": "完整的匿名医学报告内容"
}

报告格式要求：
- 第一部分：异常指标列表
- 第二部分：详细分析（每个异常指标包含医学解释和健康建议，连续写在一起）
  格式：【异常指标】\n医学解释：...\n健康建议：...\n
- 语言专业、清晰、易懂
- **完全匿名，不包含任何个人识别信息**
- **只去除OCR噪音，不要自己编造或改写医学内容**
- **所有内容必须来自原文，不要添加任何内容**
- **总而言之，要把能当成报告的内容整理成格式整齐的报告**
"""


def call_ollama_api(text, model=MODEL_NAME):
    """调用Ollama API生成医学报告"""
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"请分析以下体检报告并生成完整的匿名医学报告：\n\n{text[:3000]}"}
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.3,
                    "num_predict": 2000
                }
            },
            timeout=180
        )

        if response.status_code == 200:
            result = response.json()
            content = result['message']['content']
            return json.loads(content)
        else:
            print(f"API错误: {response.status_code}")
            return None

    except Exception as e:
        print(f"调用失败: {e}")
        return None


def extract_findings_with_details(text):
    """从健康指导建议部分提取异常指标及其详细说明"""
    findings = []

    # 找到"健康指导建议"部分
    if '健康指导建议' not in text:
        return findings

    guidance_section = text.split('健康指导建议', 1)[1]

    # 按"医学解释"分割成多个块
    blocks = re.split(r'\n\s*医学解释[：:：]?\s*\n', guidance_section)

    for i in range(1, len(blocks)):
        # 从前一个块的末尾提取指标名称（最后一个非空行）
        prev_block_lines = [line.strip() for line in blocks[i-1].strip().split('\n') if line.strip()]
        if not prev_block_lines:
            continue

        indicator = prev_block_lines[-1]

        # 清理指标名称中的OCR噪音和多余点号
        indicator = re.sub(r'^[*♦\s|!1]+', '', indicator)
        indicator = re.sub(r'[\.]{2,}', '', indicator)  # 去除连续的点号
        indicator = indicator.strip()

        # 跳过太长或太短的指标名称
        if not indicator or len(indicator) > 100 or len(indicator) < 3:
            continue

        # 当前块包含医学解释和医生建议
        current_block = blocks[i]

        # 分割医学解释和医生建议
        advice_pattern = r'([!1nw岂|]+\s*[一]*\s*医生建议)[：:：]?\s*'
        advice_match = re.search(advice_pattern, current_block)

        if advice_match:
            # 有医生建议
            explanation = current_block[:advice_match.start()].strip()
            advice = current_block[advice_match.end():].strip()
        else:
            # 没有医生建议，全部是医学解释
            explanation = current_block.strip()
            advice = ""

        # 清理内容：去除下一个指标标题（如果存在）
        # 如果内容中包含以"偏高|偏低|阳性"结尾的行，那可能是下一个指标的标题，需要截断
        explanation_lines = explanation.split('\n')
        clean_explanation_lines = []
        for line in explanation_lines:
            line_stripped = line.strip()
            # 如果这一行看起来像一个指标标题（短，以关键词结尾），停止
            if re.search(r'^.{5,80}(?:偏高|偏低|阳性)\s*$', line_stripped):
                break
            clean_explanation_lines.append(line)
        explanation = '\n'.join(clean_explanation_lines).strip()

        advice_lines = advice.split('\n')
        clean_advice_lines = []
        for line in advice_lines:
            line_stripped = line.strip()
            # 如果这一行看起来像一个指标标题或其他部分的开始，停止
            if re.search(r'^.{5,80}(?:偏高|偏低|阳性)\s*$', line_stripped):
                break
            if re.search(r'^[*♦]|\|白细胞|血小板|主检医生|体检结果|常规检查', line_stripped):
                break
            clean_advice_lines.append(line)
        advice = '\n'.join(clean_advice_lines).strip()

        # 清理OCR噪音
        explanation = re.sub(r'[♦*！]+', '', explanation)
        explanation = re.sub(r'\n+', ' ', explanation)
        explanation = re.sub(r'!1\s*', '', explanation)
        explanation = re.sub(r'[闺司岂wn]\s*', '', explanation)
        explanation = explanation.strip()

        advice = re.sub(r'[♦*！]+', '', advice)
        advice = re.sub(r'\n+', ' ', advice)
        advice = re.sub(r'!1\s*', '', advice)
        advice = re.sub(r'[闺司岂wn]\s*', '', advice)
        advice = advice.strip()

        # 只有当有实际内容时才添加
        if indicator and (explanation or advice):
            findings.append({
                'indicator': indicator,
                'explanation': explanation[:1000] if explanation else "",
                'advice': advice[:1000] if advice else ""
            })

    return findings


def extract_structured_data_rule_based(ocr_text):
    """
    基于规则的提取方法（备用方案）
    按患者汇总所有异常
    """
    # 从"健康指导建议"部分直接提取所有异常及其详细说明
    findings_with_details = extract_findings_with_details(ocr_text)

    if not findings_with_details:
        return None

    # 汇总生成匿名报告
    medical_report = "体检异常指标分析报告\n\n"
    medical_report += f"检出异常指标：{len(findings_with_details)} 项\n\n"

    # 第一部分：异常项目清单
    medical_report += "一、异常项目清单：\n"
    for i, item in enumerate(findings_with_details, 1):
        medical_report += f"{i}. {item['indicator']}\n"

    # 第二部分：详细分析（医学解释和健康建议整合在一起）
    medical_report += "\n" + "="*50 + "\n\n二、详细分析：\n\n"

    for item in findings_with_details:
        medical_report += f"【{item['indicator']}】\n\n"

        if item['explanation']:
            medical_report += f"医学解释：{item['explanation']}\n\n"

        if item['advice']:
            medical_report += f"健康建议：{item['advice']}\n\n"

        medical_report += "-" * 50 + "\n\n"

    return {
        "abnormal_findings": [item['indicator'] for item in findings_with_details],
        "medical_report": medical_report
    }


def process_single_record(ocr_text, use_llm=True):
    """
    处理单条记录
    返回：包含匿名患者信息的完整报告
    """
    if use_llm:
        # 尝试使用LLM
        result = call_ollama_api(ocr_text)
        if result and 'abnormal_findings' in result and 'medical_report' in result:
            return result

    # 回退到规则方法
    result = extract_structured_data_rule_based(ocr_text)
    return result


def convert_to_fine_tune_format(record_index, result):
    """
    转换为Kimi微调格式 - 按患者汇总（匿名）

    Args:
        record_index: 记录索引（0开始）
        result: 包含 abnormal_findings 和 medical_report 的字典

    Returns:
        单条训练数据（完全匿名）
    """
    if not result or not result.get('abnormal_findings'):
        return None

    abnormal_findings = result['abnormal_findings']
    medical_report = result['medical_report']

    # 生成匿名患者ID
    patient_id = f"PATIENT_{record_index+1:05d}"  # 如：PATIENT_00001

    # 构建输入：列举所有异常指标
    findings_str = "，".join(abnormal_findings)
    instruction = f"请解释以下体检异常指标并给出健康建议：{findings_str}"

    # 构建输出：完整匿名医学报告
    output = medical_report

    return {
        "patient_id": patient_id,  # 匿名ID
        "abnormal_count": len(abnormal_findings),
        "messages": [
            {"role": "user", "content": instruction},
            {"role": "assistant", "content": output}
        ]
    }


def main(use_llm=True):
    """
    主处理流程

    Args:
        use_llm: 是否使用LLM（False则使用纯规则方法）
    """
    print("开始读取数据...")
    df = pd.read_excel(INPUT_FILE)
    print(f"共读取 {len(df)} 条记录")
    print("注意：所有患者信息将完全匿名处理\n")

    if use_llm:
        # 测试Ollama连接
        try:
            response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
            if response.status_code == 200:
                print(f"Ollama连接成功！使用模型: {MODEL_NAME}")
            else:
                print("Ollama连接失败，将使用规则方法")
                use_llm = False
        except:
            print("无法连接到Ollama，将使用规则方法")
            use_llm = False

    # 处理样例
    print("\n处理前5条样例数据...\n")
    sample_results = []

    for i in tqdm(range(min(5, len(df))), desc="处理样例"):
        ocr_text = df.iloc[i]['extracted_content']

        result = process_single_record(ocr_text, use_llm)

        if result:
            formatted = convert_to_fine_tune_format(i, result)
            if formatted:
                sample_results.append(formatted)
                print(f"\n第{i+1}条 [{formatted['patient_id']}]: 提取到 {formatted['abnormal_count']} 个异常项")

    # 保存样例
    with open(SAMPLE_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(sample_results, f, ensure_ascii=False, indent=2)

    print(f"\n样例数据已保存到: {SAMPLE_OUTPUT}")
    print(f"样例共生成 {len(sample_results)} 条训练数据（每条对应1个患者，完全匿名）")

    # 显示一条样例
    if sample_results:
        print("\n" + "="*60)
        print("样例数据预览：")
        print(f"患者ID: {sample_results[0]['patient_id']} (匿名)")
        print(f"异常数量: {sample_results[0]['abnormal_count']}")
        print(f"问题: {sample_results[0]['messages'][0]['content'][:100]}...")
        print(f"回答前200字: {sample_results[0]['messages'][1]['content'][:200]}...")
        print("="*60)

    # 询问是否继续
    response = input("\n是否继续处理全部数据？(y/n): ")
    if response.lower() != 'y':
        print("已取消")
        return

    # 批量处理
    print("\n开始批量处理...")
    all_results = []

    for i in tqdm(range(len(df)), desc="处理中"):
        ocr_text = df.iloc[i]['extracted_content']

        result = process_single_record(ocr_text, use_llm)

        if result:
            formatted = convert_to_fine_tune_format(i, result)
            if formatted:
                all_results.append(formatted)

        # 每100条保存一次
        if (i + 1) % 100 == 0:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for item in all_results:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
            print(f"  已处理 {i+1} 条，生成 {len(all_results)} 条训练数据（匿名）")

    # 最终保存
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for item in all_results:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    print(f"\n处理完成！")
    print(f"原始数据: {len(df)} 条患者记录")
    print(f"生成训练数据: {len(all_results)} 条（每条对应1个患者，完全匿名）")
    print(f"平均每个患者: {sum(r['abnormal_count'] for r in all_results) / len(all_results):.1f} 个异常项")
    print(f"输出文件: {OUTPUT_FILE}")
    print(f"\n所有患者信息已完全匿名化处理（patient_id格式：PATIENT_00001）")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--no-llm', action='store_true', help='使用纯规则方法（不调用LLM）')
    args = parser.parse_args()

    main(use_llm=not args.no_llm)

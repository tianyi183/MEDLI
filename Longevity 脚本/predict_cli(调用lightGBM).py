#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI 入口：Node 调用后，读取 Excel/CSV → 17 个 LightGBM 模型推理 → 输出 JSON
Usage: python3 predict_cli.py <file_path>
"""
import sys, os, json

# 设置控制台编码为UTF-8（Windows）
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# 复用 app.py 里已经写好的函数
from app import predict_with_models

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: predict_cli.py <file_path>", file=sys.stderr)
        sys.exit(1)

    file_path   = sys.argv[1]
    user_dir    = os.path.dirname(file_path)         # 结果文件跟上传文件放一起
    try:
        result_path, summary = predict_with_models(file_path, user_dir)
        # 让 Node 端只需解析最后一行即可
        print(json.dumps({"resultPath": result_path, "summary": summary}))
    except Exception as e:
        # 把异常信息也打印出来，Node 那边会收到 stderr
        print(f"ERROR::{str(e)}", file=sys.stderr)
        sys.exit(2)


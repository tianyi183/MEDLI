"""
QLoRA 微调脚本 - 使用 4-bit 量化大幅降低显存占用
支持多卡训练，32B 模型每卡仅需 8-10GB
"""

import os
import sys
import argparse

# 设置环境变量
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import json
import yaml
import torch
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from datasets import load_dataset, DatasetDict
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    AutoConfig,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
    set_seed,
    BitsAndBytesConfig,
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType,
)

# 设置日志
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> Dict:
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def get_model_config(config: Dict) -> Dict:
    """获取当前使用的模型配置"""
    current_model = config['model']['current']
    model_config = config['model'][current_model]
    logger.info(f"当前使用模型: {current_model}")
    logger.info(f"模型路径: {model_config['model_name_or_path']}")
    return model_config


def prepare_dataset(config: Dict, tokenizer) -> DatasetDict:
    """准备训练数据集"""
    logger.info("开始加载数据集...")

    # 加载 JSONL 数据
    data_path = config['data']['train_file']
    dataset = load_dataset('json', data_files=data_path)

    logger.info(f"数据集加载完成，共 {len(dataset['train'])} 条数据")

    # 划分训练集和验证集
    validation_split = config['data']['validation_split']
    if validation_split > 0:
        dataset = dataset['train'].train_test_split(
            test_size=validation_split,
            seed=config['training']['seed']
        )
        dataset = DatasetDict({
            'train': dataset['train'],
            'validation': dataset['test']
        })
        logger.info(f"训练集: {len(dataset['train'])} 条")
        logger.info(f"验证集: {len(dataset['validation'])} 条")
    else:
        dataset = DatasetDict({'train': dataset['train']})
        logger.info("未划分验证集")

    # 数据预处理函数
    def preprocess_function(examples):
        """将对话格式转换为模型输入格式"""
        model_inputs = {
            "input_ids": [],
            "attention_mask": [],
            "labels": []
        }

        for messages in examples["messages"]:
            if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template is not None:
                text = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=False
                )
                tokenized = tokenizer(
                    text,
                    max_length=config['data']['max_length'],
                    truncation=True,
                    padding=False,
                )
            else:
                text = ""
                for message in messages:
                    role = message["role"]
                    content = message["content"]
                    if role == "user":
                        text += f"<|im_start|>user\n{content}<|im_end|>\n"
                    elif role == "assistant":
                        text += f"<|im_start|>assistant\n{content}<|im_end|>\n"

                tokenized = tokenizer(
                    text,
                    max_length=config['data']['max_length'],
                    truncation=True,
                    padding=False,
                )

            model_inputs["input_ids"].append(tokenized["input_ids"])
            model_inputs["attention_mask"].append(tokenized["attention_mask"])
            model_inputs["labels"].append(tokenized["input_ids"].copy())

        return model_inputs

    # 处理数据集
    logger.info("开始处理数据集...")
    processed_dataset = dataset.map(
        preprocess_function,
        batched=True,
        num_proc=config['data']['preprocessing_num_workers'],
        remove_columns=dataset['train'].column_names,
        desc="处理数据集",
    )

    logger.info("数据集处理完成")
    return processed_dataset


def create_model_and_tokenizer(config: Dict):
    """创建模型和 tokenizer（QLoRA 版本）"""
    model_config = get_model_config(config)
    model_path = model_config['model_name_or_path']

    logger.info("加载 tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=config['other']['trust_remote_code'],
        use_fast=True,
    )

    # 设置 pad_token
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        logger.info(f"设置 pad_token 为 eos_token: {tokenizer.eos_token}")

    logger.info("使用 QLoRA 加载模型（4-bit 量化）...")

    # 先加载配置，禁用模型自带的 FP8 量化（如 Kimi K2）
    logger.info("加载模型配置...")
    model_config_obj = AutoConfig.from_pretrained(
        model_path,
        trust_remote_code=config['other']['trust_remote_code'],
    )
    # 移除 FP8 量化配置（A6000 不支持），我们使用 4-bit QLoRA
    if hasattr(model_config_obj, 'quantization_config'):
        logger.info("检测到模型自带量化配置，将使用 4-bit QLoRA 替代")
        model_config_obj.quantization_config = None

    # 关闭 use_cache（QLoRA 训练需要）
    model_config_obj.use_cache = False

    # QLoRA 配置：4-bit 量化
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if config['training']['bf16'] else torch.float16,
        llm_int8_enable_fp32_cpu_offload=True,  # 允许 CPU offload
    )

    # 检测是否为分布式训练（通过环境变量判断）
    world_size = int(os.environ.get('WORLD_SIZE', '1'))
    local_rank = int(os.environ.get('LOCAL_RANK', '0'))
    is_distributed = world_size > 1

    logger.info(f"分布式训练: {is_distributed}, WORLD_SIZE: {world_size}, LOCAL_RANK: {local_rank}")

    # 加载量化模型
    # 多卡时：不使用 device_map，在 CPU 上加载，稍后由 Trainer 移动到对应 GPU
    # 单卡时：使用 device_map="auto" 自动分配
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        config=model_config_obj,
        trust_remote_code=config['other']['trust_remote_code'],
        quantization_config=bnb_config,
        device_map={"": "cpu"} if is_distributed else "auto",  # 多卡时先加载到 CPU
    )

    logger.info(f"模型加载完成（4-bit 量化），参数量: {model.num_parameters() / 1e9:.2f}B")

    # 准备模型用于 k-bit 训练
    model = prepare_model_for_kbit_training(model)
    logger.info("模型已准备好用于 4-bit 训练")

    # 启用梯度检查点
    if config['training']['gradient_checkpointing']:
        model.gradient_checkpointing_enable()
        logger.info("已启用梯度检查点")

    # 配置 LoRA
    logger.info("配置 LoRA...")
    lora_config = LoraConfig(
        r=config['lora']['r'],
        lora_alpha=config['lora']['lora_alpha'],
        target_modules=config['lora']['target_modules'],
        lora_dropout=config['lora']['lora_dropout'],
        bias=config['lora']['bias'],
        task_type=TaskType.CAUSAL_LM,
    )

    # 应用 LoRA
    model = get_peft_model(model, lora_config)

    # 打印可训练参数
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    all_params = sum(p.numel() for p in model.parameters())
    logger.info(f"可训练参数: {trainable_params:,} ({100 * trainable_params / all_params:.2f}%)")
    logger.info(f"总参数: {all_params:,}")

    return model, tokenizer


def create_trainer(model, tokenizer, train_dataset, eval_dataset, config: Dict):
    """创建 Trainer（QLoRA 版本，不使用 DeepSpeed）"""

    # 训练参数
    training_args = TrainingArguments(
        output_dir=config['training']['output_dir'],
        num_train_epochs=config['training']['num_train_epochs'],
        per_device_train_batch_size=config['training']['per_device_train_batch_size'],
        per_device_eval_batch_size=config['training']['per_device_eval_batch_size'],
        gradient_accumulation_steps=config['training']['gradient_accumulation_steps'],
        learning_rate=config['training']['learning_rate'],
        lr_scheduler_type=config['training']['lr_scheduler_type'],
        warmup_steps=config['training']['warmup_steps'],
        weight_decay=config['training']['weight_decay'],
        max_grad_norm=config['training']['max_grad_norm'],
        logging_steps=config['training']['logging_steps'],
        save_steps=config['training']['save_steps'],
        eval_steps=config['training']['eval_steps'],
        eval_strategy=config['training']['evaluation_strategy'],
        save_strategy=config['training']['save_strategy'],
        save_total_limit=config['training']['save_total_limit'],
        load_best_model_at_end=config['training']['load_best_model_at_end'],
        metric_for_best_model=config['training']['metric_for_best_model'],
        greater_is_better=config['training']['greater_is_better'],
        fp16=config['training']['fp16'],
        bf16=config['training']['bf16'],
        gradient_checkpointing=config['training']['gradient_checkpointing'],
        seed=config['training']['seed'],
        dataloader_num_workers=config['training']['dataloader_num_workers'],
        remove_unused_columns=config['training']['remove_unused_columns'],
        ddp_backend=config['training']['ddp_backend'],
        optim=config['training']['optim'],
        report_to=["tensorboard"],
        logging_dir=os.path.join(config['training']['output_dir'], "logs"),
        # QLoRA 不需要 DeepSpeed
    )

    # Data collator
    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=model,
        padding=True,
        return_tensors="pt",
    )

    # 创建 Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
    )

    return trainer


def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="QLoRA 微调训练")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="配置文件路径（默认: config.yaml）"
    )
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("开始 QLoRA 微调训练（4-bit 量化）")
    logger.info(f"配置文件: {args.config}")
    logger.info("=" * 50)

    # 加载配置
    config = load_config(args.config)

    # 设置随机种子
    set_seed(config['training']['seed'])

    # 创建模型和 tokenizer
    model, tokenizer = create_model_and_tokenizer(config)

    # 准备数据集
    dataset = prepare_dataset(config, tokenizer)

    # 创建 Trainer
    trainer = create_trainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset['train'],
        eval_dataset=dataset.get('validation', None),
        config=config,
    )

    # 检查是否有检查点可以恢复
    checkpoint = None
    output_dir = config['training']['output_dir']
    if os.path.exists(output_dir):
        checkpoints = [d for d in os.listdir(output_dir) if d.startswith('checkpoint-')]
        if checkpoints:
            checkpoints = sorted(checkpoints, key=lambda x: int(x.split('-')[1]))
            checkpoint = os.path.join(output_dir, checkpoints[-1])
            logger.info(f"发现检查点，将从 {checkpoint} 恢复训练")

    # 开始训练
    logger.info("开始训练...")
    train_result = trainer.train(resume_from_checkpoint=checkpoint)

    # 保存模型
    logger.info("保存模型...")
    trainer.save_model()
    trainer.save_state()

    # 保存训练指标
    metrics = train_result.metrics
    trainer.log_metrics("train", metrics)
    trainer.save_metrics("train", metrics)

    logger.info("=" * 50)
    logger.info("训练完成！")
    logger.info(f"模型保存路径: {config['training']['output_dir']}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()

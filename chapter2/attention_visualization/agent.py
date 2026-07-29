"""
注意力可视化 Agent
使用 llama.cpp 的 OpenAI 兼容 API 实现基础的可视化功能

注意：由于 llama.cpp 不直接返回注意力权重，本项目采用以下替代方案：
1. 记录每个生成 token 的对数概率（logprobs）- 反映模型置信度
2. 捕获模型的思考过程（如支持）
3. 记录工具调用序列 - 展示模型的推理路径
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
import numpy as np

from config import (
    LLAMA_HOST, LLAMA_PORT, LLAMA_MODEL, LLAMA_OPENAI_COMPATIBLE_URL,
    DEFAULT_MAX_NEW_TOKENS, DEFAULT_TEMPERATURE, DEFAULT_TOP_P,
    SYSTEM_PROMPTS, RESULTS_DIR, LOG_LEVEL
)

# 配置日志
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TokenInfo:
    """记录单个 token 的信息"""
    token: str
    token_id: Optional[int]
    logprob: float
    top_logprobs: List[Dict[str, float]]
    position: int

    def to_dict(self):
        return {
            'token': self.token,
            'token_id': self.token_id,
            'logprob': self.logprob,
            'top_logprobs': self.top_logprobs,
            'position': self.position
        }


@dataclass
class GenerationResult:
    """生成结果的数据类"""
    input_text: str
    output_text: str
    input_tokens: List[str]
    output_tokens: List[str]
    token_info: List[TokenInfo]
    model: str
    temperature: float
    finish_reason: str
    thinking_content: str = ""
    tool_calls: List[Dict] = field(default_factory=list)

    def to_dict(self):
        return {
            'input_text': self.input_text,
            'output_text': self.output_text,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'token_info': [t.to_dict() for t in self.token_info],
            'model': self.model,
            'temperature': self.temperature,
            'finish_reason': self.finish_reason,
            'thinking_content': self.thinking_content,
            'tool_calls': self.tool_calls
        }


class AttentionVisualizationAgent:
    """
    注意力可视化 Agent

    使用 llama.cpp 的 OpenAI 兼容 API 进行推理，
    通过 logprobs 和推理链分析模型的"关注"行为。
    """

    def __init__(
        self,
        model: str = None,
        host: str = None,
        port: int = None,
        verbose: bool = True
    ):
        """
        初始化 Agent

        Args:
            model: 模型名称（默认使用配置中的模型）
            host: llama.cpp 服务器地址
            port: llama.cpp 服务器端口
            verbose: 是否输出详细日志
        """
        self.model = model or LLAMA_MODEL
        self.host = host or LLAMA_HOST
        self.port = port if port is not None else LLAMA_PORT
        self.verbose = verbose

        # 构建 base URL
        self.base_url = f"http://{self.host}:{self.port}/v1"

        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            base_url=self.base_url,
            api_key="llama-cpp"
        )

        self.conversation_history = []

        if self.verbose:
            logger.info(f"🌐 连接到 llama.cpp 服务器: {self.base_url}")
            logger.info(f"📦 使用模型: {self.model}")

    def generate_with_logprobs(
        self,
        prompt: str,
        max_tokens: int = None,
        temperature: float = DEFAULT_TEMPERATURE,
        top_logprobs: int = 5,
        system_prompt: str = None,
        save_result: bool = False,
        category: str = "默认"
    ) -> GenerationResult:
        """
        生成文本并记录 token 级别的 logprobs

        Args:
            prompt: 输入提示
            max_tokens: 最大生成 token 数
            temperature: 采样温度
            top_logprobs: 记录前 N 个候选 token 的概率
            system_prompt: 系统提示词
            save_result: 是否保存结果到文件
            category: 结果分类

        Returns:
            GenerationResult: 包含生成结果和 token 信息
        """
        max_tokens = max_tokens or DEFAULT_MAX_NEW_TOKENS
        system_prompt = system_prompt or SYSTEM_PROMPTS["default"]

        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        if self.verbose:
            logger.info(f"📝 输入: {prompt[:100]}...")
            logger.info(f"🌡️  温度: {temperature}, 最大 token: {max_tokens}")

        try:
            # 调用 API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=DEFAULT_TOP_P,
                logprobs=True,
                top_logprobs=top_logprobs
            )

            # 提取结果
            choice = response.choices[0]
            output_text = choice.message.content or ""
            finish_reason = choice.finish_reason

            # 提取 token 信息
            token_info_list = []
            output_tokens = []

            if hasattr(choice, 'logprobs') and choice.logprobs:
                if hasattr(choice.logprobs, 'content'):
                    for item in choice.logprobs.content:
                        if item:
                            token_info = TokenInfo(
                                token=item.token,
                                token_id=None,  # llama.cpp 可能不提供
                                logprob=item.logprob or 0.0,
                                top_logprobs=[
                                    {t.token: t.logprob}
                                    for t in (item.top_logprobs or [])
                                ],
                                position=len(output_tokens)
                            )
                            token_info_list.append(token_info)
                            output_tokens.append(item.token)

            # 如果 content 为空但有 tokens，从 tokens 重建文本
            if not output_text and output_tokens:
                output_text = ''.join(output_tokens)

            # 提取思考内容（如果有）
            thinking_content = ""
            if output_text:
                # 检查是否有思考标签
                if "<|thinking|>" in output_text:
                    parts = output_text.split("<|thinking|>")
                    if len(parts) > 1:
                        thinking_parts = parts[1].split("<|/thinking|>")
                        thinking_content = thinking_parts[0].strip()
                        output_text = parts[0] + (
                            thinking_parts[1] if len(thinking_parts) > 1 else ""
                        )

            # 创建结果对象
            result = GenerationResult(
                input_text=prompt,
                output_text=output_text.strip(),
                input_tokens=[],  # llama.cpp 不返回输入 token
                output_tokens=output_tokens,
                token_info=token_info_list,
                model=self.model,
                temperature=temperature,
                finish_reason=finish_reason
            )

            if self.verbose:
                logger.info(f"✅ 生成完成，token 数: {len(output_tokens)}")
                logger.info(f"📄 输出: {output_text[:100]}...")

            # 保存结果
            if save_result:
                self._save_generation_result(result, category)

            return result

        except Exception as e:
            logger.error(f"❌ 生成失败: {e}")
            raise

    def _save_generation_result(self, result: GenerationResult, category: str):
        """保存生成结果到 JSON 文件"""
        RESULTS_DIR.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = RESULTS_DIR / f"generation_{category}_{timestamp}.json"

        data = {
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "result": result.to_dict()
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"💾 结果已保存: {filename}")

    def generate_streaming(
        self,
        prompt: str,
        max_tokens: int = None,
        temperature: float = DEFAULT_TEMPERATURE,
        system_prompt: str = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式生成文本

        Args:
            prompt: 输入提示
            max_tokens: 最大生成 token 数
            temperature: 采样温度
            system_prompt: 系统提示词

        Yields:
            包含 chunk 类型和内容的字典
        """
        max_tokens = max_tokens or DEFAULT_MAX_NEW_TOKENS
        system_prompt = system_prompt or SYSTEM_PROMPTS["default"]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        if self.verbose:
            logger.info(f"📝 输入: {prompt[:100]}...")

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=DEFAULT_TOP_P,
                stream=True
            )

            for chunk in stream:
                if chunk.choices:
                    choice = chunk.choices[0]
                    delta = choice.delta

                    if delta.content:
                        yield {
                            "type": "content",
                            "content": delta.content
                        }

                    if choice.finish_reason:
                        yield {
                            "type": "done",
                            "reason": choice.finish_reason
                        }

        except Exception as e:
            logger.error(f"❌ 流式生成失败: {e}")
            yield {"type": "error", "message": str(e)}


def demonstrate_basic_generation():
    """演示基础生成功能"""
    print("=" * 60)
    print("注意力可视化 Agent - 基础生成演示")
    print("=" * 60)

    # 初始化 Agent
    agent = AttentionVisualizationAgent(verbose=True)

    # 中文测试提示词
    test_prompts = [
        ("北京现在的天气怎么样？", "知识查询"),
        ("解释什么是机器学习", "概念解释"),
        ("25 乘以 37 等于多少？", "数学计算"),
    ]

    for prompt, category in test_prompts:
        print(f"\n{'─' * 60}")
        print(f"📋 类别: {category}")
        print(f"📝 提示: {prompt}")
        print(f"{'─' * 60}")

        try:
            result = agent.generate_with_logprobs(
                prompt=prompt,
                max_tokens=150,
                temperature=0.7,
                top_logprobs=3,
                save_result=True,
                category=category
            )

            print(f"\n🤖 回复:")
            print(result.output_text)

            # 显示一些 token 概率信息
            if result.token_info:
                print(f"\n📊 Token 置信度分析（前5个）:")
                for info in result.token_info[:5]:
                    print(f"  '{info.token}': logprob={info.logprob:.4f}")

        except Exception as e:
            print(f"❌ 错误: {e}")

    print("\n" + "=" * 60)
    print("✨ 演示完成！")
    print(f"💾 结果已保存到: {RESULTS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    demonstrate_basic_generation()

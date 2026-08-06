"""
文件系统工具模块

提供文件读取、模式搜索和文本摘要功能。

此模块包含：
- read_file: 读取文件内容（支持多种编码）
- grep_search: 在文件中进行类 grep 的模式搜索
- summarize_text: 对长文本进行智能摘要（支持 LLM）
"""
import json
import logging
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Union

from dotenv import load_dotenv
from mcp.types import TextContent

# 添加项目根目录到路径，用于导入统一 LLM 客户端
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from base import ActionResponse, validate_file_path


load_dotenv()


# 中文文本摘要提示词
SUMMARIZE_PROMPT_ZH = """请对以下文本进行摘要，提取关键信息。

要求：
1. 摘要长度控制在 {max_length} 字左右
2. 保留原文的核心观点和重要信息
3. 使用简洁清晰的语言
4. 突出重点内容

待摘要文本：
{text}

请输出摘要："""


async def read_file(
    file_path: str,
    encoding: str = "utf-8",
    max_length: int = 50000
) -> Union[str, TextContent]:
    """
    读取文件并返回其内容

    支持多种编码，可限制返回内容的最大长度。

    Args:
        file_path: 文件路径
        encoding: 文件编码（默认：utf-8）
        max_length: 返回的最大字符数（默认：50000），设为 -1 返回全部

    Returns:
        包含文件内容的 TextContent

    示例:
        >>> result = await read_file("/path/to/file.txt")
        >>> result['content'][:100]
        '文件内容的前100个字符...'
    """
    try:
        path = validate_file_path(file_path)

        logging.info(f"📖 正在读取文件：{path}")

        with open(path, 'r', encoding=encoding, errors='ignore') as f:
            content = f.read()

        # 处理长度限制
        if max_length < 0:
            max_length = len(content)
        truncated = len(content) > max_length
        if truncated:
            content = content[:max_length]

        result = {
            "file_path": str(path),
            "content": content,
            "size_bytes": path.stat().st_size,
            "truncated": truncated,
            "encoding": encoding
        }

        logging.info(f"✅ 成功读取文件（{len(content)} 个字符）")

        action_response = ActionResponse(
            success=True,
            message=result,
            metadata={"file_path": str(path)}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"文件读取失败：{str(e)}"
        logging.error(f"文件读取错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "file_read_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def grep_search(
    pattern: str,
    directory: str,
    file_pattern: str = "*",
    recursive: bool = True,
    case_sensitive: bool = False,
    max_results: int = 100
) -> Union[str, TextContent]:
    """
    在文件中进行类 grep 的模式搜索

    使用正则表达式在目录中搜索包含指定模式的文件。

    Args:
        pattern: 搜索的正则表达式模式
        directory: 搜索目录
        file_pattern: 文件模式（例如："*.py"），默认 "*"
        recursive: 是否递归搜索子目录，默认 True
        case_sensitive: 是否区分大小写，默认 False
        max_results: 返回的最大结果数，默认 100

    Returns:
        包含搜索结果的 TextContent

    示例:
        >>> results = await grep_search(
        ...     pattern="def.*\\(",
        ...     directory="/src",
        ...     file_pattern="*.py",
        ...     max_results=50
        ... )
    """
    try:
        dir_path = Path(directory).expanduser().resolve()

        # 验证目录
        if not dir_path.exists():
            raise FileNotFoundError(f"未找到目录：{dir_path}")

        if not dir_path.is_dir():
            raise ValueError(f"路径不是目录：{dir_path}")

        logging.info(f"🔍 正在搜索模式 '{pattern}' 在 {dir_path}")

        results = []

        # 处理 max_results=0 的情况
        if max_results <= 0:
            action_response = ActionResponse(
                success=True,
                message={
                    "pattern": pattern,
                    "results": results,
                    "total_found": 0,
                    "truncated": False,
                },
                metadata={
                    "directory": str(dir_path),
                    "file_pattern": file_pattern,
                    "recursive": recursive,
                },
            )
            return TextContent(
                type="text",
                text=json.dumps(action_response.model_dump(), ensure_ascii=False),
            )

        # 编译正则表达式
        flags = re.IGNORECASE if not case_sensitive else 0
        regex = re.compile(pattern, flags)

        # 获取文件列表
        if recursive:
            files = dir_path.rglob(file_pattern)
        else:
            files = dir_path.glob(file_pattern)

        # 搜索文件
        for file_path in files:
            if not file_path.is_file():
                continue

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append({
                                "file": str(file_path.relative_to(dir_path)),
                                "line_number": line_num,
                                "line": line.strip(),
                                "absolute_path": str(file_path)
                            })

                            if len(results) >= max_results:
                                break

                if len(results) >= max_results:
                    break

            except Exception as e:
                logging.warning(f"读取 {file_path} 时出错：{e}")
                continue

        logging.info(f"✅ 找到 {len(results)} 个匹配")

        action_response = ActionResponse(
            success=True,
            message={
                "pattern": pattern,
                "results": results,
                "total_found": len(results),
                "truncated": len(results) >= max_results
            },
            metadata={
                "directory": str(dir_path),
                "file_pattern": file_pattern,
                "recursive": recursive
            }
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"Grep 搜索失败：{str(e)}"
        logging.error(f"Grep 错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "grep_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def summarize_text(
    text: str,
    max_length: int = 500,
    use_llm: bool = True
) -> Union[str, TextContent]:
    """
    对长文本内容进行智能摘要

    支持使用 LLM 进行智能摘要，或使用简单的抽取式摘要。

    Args:
        text: 待摘要的文本
        max_length: 目标摘要长度（字符数），默认 500
        use_llm: 是否使用 LLM 进行摘要（默认 True）

    Returns:
        包含摘要结果的 TextContent

    注意:
        - 当 use_llm=True 时，需要配置 LLM 客户端
        - 当 LLM 不可用时，自动回退到抽取式摘要

    示例:
        >>> result = await summarize_text(
        ...     "这是一段很长的文本内容...",
        ...     max_length=200,
        ...     use_llm=True
        ... )
        >>> result['summary']
        '摘要内容...'
    """
    try:
        logging.info(f"📝 正在摘要文本（{len(text)} 个字符）")

        method = "unknown"
        summary = ""

        if use_llm:
            try:
                # 使用项目统一的 LLM 客户端
                from llm.client import get_llm_client
                client = get_llm_client()

                # 构建中文摘要提示词
                prompt = SUMMARIZE_PROMPT_ZH.format(
                    max_length=max_length,
                    text=text[:10000]  # 限制输入长度
                )

                # 调用 LLM
                response = client.chat.completions.create(
                    model=client.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一个专业的文本摘要助手，擅长提取关键信息并生成简洁的摘要。"
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_tokens=max_length * 2,
                    temperature=0.7
                )

                summary = response.choices[0].message.content.strip()
                method = "llm"

            except (ImportError, ValueError) as e:
                logging.warning(f"LLM 不可用，使用抽取式摘要：{e}")
                use_llm = False
            except Exception as e:
                logging.warning(f"LLM 调用失败，使用抽取式摘要：{e}")
                use_llm = False

        if not use_llm:
            # 抽取式摘要：提取重要句子
            sentences = re.split(r'[。！？.!?]+', text)
            summary = ""

            # 简单的重要性评分：包含关键词的句子优先
            keywords = ['重要', '关键', '核心', '主要', '总之', '因此', '所以']
            scored_sentences = []

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                # 计算重要性分数
                score = sum(1 for kw in keywords if kw in sentence)
                score += len(sentence) / 100  # 稍微偏好长句子

                scored_sentences.append((score, sentence))

            # 按分数排序
            scored_sentences.sort(key=lambda x: x[0], reverse=True)

            # 选择句子直到达到长度限制
            for _, sentence in scored_sentences:
                if len(summary) + len(sentence) + 1 <= max_length:
                    summary += sentence + "。"
                else:
                    break

            # 如果还是没有内容，直接截断
            if not summary and text:
                summary = text[:max_length] + "..." if len(text) > max_length else text

            method = "extractive"

        # 确保有内容
        if not summary:
            summary = text[:max_length] + "..." if len(text) > max_length else text
            method = "truncation"

        result = {
            "original_length": len(text),
            "summary_length": len(summary),
            "summary": summary,
            "method": method,
            "compression_ratio": len(summary) / len(text) if len(text) > 0 else 0
        }

        logging.info(f"✅ 生成摘要（{len(summary)} 个字符，方法：{method}）")

        action_response = ActionResponse(
            success=True,
            message=result,
            metadata={"method": method}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"文本摘要失败：{str(e)}"
        logging.error(f"摘要错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "summarization_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

"""
感知工具基础模块

提供标准响应格式和通用工具函数。

此模块定义了：
- ActionResponse: 所有工具函数的统一响应格式
- DocumentMetadata: 文档处理操作的元数据格式
- URL判断、文件验证、文件下载等通用函数
"""
import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from pydantic import BaseModel, Field

# 添加项目根目录到路径，以便导入统一的 LLM 客户端
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)


class ActionResponse(BaseModel):
    """
    所有感知工具操作的标准响应格式

    属性:
        success: 操作是否成功执行
        message: 操作的执行结果（可以是任意类型的数据）
        metadata: 操作相关的额外元数据
    """

    success: bool = Field(default=False, description="操作是否成功执行")
    message: Any = Field(default=None, description="操作的执行结果")
    metadata: dict[str, Any] = Field(default_factory=dict, description="操作相关的额外元数据")


class DocumentMetadata(BaseModel):
    """
    文档处理操作的元数据

    属性:
        file_name: 原始文件名
        file_size: 文件大小（字节）
        file_type: 文档类型/扩展名
        absolute_path: 文件的绝对路径
        page_count: 文档页数（可选）
        processing_time: 处理耗时（秒，可选）
        output_format: 提取内容的格式
    """

    file_name: str = Field(description="原始文件名")
    file_size: int = Field(description="文件大小（字节）")
    file_type: str = Field(description="文档文件类型/扩展名")
    absolute_path: str = Field(description="文档文件的绝对路径")
    page_count: int | None = Field(default=None, description="文档页数")
    processing_time: float | None = Field(default=None, description="处理耗时")
    output_format: str = Field(description="提取内容的格式")


def is_url(path_or_url: str) -> bool:
    """
    检查给定字符串是否为 URL

    通过解析字符串判断是否包含有效的协议和网络位置。

    Args:
        path_or_url: 待检查的字符串

    Returns:
        如果是 URL 返回 True，否则返回 False

    示例:
        >>> is_url("https://example.com/file.pdf")
        True
        >>> is_url("/local/path/file.txt")
        False
    """
    parsed = urlparse(path_or_url)
    return bool(parsed.scheme and parsed.netloc)


def validate_file_path(file_path: str) -> Path:
    """
    验证并解析文件路径

    确保文件存在且是有效文件，返回解析后的 Path 对象。

    Args:
        file_path: 文件路径（支持 ~ 扩展）

    Returns:
        解析后的 Path 对象

    Raises:
        FileNotFoundError: 文件不存在时抛出
        ValueError: 路径不是文件时抛出

    示例:
        >>> validate_file_path("~/document.txt")
        PosixPath('/home/user/document.txt')
    """
    path = Path(file_path).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    if not path.is_file():
        raise ValueError(f"路径不是文件: {path}")

    return path


def download_file_from_url(
    url: str,
    timeout: int = 60,
    max_size_mb: float = 100.0
) -> tuple[str, bytes]:
    """
    从 URL 下载文件到临时位置

    支持大文件流式下载，自动进行大小检查。

    Args:
        url: 下载地址
        timeout: 请求超时时间（秒），默认 60 秒
        max_size_mb: 最大文件大小（MB），默认 100MB

    Returns:
        (临时文件路径, 内容字节) 的元组

    Raises:
        ValueError: 文件大小超过限制时抛出
        requests.RequestException: 下载失败时抛出
        IOError: 其他 IO 错误时抛出

    注意:
        - 临时文件需要调用者手动清理
        - 尽最大努力进行 HEAD 预检查，但许多服务器拒绝 HEAD 请求
        - 实际大小限制由流式下载时的字节计数强制执行
    """
    max_size_bytes = max_size_mb * 1024 * 1024

    # 尽最大努力进行大小预检查。许多主机拒绝 HEAD 请求（预签名
    # S3/GCS URL 对动词进行签名，返回 403；CDN/WAF 前端的端点通常
    # 返回 405），因此失败的 HEAD 不应中止 GET 可以提供的下载
    # ——下方的流式循环无论如何都会强制执行 max_size_bytes。
    try:
        head_response = requests.head(url, timeout=timeout, allow_redirects=True)
        head_response.raise_for_status()
        content_length = head_response.headers.get("content-length")
    except requests.RequestException:
        content_length = None

    if content_length and int(content_length) > max_size_bytes:
        raise ValueError(
            f"文件大小 ({int(content_length) / (1024 * 1024):.2f} MB) "
            f"超过最大允许大小 ({max_size_mb} MB)"
        )

    try:
        # 流式下载文件
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        # 读取内容并进行大小检查
        content = b""
        for chunk in response.iter_content(chunk_size=8192):
            if len(content) + len(chunk) > max_size_bytes:
                raise ValueError(f"文件大小超过最大允许大小 ({max_size_mb} MB)")
            content += chunk

        # 创建临时文件
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path) or "downloaded_file"
        suffix = Path(filename).suffix or ".tmp"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        return temp_path, content

    except requests.RequestException as e:
        raise requests.RequestException(f"从 URL 下载文件失败: {e}")
    except ValueError:
        # 记录在文档字符串中；不得重新包装为 IOError。
        raise
    except Exception as e:
        raise IOError(f"下载文件时出错: {e}")

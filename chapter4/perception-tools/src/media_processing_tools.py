"""
媒体处理工具模块

提供音频、图像和视频处理功能，包括：
- 音频转录（Whisper 本地/API）
- 图像分析（AI 视觉）
- 视频关键帧提取和分析
- 音频/图像元数据提取

所有 LLM 调用统一使用项目配置的客户端。
"""
import json
import logging
import traceback
import subprocess
import base64
import os
import sys
from pathlib import Path
from typing import Union, Dict, Any

import cv2
from PIL import Image
from dotenv import load_dotenv
from mcp.types import TextContent

from base import ActionResponse, validate_file_path

# 添加项目根目录到路径，用于导入统一 LLM 客户端
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

load_dotenv()


# 中文提示词
DEFAULT_IMAGE_ANALYSIS_PROMPT = "请详细描述这张图片的内容"
DEFAULT_VIDEO_ANALYSIS_PROMPT = "分析这段视频并描述其中发生的事情"


def _get_vision_llm_client() -> tuple:
    """
    获取视觉 LLM 客户端

    使用项目根目录 .env 配置，支持多种提供商。

    Returns:
        (client, model): 客户端实例和模型名称

    Raises:
        ValueError: 当没有任何可用配置时

    注意:
        - 优先使用项目统一 LLM 客户端
        - 回退到 OPENAI_API_KEY 环境变量
        - 需要支持视觉功能的模型（如 gpt-4o、claude-sonnet-4）
    """
    from openai import OpenAI

    # 方式 1: 使用项目统一的 LLM 客户端（推荐）
    try:
        from llm.client import get_llm_client
        client = get_llm_client()
        model = client.model_name
        logging.info(f"使用项目配置的 LLM 客户端: provider={client.provider}, model={model}")
        return client, model
    except (ImportError, ValueError):
        pass

    # 方式 2: 使用 OPENAI_API_KEY（回退）
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        base_url = os.getenv("OPENAI_BASE_URL")
        model = os.getenv("PERCEPTION_VISION_MODEL", "gpt-4o")
        client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        logging.info(f"使用 OPENAI_API_KEY: model={model}")
        return client, model

    raise ValueError(
        "未配置 LLM 密钥。请通过项目根目录 .env 文件配置：\n"
        "- API_KEY: 通用 API 密钥\n"
        "- LLM_PROVIDER: 提供商（openai、anthropic 等）\n"
        "- LLM_MODEL: 模型名称（需支持视觉）"
    )


async def transcribe_audio_whisper(
    file_path: str,
    model_size: str = "base",
    language: str = "zh"
) -> Union[str, TextContent]:
    """
    使用 Whisper 转录音频文件

    优先使用本地 Whisper 模型，未安装时回退到 OpenAI API。

    Args:
        file_path: 音频文件路径
        model_size: Whisper 模型大小（tiny, base, small, medium, large）
        language: 语言代码（默认 zh 中文）

    Returns:
        包含转录结果的 TextContent

    注意:
        - 本地 Whisper 需要安装：pip install openai-whisper
        - API 模式需要配置 LLM 客户端

    示例:
        >>> result = await transcribe_audio_whisper("/path/to/audio.wav", language="zh")
        >>> result['transcription']
        '转录的文本内容...'
    """
    try:
        path = validate_file_path(file_path)

        logging.info(f"🎤 正在转录音频: {path}")

        try:
            # 尝试使用本地 Whisper
            import whisper

            # 加载模型
            model = whisper.load_model(model_size)

            # 执行转录
            result = model.transcribe(str(path), language=language)

            transcription = result["text"]

            response_data = {
                "file_name": path.name,
                "file_type": path.suffix,
                "model": model_size,
                "language": language,
                "transcription": transcription,
                "word_count": len(transcription.split())
            }

            logging.info(f"✅ 转录完成: {len(transcription)} 字符")

            action_response = ActionResponse(
                success=True,
                message=response_data,
                metadata={"file_path": str(path), "method": "local_whisper"}
            )

        except ImportError:
            # 回退到 OpenAI API
            from openai import OpenAI

            logging.info("本地 Whisper 未安装，尝试使用 OpenAI API")

            # 尝试从项目配置获取客户端
            try:
                from llm.client import get_llm_client
                client = get_llm_client()
            except (ImportError, ValueError):
                # 回退到环境变量
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ImportError("Whisper 未安装且未找到 LLM 配置")
                client = OpenAI(api_key=api_key)

            with open(path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language
                )

            response_data = {
                "file_name": path.name,
                "file_type": path.suffix,
                "model": "whisper-1 (API)",
                "language": language,
                "transcription": transcription.text,
                "word_count": len(transcription.text.split())
            }

            action_response = ActionResponse(
                success=True,
                message=response_data,
                metadata={"file_path": str(path), "method": "openai_api"}
            )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"音频转录失败: {str(e)}"
        logging.error(f"音频转录错误: {traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "audio_transcription_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def extract_audio_metadata(
    file_path: str
) -> Union[str, TextContent]:
    """
    使用 ffprobe 提取音频文件元数据

    Args:
        file_path: 音频文件路径

    Returns:
        包含音频元数据的 TextContent

    注意:
        - 需要系统安装 ffprobe
        - 返回格式、编码、采样率等信息

    示例:
        >>> result = await extract_audio_metadata("/path/to/audio.mp3")
        >>> result['duration']
        180.5
        >>> result['sample_rate']
        44100
    """
    try:
        path = validate_file_path(file_path)

        logging.info(f"🎵 正在提取音频元数据: {path}")

        # 使用 ffprobe 获取元数据
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            metadata = json.loads(result.stdout)

            format_info = metadata.get("format", {})
            streams = metadata.get("streams", [])
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

            response_data = {
                "file_name": path.name,
                "file_size": path.stat().st_size,
                "duration": float(format_info.get("duration", 0)),
                "bit_rate": int(format_info.get("bit_rate", 0)),
                "format": format_info.get("format_name"),
                "codec": audio_stream.get("codec_name"),
                "sample_rate": int(audio_stream.get("sample_rate", 0)) if audio_stream.get("sample_rate") else None,
                "channels": int(audio_stream.get("channels", 0)) if audio_stream.get("channels") else None
            }

            logging.info(f"✅ 音频元数据提取完成")

            action_response = ActionResponse(
                success=True,
                message=response_data,
                metadata={"file_path": str(path)}
            )
        else:
            raise RuntimeError(f"ffprobe 执行失败: {result.stderr}")

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"音频元数据提取失败: {str(e)}"
        logging.error(f"音频元数据错误: {traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "audio_metadata_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def extract_text_ocr(
    image_path: str,
    language: str = "chi_sim+eng"
) -> Union[str, TextContent]:
    """
    使用 OCR 从图片中提取文字

    Args:
        image_path: 图片文件路径
        language: OCR 语言（默认 chi_sim+eng 中英文混合）

    Returns:
        包含提取文字的 TextContent

    注意:
        - 需要安装 pytesseract：pip install pytesseract
        - 需要系统安装 tesseract-ocr

    示例:
        >>> result = await extract_text_ocr("/path/to/image.png")
        >>> result['extracted_text']
        '识别出的文字...'
    """
    try:
        path = validate_file_path(image_path)

        logging.info(f"🔍 正在进行 OCR 文字识别: {path}")

        try:
            import pytesseract

            img = Image.open(path)
            text = pytesseract.image_to_string(img, lang=language)

            result = {
                "file_name": path.name,
                "image_size": img.size,
                "extracted_text": text,
                "text_length": len(text),
                "word_count": len(text.split()),
                "language": language,
                "method": "pytesseract"
            }

            logging.info(f"✅ OCR 提取完成: {len(text)} 字符")

            action_response = ActionResponse(
                success=True,
                message=result,
                metadata={"file_path": str(path)}
            )

        except ImportError:
            raise ImportError(
                "pytesseract 未安装。请安装: pip install pytesseract\n"
                "同时需要系统安装 tesseract-ocr"
            )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"OCR 文字提取失败: {str(e)}"
        logging.error(f"OCR 错误: {traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "ocr_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def analyze_image_ai(
    image_path: str,
    prompt: str = DEFAULT_IMAGE_ANALYSIS_PROMPT
) -> Union[str, TextContent]:
    """
    使用 AI 分析图片内容

    Args:
        image_path: 图片文件路径
        prompt: 分析提示词（默认为中文提示）

    Returns:
        包含 AI 分析结果的 TextContent

    注意:
        - 需要配置支持视觉的 LLM 模型
        - 图片会进行 base64 编码后发送给模型

    示例:
        >>> result = await analyze_image_ai(
        ...     "/path/to/image.jpg",
        ...     prompt="请描述图片中的主要物体"
        ... )
        >>> result['analysis']
        '图片分析结果...'
    """
    try:
        path = validate_file_path(image_path)

        logging.info(f"🤖 正在使用 AI 分析图片: {path}")

        client, model = _get_vision_llm_client()

        # 编码图片
        with open(path, "rb") as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode('utf-8')

        # 调用视觉 API
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000
        )

        analysis = response.choices[0].message.content

        result = {
            "file_name": path.name,
            "prompt": prompt,
            "analysis": analysis,
            "model": model
        }

        logging.info(f"✅ AI 分析完成")

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
        error_msg = f"AI 图片分析失败: {str(e)}"
        logging.error(f"AI 分析错误: {traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "ai_image_analysis_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def extract_video_keyframes(
    video_path: str,
    num_frames: int = 10
) -> Union[str, TextContent]:
    """
    从视频中提取关键帧

    Args:
        video_path: 视频文件路径
        num_frames: 要提取的关键帧数量

    Returns:
        包含关键帧信息的 TextContent

    注意:
        - 帧按时间间隔均匀分布
        - 返回每帧的时间戳和帧编号

    示例:
        >>> result = await extract_video_keyframes("/path/to/video.mp4", num_frames=5)
        >>> result['keyframes'][0]
        {'frame_number': 0, 'timestamp': 0.0, 'shape': [1080, 1920, 3]}
    """
    try:
        path = validate_file_path(video_path)

        num_frames = max(1, num_frames)

        logging.info(f"🎬 正在从视频中提取关键帧: {path}")

        video = cv2.VideoCapture(str(path))

        fps = video.get(cv2.CAP_PROP_FPS)
        frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0

        # 计算帧间隔
        interval = max(1, frame_count // num_frames)

        keyframes = []
        frame_num = 0

        while len(keyframes) < num_frames and video.isOpened():
            ret, frame = video.read()
            if not ret:
                break

            if frame_num % interval == 0:
                timestamp = frame_num / fps if fps > 0 else 0
                keyframes.append({
                    "frame_number": frame_num,
                    "timestamp": round(timestamp, 2),
                    "shape": list(frame.shape) if frame is not None else None
                })

            frame_num += 1

        video.release()

        result = {
            "file_name": path.name,
            "duration": duration,
            "total_frames": frame_count,
            "fps": fps,
            "keyframes_extracted": len(keyframes),
            "keyframes": keyframes
        }

        logging.info(f"✅ 提取了 {len(keyframes)} 个关键帧")

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
        error_msg = f"关键帧提取失败: {str(e)}"
        logging.error(f"视频处理错误: {traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "video_keyframe_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def analyze_video_ai(
    video_path: str,
    num_frames: int = 5,
    prompt: str = DEFAULT_VIDEO_ANALYSIS_PROMPT
) -> Union[str, TextContent]:
    """
    使用 AI 视觉分析视频内容

    Args:
        video_path: 视频文件路径
        num_frames: 要分析的帧数
        prompt: 分析提示词（默认为中文提示）

    Returns:
        包含 AI 分析结果的 TextContent

    注意:
        - 每帧单独分析，然后汇总
        - 需要配置支持视觉的 LLM 模型

    示例:
        >>> result = await analyze_video_ai(
        ...     "/path/to/video.mp4",
        ...     num_frames=3,
        ...     prompt="描述这个场景"
        ... )
        >>> result['frames_analyzed']
        3
    """
    video = None
    try:
        path = validate_file_path(video_path)

        num_frames = max(1, num_frames)

        logging.info(f"🤖 正在使用 AI 分析视频: {path}")

        client, model = _get_vision_llm_client()

        # 提取关键帧
        video = cv2.VideoCapture(str(path))
        fps = video.get(cv2.CAP_PROP_FPS)
        frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        interval = max(1, frame_count // num_frames)

        # 提取并编码帧
        frame_analyses = []
        frame_num = 0
        frames_analyzed = 0

        while frames_analyzed < num_frames and video.isOpened():
            ret, frame = video.read()
            if not ret:
                break

            if frame_num % interval == 0:
                # 编码帧
                _, buffer = cv2.imencode('.jpg', frame)
                img_base64 = base64.b64encode(buffer).decode('utf-8')

                # 使用 AI 视觉分析
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"{prompt}（第 {frames_analyzed + 1}/{num_frames} 帧）"},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
                                }
                            ]
                        }
                    ],
                    max_tokens=500
                )

                timestamp = frame_num / fps if fps > 0 else 0
                analysis = response.choices[0].message.content

                frame_analyses.append({
                    "frame_number": frame_num,
                    "timestamp": round(timestamp, 2),
                    "analysis": analysis
                })

                frames_analyzed += 1

            frame_num += 1

        # 生成综合摘要
        combined_analyses = "\n\n".join([
            f"第 {i+1} 帧 (t={a['timestamp']}s): {a['analysis']}"
            for i, a in enumerate(frame_analyses)
        ])

        result = {
            "file_name": path.name,
            "frames_analyzed": len(frame_analyses),
            "analyses": frame_analyses,
            "combined_analysis": combined_analyses
        }

        logging.info(f"✅ 分析了 {len(frame_analyses)} 帧")

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
        error_msg = f"视频分析失败: {str(e)}"
        logging.error(f"视频分析错误: {traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "video_analysis_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )
    finally:
        # 释放视频资源
        if video is not None:
            video.release()


async def trim_audio(
    audio_path: str,
    start_time: float,
    duration: float | None = None,
    output_path: str | None = None
) -> Union[str, TextContent]:
    """
    使用 ffmpeg 裁剪音频文件到指定时间范围

    Args:
        audio_path: 音频文件路径
        start_time: 开始时间（秒）
        duration: 持续时间（秒），None 表示裁剪到结尾
        output_path: 输出文件路径，None 表示自动生成

    Returns:
        包含裁剪后音频信息的 TextContent

    注意:
        - 需要系统安装 ffmpeg
        - 输出路径默认为原文件名加上 _trimmed 后缀

    示例:
        >>> result = await trim_audio(
        ...     "/path/to/audio.mp3",
        ...     start_time=30,
        ...     duration=60
        ... )
        >>> result['output_file']
        '/path/to/audio_trimmed.mp3'
    """
    try:
        path = validate_file_path(audio_path)

        logging.info(f"✂️ 正在裁剪音频: {path}")

        # 生成输出路径（如果未提供）
        if output_path is None:
            output_path = str(path.parent / f"{path.stem}_trimmed{path.suffix}")

        # 构建 ffmpeg 命令
        cmd = ["ffmpeg", "-i", str(path), "-ss", str(start_time)]

        if duration is not None:
            cmd.extend(["-t", str(duration)])

        cmd.extend(["-c", "copy", "-y", output_path])

        # 执行 ffmpeg
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 执行失败: {result.stderr}")

        output_file = Path(output_path)

        response_data = {
            "input_file": str(path),
            "output_file": str(output_file),
            "start_time": start_time,
            "duration": duration,
            "file_size": output_file.stat().st_size if output_file.exists() else 0
        }

        logging.info(f"✅ 裁剪后的音频已保存到: {output_path}")

        action_response = ActionResponse(
            success=True,
            message=response_data,
            metadata={"output_path": str(output_path)}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"音频裁剪失败: {str(e)}"
        logging.error(f"音频裁剪错误: {traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "audio_trim_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def get_image_metadata(
    image_path: str
) -> Union[str, TextContent]:
    """
    获取详细的图片元数据（包括 EXIF 数据）

    Args:
        image_path: 图片文件路径

    Returns:
        包含图片元数据的 TextContent

    注意:
        - EXIF 数据包含拍摄时间、相机型号等信息
        - 某些图片可能没有 EXIF 数据

    示例:
        >>> result = await get_image_metadata("/path/to/photo.jpg")
        >>> result['metadata']['format']
        'JPEG'
        >>> result['has_exif']
        True
    """
    try:
        path = validate_file_path(image_path)

        logging.info(f"📷 正在获取图片元数据: {path}")

        img = Image.open(path)

        # 基本元数据
        metadata = {
            "file_name": path.name,
            "format": img.format,
            "mode": img.mode,
            "size": img.size,
            "width": img.width,
            "height": img.height,
            "file_size": path.stat().st_size
        }

        # 尝试获取 EXIF 数据
        try:
            from PIL.ExifTags import TAGS
            exif_data = {}

            if hasattr(img, '_getexif') and img._getexif():
                exif = img._getexif()
                for tag_id, value in exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    exif_data[tag] = str(value)

            if exif_data:
                metadata["exif"] = exif_data
        except Exception as e:
            logging.debug(f"无 EXIF 数据: {e}")

        # 图片信息
        if hasattr(img, 'info'):
            # PIL 的 img.info 通常携带非 JSON 可序列化的值
            # 将字节数据转换为大小标记
            metadata["info"] = {
                k: (f"<{len(v)} 字节>" if isinstance(v, (bytes, bytearray)) else v)
                for k, v in img.info.items()
            }

        result = {
            "metadata": metadata,
            "has_exif": "exif" in metadata
        }

        logging.info(f"✅ 图片元数据提取完成")

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
        error_msg = f"元数据提取失败: {str(e)}"
        logging.error(f"元数据错误: {traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "image_metadata_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

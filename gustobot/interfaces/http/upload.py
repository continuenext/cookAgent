"""
文件上传路由 (/upload)

负责普通文档和图片的上传、访问与删除。
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict, Set

import aiofiles
import aiofiles.os
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from gustobot.config.settings import settings
from gustobot.domain.models.schemas import FileUploadResponse
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="http.upload")

router = APIRouter(prefix="/upload", tags=["文件上传"])

# 上传根目录
_UPLOAD_DIR = Path(settings.BASE_DIR) / "uploads"
_IMAGE_DIR = _UPLOAD_DIR / "images"
_MAX_BYTES = settings.FILE_UPLOAD_MAX_MB * 1024 * 1024

# 允许的文件扩展名
_ALLOWED_FILE_TYPES = {
    ".txt", ".md", ".json", ".csv", ".log",
    ".xlsx", ".xls", ".pdf", ".doc", ".docx",
}

_ALLOWED_IMAGE_TYPES = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
}


async def _handle_upload(
    file: UploadFile,
    allowed_types: Set[str],
    upload_dir: Path,
    url_prefix: str,
) -> FileUploadResponse:
    """文件上传公共逻辑：校验、存储、返回响应。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}，允许: {', '.join(sorted(allowed_types))}",
        )

    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制（最大 {settings.FILE_UPLOAD_MAX_MB} MB）",
        )

    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex
    safe_name = f"{file_id}_{file.filename}"
    save_path = upload_dir / safe_name

    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    logger.info("文件上传成功: %s (%d bytes)", safe_name, len(content))

    return FileUploadResponse(
        file_id=file_id,
        filename=safe_name,
        original_name=file.filename,
        size_bytes=len(content),
        file_path=str(save_path),
        file_url=f"{url_prefix}/{safe_name}",
        file_type=ext,
    )


# ── 文档上传 ──────────────────────────────────────────


@router.post("/file", response_model=FileUploadResponse, summary="上传文档")
async def upload_file(file: UploadFile) -> FileUploadResponse:
    """上传文本/文档文件（txt, excel, pdf 等）"""
    return await _handle_upload(file, _ALLOWED_FILE_TYPES, _UPLOAD_DIR, f"{settings.API_PREFIX}/upload/files")


# ── 图片上传 ──────────────────────────────────────────


@router.post("/image", response_model=FileUploadResponse, summary="上传图片")
async def upload_image(image: UploadFile) -> FileUploadResponse:
    """上传图片文件（jpg, png, webp 等），最大 50 MB。"""
    return await _handle_upload(image, _ALLOWED_IMAGE_TYPES, _IMAGE_DIR, f"{settings.API_PREFIX}/upload/images")


# ── 文件访问 ──────────────────────────────────────────


@router.get("/files/{filename}", summary="获取文档")
async def get_uploaded_file(filename: str) -> FileResponse:
    """获取上传的文档文件。"""
    file_path = _UPLOAD_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    # 防止路径穿越
    if not file_path.resolve().is_relative_to(_UPLOAD_DIR.resolve()):
        raise HTTPException(status_code=400, detail="非法路径")
    return FileResponse(file_path)


@router.get("/images/{filename}", summary="获取图片")
async def get_uploaded_image(filename: str) -> FileResponse:
    """获取上传的图片文件。"""
    file_path = _IMAGE_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    if not file_path.resolve().is_relative_to(_IMAGE_DIR.resolve()):
        raise HTTPException(status_code=400, detail="非法路径")
    return FileResponse(file_path)


# ── 文件删除 ──────────────────────────────────────────


@router.delete("/{file_id}", summary="删除文件")
async def delete_file(file_id: str) -> Dict[str, str]:
    """根据文件 ID 删除文件（文档或图片）。"""
    for search_dir in (_UPLOAD_DIR, _IMAGE_DIR):
        if not search_dir.exists():
            continue
        for file_path in search_dir.glob(f"{file_id}_*"):
            if file_path.is_file():
                await aiofiles.os.remove(file_path)
                logger.info("文件删除成功: %s", file_path)
                return {"status": "success", "message": "文件已删除"}

    raise HTTPException(status_code=404, detail="文件不存在")

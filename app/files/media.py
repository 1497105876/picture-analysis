"""图片媒体提取：哈希、dHash、EXIF、主色调、缩略图、EXIF 剥离。"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
THUMB_SIZE = 256
# 与 PIL 默认防解压炸弹上限一致（Image.MAX_IMAGE_PIXELS 可被外部改动，这里给兜底）
MAX_PIXELS = int(Image.MAX_IMAGE_PIXELS or 178_956_970)


@dataclass(frozen=True)
class MediaInfo:
    md5: str
    dhash: str
    width: int | None
    height: int | None
    bytes: int
    mtime: float
    exif_taken_at: str | None
    dominant_color: str | None


def file_md5(path: Path) -> str:
    import hashlib

    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def perceptual_hash(image: Image.Image) -> str:
    gray = ImageOps.grayscale(image.resize((9, 8)))
    pixels = list(gray.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left = pixels[row * 9 + col]
            right = pixels[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def _exif_taken(image: Image.Image) -> str | None:
    try:
        exif = image.getexif()
        ifd = exif.get_ifd(0x8769)
        raw = ifd.get(36867) or exif.get(306) or exif.get(36867)
        if not raw:
            return None
        parsed = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
        return parsed.isoformat()
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def _dominant_color(image: Image.Image) -> str:
    small = image.convert("RGB").resize((16, 16))
    pixels = list(small.getdata())
    count = len(pixels) or 1
    r = sum(p[0] for p in pixels) // count
    g = sum(p[1] for p in pixels) // count
    b = sum(p[2] for p in pixels) // count
    return f"#{r:02x}{g:02x}{b:02x}"


def _peek_size(path: Path) -> tuple[int, int] | None:
    """不解码像素、只读文件头获取尺寸（超大图防解压炸弹时的兜底）。"""
    try:
        with path.open("rb") as handle:
            head = handle.read(32)
            if head.startswith(b"\x89PNG\r\n\x1a\n"):
                handle.seek(16)
                data = handle.read(8)
                return int(struct.unpack(">I", data[:4])[0]), int(struct.unpack(">I", data[4:8])[0])
            if head.startswith(b"\xff\xd8"):  # JPEG：顺序找 SOF 段
                handle.seek(2)
                while True:
                    marker = handle.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    code = marker[1]
                    if code in (0xD8, 0x01) or 0xD0 <= code <= 0xD7:
                        continue
                    seg_len_bytes = handle.read(2)
                    if len(seg_len_bytes) < 2:
                        return None
                    seg_len = struct.unpack(">H", seg_len_bytes)[0]
                    if seg_len < 2:
                        return None
                    if 0xC0 <= code <= 0xCF and code not in (0xC4, 0xC8, 0xCC):
                        data = handle.read(5)
                        if len(data) < 5:
                            return None
                        return int(struct.unpack(">H", data[3:5])[0]), int(
                            struct.unpack(">H", data[1:3])[0]
                        )
                    handle.seek(seg_len - 2, 1)
            if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
                kind = head[12:16]
                if kind == b"VP8X":
                    handle.seek(24)
                    data = handle.read(6)
                    return (
                        int.from_bytes(data[0:3], "little") + 1,
                        int.from_bytes(data[3:6], "little") + 1,
                    )
                if kind == b"VP8 ":
                    handle.seek(26)
                    data = handle.read(4)
                    return (
                        int(struct.unpack("<H", data[0:2])[0]) & 0x3FFF,
                        int(struct.unpack("<H", data[2:4])[0]) & 0x3FFF,
                    )
                if kind == b"VP8L":
                    handle.seek(21)
                    data = handle.read(4)
                    bits = int.from_bytes(data, "little")
                    return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
                return None
            if head.startswith(b"GIF8"):
                return int(struct.unpack("<H", head[6:8])[0]), int(
                    struct.unpack("<H", head[8:10])[0]
                )
            if head.startswith(b"BM"):
                handle.seek(18)
                data = handle.read(8)
                width, height = struct.unpack("<ii", data)
                return abs(int(width)), abs(int(height))
    except (OSError, struct.error, IndexError):
        return None
    return None


def extract(path: Path) -> MediaInfo:
    stat = path.stat()
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            dhash = perceptual_hash(image)
            taken = _exif_taken(image)
            color = _dominant_color(image)
    except Image.DecompressionBombError:
        # 超出防解压炸弹上限：绝不整图解码（内存炸弹），只读文件头入库，
        # 感知哈希/主色调留空，缩略图与 AI 识图由调用方跳过。
        size = _peek_size(path)
        return MediaInfo(
            md5=file_md5(path),
            dhash="",
            width=int(size[0]) if size else None,
            height=int(size[1]) if size else None,
            bytes=int(stat.st_size),
            mtime=float(stat.st_mtime),
            exif_taken_at=None,
            dominant_color=None,
        )
    return MediaInfo(
        md5=file_md5(path),
        dhash=dhash,
        width=int(width),
        height=int(height),
        bytes=int(stat.st_size),
        mtime=float(stat.st_mtime),
        exif_taken_at=taken,
        dominant_color=color,
    )


def make_thumbnail(path: Path, thumbs_dir: Path, key: str, size: int = THUMB_SIZE) -> Path:
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    dest = thumbs_dir / f"{key}.jpg"
    if dest.exists():
        return dest
    try:
        with Image.open(path) as opened:
            rotated = ImageOps.exif_transpose(opened)
            rotated.thumbnail((size, size))
            if rotated.mode not in ("RGB", "L"):
                rotated = rotated.convert("RGB")
            rotated.save(dest, "JPEG", quality=85)
    except Image.DecompressionBombError as exc:
        raise ValueError(f"图片尺寸过大，无法生成缩略图：{path.name}") from exc
    return dest


def strip_exif(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source) as image:
            clean = ImageOps.exif_transpose(image)
            data = clean.getdata()
            output = Image.new(clean.mode, clean.size)
            output.putdata(data)
            if output.mode != "RGB":
                output = output.convert("RGB")
            output.save(dest, "JPEG", quality=92)
    except Image.DecompressionBombError as exc:
        raise ValueError(f"图片尺寸过大，无法导出：{source.name}") from exc


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False

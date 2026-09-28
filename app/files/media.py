"""图片媒体提取：哈希、dHash、EXIF、主色调、缩略图、EXIF 剥离。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
THUMB_SIZE = 256


@dataclass(frozen=True)
class MediaInfo:
    md5: str
    dhash: str
    width: int
    height: int
    bytes: int
    mtime: float
    exif_taken_at: str | None
    dominant_color: str


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


def extract(path: Path) -> MediaInfo:
    stat = path.stat()
    with Image.open(path) as image:
        image.load()
        width, height = image.size
        dhash = perceptual_hash(image)
        taken = _exif_taken(image)
        color = _dominant_color(image)
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
    with Image.open(path) as opened:
        rotated = ImageOps.exif_transpose(opened)
        rotated.thumbnail((size, size))
        if rotated.mode not in ("RGB", "L"):
            rotated = rotated.convert("RGB")
        rotated.save(dest, "JPEG", quality=85)
    return dest


def strip_exif(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        clean = ImageOps.exif_transpose(image)
        data = clean.getdata()
        output = Image.new(clean.mode, clean.size)
        output.putdata(data)
        if output.mode != "RGB":
            output = output.convert("RGB")
        output.save(dest, "JPEG", quality=92)


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False

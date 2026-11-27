"""Save a P-Gure figure using the filename extension to select the encoder."""

from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from .model import Topology
from .style import Style
from .svg import render_svg


_FORMATS = {".svg": "SVG", ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WebP"}


def _write_raster(svg: str, output: BinaryIO, image_format: str) -> None:
    try:
        from resvg_py import svg_to_bytes
        from PIL import Image
    except ModuleNotFoundError as error:
        if error.name not in {"resvg_py", "PIL"}:
            raise
        raise ImportError("Raster export requires the pgure[raster] extra.") from error

    png = svg_to_bytes(svg_string=svg, background="#ffffff")
    if image_format == "PNG":
        output.write(png)
        return
    with Image.open(BytesIO(png)) as image:
        if image_format == "JPEG":
            image.convert("RGB").save(output, format="JPEG", quality=95, subsampling=0)
        else:
            image.save(output, format="WEBP", lossless=True)


def save_figure(graph: Topology, path: str | Path, *, style: Style | None = None,
                scale: float = 1) -> Path:
    """Save an SVG, PNG, JPEG, or WebP file and return its path."""
    path = Path(path)
    image_format = _FORMATS.get(path.suffix.lower())
    if image_format is None:
        raise ValueError(f"unsupported figure extension {path.suffix!r}, expected one of {', '.join(_FORMATS)}")
    svg = render_svg(graph, style=style, scale=scale)
    # Replace the destination only once its encoder has finished writing.
    output = NamedTemporaryFile(dir=path.parent, delete=False)
    temporary = Path(output.name)
    try:
        with output:
            if image_format == "SVG":
                output.write(svg.encode("utf-8"))
            else:
                _write_raster(svg, output, image_format)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path

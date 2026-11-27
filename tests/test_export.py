import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from pgure import Style, parse, render_svg, save_figure


class ExportTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.graph = parse("""
name: T
peers: [{id: A, role: source}]
links: [{source: A, target: B}]
views: [{title: Route, messages: [{path: [A, B], placement: outside}]}]
""")
        self.style = Style(peer_fills={"source": "#ff8800"})

    def test_svg_file_and_scaled_viewport(self):
        path = self.directory / "figure.SVG"
        self.assertEqual(save_figure(self.graph, str(path)), path)
        svg = path.read_text(encoding="utf-8")
        self.assertEqual(svg, render_svg(self.graph))
        save_figure(self.graph, path, scale=2)
        original = ET.fromstring(svg)
        scaled = ET.parse(path).getroot()
        self.assertEqual(scaled.get("viewBox"), original.get("viewBox"))
        for axis in ("width", "height"):
            self.assertEqual(int(scaled.get(axis)), 2 * int(original.get(axis)))

    def test_failed_export_preserves_existing_file(self):
        path = self.directory / "figure.png"
        path.write_bytes(b"previous figure")
        for scale in (0, -1, float("inf"), float("nan")):
            with self.subTest(scale=scale), self.assertRaisesRegex(ValueError, "scale"):
                save_figure(self.graph, path, scale=scale)
        with patch.dict("sys.modules", {"resvg_py": None}):
            with self.assertRaisesRegex(ImportError, r"pgure\[raster\]"):
                save_figure(self.graph, path)
        with self.assertRaisesRegex(ValueError, "extension"):
            save_figure(self.graph, self.directory / "figure.unknown")
        self.assertEqual(path.read_bytes(), b"previous figure")
        self.assertEqual(list(self.directory.iterdir()), [path])

    @unittest.skipUnless(find_spec("resvg_py") and find_spec("PIL"), "requires pgure[raster]")
    def test_raster_formats(self):
        from PIL import Image

        svg = ET.fromstring(render_svg(self.graph))
        expected_size = tuple(round(int(svg.get(axis)) * 1.5) for axis in ("width", "height"))
        for suffix, image_format in [(".PNG", "PNG"), (".jpg", "JPEG"), (".JPEG", "JPEG"), (".webp", "WEBP")]:
            with self.subTest(suffix=suffix):
                path = save_figure(self.graph, self.directory / ("figure" + suffix),
                                   scale=1.5, style=self.style)
                with Image.open(path) as image:
                    image.load()
                    self.assertEqual(image.format, image_format)
                    self.assertEqual(image.size, expected_size)
                    rgb = image.convert("RGB")
                    self.assertEqual(rgb.getpixel((0, 0)), (255, 255, 255))
                    # The styled peer interior survives both rasterization and lossy JPEG encoding.
                    colors = rgb.getcolors(maxcolors=rgb.width * rgb.height)
                    self.assertTrue(any(count > 30 and r > 240 and 120 < g < 150 and b < 15
                                        for count, (r, g, b) in colors))

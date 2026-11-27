import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from pgure import FigureError, Style, load, load_style, parse, render_svg, save_figure


SOURCE = """name: Sample
peers: [{id: A, role: origin}]
links:
  - {source: A, target: B, kind: bridge, directed: true}
  - {source: B, target: C}
views: [{title: Delivery, messages: [{path: [A, B], kind: bridge}, {path: [B, C]}]}]
"""
SHEET = """peers:
  default: {fill: ivory, stroke: gray, width: 2, line: dotted}
  roles:
    origin: {fill: navy, label_color: white, line: solid}
links:
  default: {color: olive, width: 3}
  kinds:
    bridge: {line: "--"}
messages:
  default: {color: teal, line: ":"}
  kinds:
    bridge: {color: chocolate, line: [8, 3, 2, 3]}
"""


class StylesheetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.source = root / "round.1.yml"
        self.source.write_text(SOURCE, encoding="utf-8")
        self.meta = root / "round.1.meta.yaml"
        self.meta.write_text(SHEET, encoding="utf-8")

    def test_companion_cascades_by_role_and_kind(self):
        graph = load(self.source)
        output = save_figure(graph, self.source.with_suffix(".svg"))
        panel = ET.parse(output).getroot().find("{*}g[@class='panel']")
        origin = panel.find("{*}g[@data-id='A']")
        other = panel.find("{*}g[@data-id='B']/{*}circle")
        self.assertEqual((origin[0].get("fill"), origin[0].get("stroke"), origin[0].get("stroke-width")),
                         ("navy", "gray", "2"))
        self.assertIsNone(origin[0].get("stroke-dasharray"))
        self.assertIsNone(origin[0].get("stroke-linecap"))
        self.assertEqual(origin[1].get("fill"), "white")
        self.assertEqual((other.get("fill"), other.get("stroke-linecap")), ("ivory", "round"))
        tagged, plain = panel.findall("{*}g[@class='link']")
        self.assertEqual((tagged[0].get("stroke"), tagged[0].get("stroke-width"),
                          tagged[0].get("stroke-dasharray")), ("olive", "3", "6 3"))
        self.assertEqual(tagged[1].get("stroke"), "olive")
        self.assertIsNone(plain[0].get("stroke-dasharray"))
        first, second = panel.findall("{*}g[@class='message']")
        self.assertEqual((first[0].get("stroke-dasharray"), first[1].get("fill")), ("8 3 2 3", "chocolate"))
        self.assertEqual((second[0].get("stroke-linecap"), second[1].get("fill")), ("round", "teal"))

    def test_explicit_sheet_and_render_override(self):
        shared = self.source.parent / "shared.meta.yaml"
        shared.write_text("peers: {default: {fill: coral}}", encoding="utf-8")
        graph = load(self.source, meta=shared)
        self.assertEqual(render_svg(graph), render_svg(parse(SOURCE), style=load_style(shared)))
        self.assertIn('fill="coral"', render_svg(graph))
        self.assertEqual(render_svg(graph, style=Style()), render_svg(parse(SOURCE)))
        shared.unlink()
        with self.assertRaises(FileNotFoundError):
            load(self.source, meta=shared)
        self.meta.unlink()
        self.assertEqual(render_svg(load(self.source)), render_svg(parse(SOURCE)))

    def test_invalid_companion_reports_its_own_field_and_location(self):
        for rule, field in [("width: -1", "width"), ("width: true", "width"),
                            ("width: .nan", "width"), ("line: broken", "line"),
                            ("line: [0, 0]", "line"), ("color: null", "color"),
                            ("colour: red", "colour"), ("placement: side", "placement"),
                            ("placement: null", "placement")]:
            with self.subTest(rule=rule), self.assertRaises(FigureError) as caught:
                self.meta.write_text(f"links:\n  kinds:\n    bridge:\n      {rule}\n", encoding="utf-8")
                load(self.source)
            self.assertEqual(caught.exception.source, str(self.meta))
            self.assertEqual(caught.exception.path, ("links", "kinds", "bridge", field))
            self.assertEqual(caught.exception.line, 4)

    def test_placement_cascade_is_resolved_per_hop(self):
        self.source.write_text("""name: T
links: [{source: A, target: B, kind: bridge}, {source: B, target: C}]
views:
  - {title: Delivery, messages: [{path: [A, B, C], kind: delivery}]}
  - {title: Reply, messages: [{path: [C, B, A], kind: reply}]}
  - {title: Automatic, messages: [{path: [A, B, C], kind: retry}]}
""", encoding="utf-8")
        sheet = """links:
  default: {placement: outside}
  kinds: {bridge: {placement: outside}}
messages:
  default: {placement: overlay}
  kinds:
    delivery: {color: teal}
    reply: {placement: overlay}
    retry: {placement: auto}
"""

        def placements(text):
            self.meta.write_text(text, encoding="utf-8")
            svg = ET.fromstring(render_svg(load(self.source)))
            return [[path.get("data-placement") for path in panel.findall(".//{*}path[@data-placement]")]
                    for panel in svg.findall("{*}g[@class='panel']")]

        self.assertEqual(placements(sheet), [["outside", "overlay"], ["overlay", "overlay"],
                                             ["overlay", "overlay"]])
        self.assertEqual(placements(sheet.replace("  default: {placement: overlay}\n", ""))[0],
                         ["outside", "outside"])

    def test_named_lines_and_zero_width(self):
        for name, pattern in [("-", None), ("solid", None), ("--", "6 3"), ("dashed", "6 3"),
                              (":", "0 3"), ("dotted", "0 3"), ("-.", "6 3 1 3"), ("dash-dot", "6 3 1 3")]:
            with self.subTest(name=name):
                self.meta.write_text(f'links: {{default: {{line: "{name}", width: 0}}}}', encoding="utf-8")
                root = ET.fromstring(render_svg(load(self.source)))
                link = root.find(".//{*}g[@class='link']")
                self.assertEqual(link[0].get("stroke-dasharray"), pattern)
                self.assertEqual(link[0].get("stroke-width"), "0")
                self.assertEqual(len(link), 1)

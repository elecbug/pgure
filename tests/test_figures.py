import re
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from pgure import DSLError, Message, Stroke, Style, Topology, load, parse, render_svg


DOCS = Path(__file__).resolve().parents[1] / "docs"
SVG = {"s": "http://www.w3.org/2000/svg"}


class DescriptionTests(unittest.TestCase):
    def test_fanout_placement_and_validation(self):
        graph = parse('topology T { A -- outside, C\nview "V" { send A -> outside, C : probe @outside } }')
        self.assertEqual(graph.views[0].messages, (
            Message(("A", "outside"), "probe", placement="outside"),
            Message(("A", "C"), "probe", placement="outside"),
        ))
        with self.assertRaisesRegex(DSLError, "2:27 in view 'V': unknown placement"):
            parse('topology T { A -- B\nview "V" { send A -> B   @side } }')
        with self.assertRaisesRegex(DSLError, "no link for hop B -> A"):
            parse('topology T { A -> B\nview "V" { send B -> A @outside } }')
        with self.assertRaisesRegex(ValueError, "unknown message placement"):
            Message(("A", "B"), placement="side")

    def test_forward_references_and_fanout(self):
        graph = parse('''topology T {
    view "First" { send A -> B, C : lazy }
    B, C : relay
    A -> B, C : mesh
    node E
    view "First" {}
}''')
        self.assertEqual(graph.peers, {"A": None, "B": "relay", "C": "relay", "E": None})
        self.assertEqual([link.kind for link in graph.links], ["mesh", "mesh"])
        first, second = graph.views
        self.assertEqual(first.messages, (Message(("A", "B"), "lazy"), Message(("A", "C"), "lazy")))
        self.assertEqual(first.title, second.title)
        self.assertEqual(second.messages, ())

    def test_duplicate_links_roles_and_default_view(self):
        graph = parse("topology T {\nnode A, A\nA -- B\nB -- A : mesh\nA -- B\nB : relay\nB : relay\n}")
        self.assertEqual(len(graph.links), 1)
        self.assertEqual(graph.links[0].kind, "mesh")
        self.assertEqual(graph.views[0].title, "T")
        self.assertFalse(graph.views[0].messages)

    def test_strings_comments_and_line_endings(self):
        source = r'''topology T {
  node N   # an isolated peer
  view "단계 #1 \"OK\" \\ <&>" {}
}'''.replace("\n", "\r\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.pgure"
            path.write_bytes(source.encode())
            graph = load(path)
        expected = '단계 #1 "OK" \\ <&>'
        self.assertEqual(graph.views[0].title, expected)
        self.assertEqual(ET.fromstring(render_svg(graph)).find(".//s:text", SVG).text, expected)

    def test_conflicting_links_and_annotations(self):
        for declarations in [
            "A -- B\nA -> B", "B -> A\nA -- B", "A -- A", "A -> A",
            "A -- B : first\nB -- A : second", "node A\nA : source\nA : relay",
        ]:
            with self.subTest(declarations=declarations), self.assertRaises(DSLError):
                parse("topology T {\n" + declarations + "\n}")
        graph = parse("topology T {\nA -> B : x\nB -> A : y\n}")
        self.assertEqual([link.kind for link in graph.links], ["x", "y"])

    def test_semantic_diagnostics_pinpoint_the_use(self):
        for statement, column, detail in [
            ("send B -> A", 10, "B -> A"),
            ("send A -> B -> C", 15, "B -> C"),
            ("send A -> B, X", 18, "unknown peer 'X'"),
        ]:
            with self.subTest(statement=statement):
                source = 'topology T {\nnode C\nview "Round" {\n    ' + statement + "\n}\nA -> B\n}"
                with self.assertRaises(DSLError) as raised:
                    parse(source, source="case.pgure")
                error = raised.exception
                self.assertEqual((error.source, error.line, error.column, error.view),
                                 ("case.pgure", 4, column, "Round"))
                self.assertIn(detail, str(error))
        with self.assertRaisesRegex(DSLError, "unknown peer 'X'"):
            parse("topology T { X : relay }")

    def test_syntax_errors(self):
        for source in [
            "", "topology T {}", "topology view { node A }", "topology T { node A node B }",
            "topology T { node A; }", "topology T { node A", "topology T { send A -> B }",
            'topology T { view "V" { send A -> B -> C, D } }',
            'topology T { view "V" { send A -> B, C -> D } }',
            r'topology T { view "bad\q" {} }', 'topology T { view "unfinished }',
            "topology T { node A }\ntopology U { node B }",
        ]:
            with self.subTest(source=source), self.assertRaises(DSLError):
                parse(source)

    def test_failed_python_updates_preserve_existing_topology(self):
        graph = Topology("T")
        graph.add_link("A", "B", directed=True)
        graph.add_view("valid", [Message(("A", "B"))])
        with self.assertRaisesRegex(ValueError, "B -> A"):
            graph.add_view("invalid", [Message(("A", "B")), Message(("B", "A"))])
        with self.assertRaises(ValueError):
            graph.add_link("C", "C")
        self.assertEqual([view.title for view in graph.views], ["valid"])
        self.assertEqual(set(graph.peers), {"A", "B"})


class RenderTests(unittest.TestCase):
    def test_placement_guide_overlay_and_outward_arc(self):
        guide = (DOCS / "figure-dsl.md").read_text(encoding="utf-8")
        source = guide.split("```text\ntopology Placement", 1)[1].split("```", 1)[0]
        svg = render_svg(parse("topology Placement" + source))
        self.assertEqual(svg, (DOCS / "message-placement.svg").read_text(encoding="utf-8"))
        overlay, outside = ET.fromstring(svg).findall("s:g[@class='panel']", SVG)
        base = {(g.get("data-source"), g.get("data-target")): g[0].get("d")
                for g in overlay.findall("s:g[@class='link']", SVG)}

        def control_y(path):
            return float(path.split(" Q")[1].split()[0].split(",")[1])

        for i, hop in enumerate([("A", "B"), ("B", "D")]):
            along = overlay.findall(".//s:path[@data-placement='overlay']", SVG)[i].get("d")
            arc = outside.findall(".//s:path[@data-placement='outside']", SVG)[i].get("d")
            self.assertEqual(along, base[hop])
            # The outside arc of each upper link bends above its centerline.
            self.assertLess(control_y(arc), control_y(along))

    def test_overlay_on_curved_links_in_either_direction(self):
        graph = parse('''topology T {
    A -- B, C, D
    B -- D
    C -> D
    view "V" {
        send D -> B @overlay
        send C -> D @overlay
    }
}''')
        panel = ET.fromstring(render_svg(graph)).find("s:g[@class='panel']", SVG)

        def points(path):
            return re.findall(r"[-\d.]+,[-\d.]+", path.get("d"))

        links = {(g.get("data-source"), g.get("data-target")): points(g[0])
                 for g in panel.findall("s:g[@class='link']", SVG)}
        backward, forward = panel.findall(".//s:path[@data-placement='overlay']", SVG)
        self.assertEqual(points(backward), list(reversed(links["B", "D"])))
        self.assertEqual(points(forward), links["C", "D"])

    def test_explicit_overlays_reserve_the_link_for_both_directions(self):
        graph = parse('''topology T {
    A -- B
    view "V" {
        send B -> A
        send A -> B @outside
        send A -> B @overlay
        send A -> B @overlay
    }
    view "W" { send A -> B }
}''')
        paths = ET.fromstring(render_svg(graph)).findall(".//s:path[@data-placement]", SVG)
        self.assertEqual([p.get("data-placement") for p in paths],
                         ["outside", "outside", "overlay", "overlay", "overlay"])
        self.assertEqual(len({p.get("d") for p in paths[2:]}), 1)

    def test_guide_examples_and_svg_match(self):
        # Keep the figure, downloadable source, and guide example in sync.
        guide = (DOCS / "figure-dsl.md").read_text(encoding="utf-8")
        code = guide.split("```text\n", 1)[1].split("```", 1)[0]
        self.assertEqual(code, (DOCS / "gossip.pgure").read_text(encoding="utf-8"))
        graph = parse(code)
        network = Topology("Gossip")
        for a, b in [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]:
            network.add_link(a, b)
        for peer, role in [("A", "source"), ("B", "relay"), ("C", "relay"), ("D", "destination")]:
            network.set_role(peer, role)
        network.add_view("Via B", [Message(("A", "B", "D"), "eager")])
        network.add_view("Via C", [Message(("A", "C", "D"), "lazy")])
        style = Style(messages={"eager": Stroke("#145f91"), "lazy": Stroke("#995321", "6 3")})
        svg = render_svg(graph, style=style)
        self.assertEqual(svg, render_svg(network, style=style))
        self.assertEqual(svg, (DOCS / "gossip.svg").read_text(encoding="utf-8"))
        panels = ET.fromstring(svg).findall("s:g[@class='panel']", SVG)
        self.assertEqual(len(panels), 2)
        coordinates = []
        for panel in panels:
            self.assertEqual(len(panel.findall("s:g[@class='link']", SVG)), 4)
            circles = panel.findall("s:g[@class='peer']/s:circle", SVG)
            self.assertEqual(len(circles), 4)
            coordinates.append([(circle.get("cx"), circle.get("cy")) for circle in circles])
        self.assertEqual(coordinates[0], coordinates[1])
        self.assertIsNotNone(panels[1].find(".//s:path[@stroke-dasharray='6 3']", SVG))

    def test_direction_markers_style_and_repeated_messages(self):
        graph = parse('''topology T {
    A -> B : up
    B -> A : down
    A : source
    view "Both" {
        send A -> B : normal
        send A -> B : retry
        send B -> A : normal
    }
}''')
        style = Style(peer_fills={"source": "gold"}, links={"up": Stroke("black", "2 1")},
                      messages={"retry": Stroke("brown")})
        svg = ET.fromstring(render_svg(graph, style=style))
        links = svg.findall(".//s:g[@class='link']", SVG)
        self.assertEqual(len(links), 2)
        self.assertNotEqual(links[0][0].get("d"), links[1][0].get("d"))
        self.assertEqual(links[0][0].get("stroke-dasharray"), "2 1")
        self.assertEqual(links[0][1].get("fill"), "none")
        messages = svg.findall(".//s:g[@class='message']", SVG)
        self.assertEqual([m.get("data-path") for m in messages], ["A B", "A B", "B A"])
        self.assertNotEqual(messages[0][0].get("d"), messages[1][0].get("d"))
        self.assertEqual(messages[1][1].get("fill"), "brown")
        self.assertEqual(svg.find(".//s:g[@data-role='source']/s:circle", SVG).get("fill"), "gold")

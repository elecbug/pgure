import re
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from pgure import FigureError, Message, Stroke, Style, Topology, from_dict, load, load_style, parse, render_svg


DOCS = Path(__file__).resolve().parents[1] / "docs"
SVG = {"s": "http://www.w3.org/2000/svg"}


class DescriptionTests(unittest.TestCase):
    def test_forward_references_and_fanout(self):
        graph = parse("""
views:
  - {title: First, messages: [{path: [A, B], kind: lazy}, {path: [A, C], kind: lazy}]}
  - {title: First}
links:
  - {source: A, target: B, directed: true, kind: mesh}
  - {source: A, target: C, directed: true, kind: mesh}
peers: [{id: B, role: relay}, {id: C, role: relay}, {id: E}]
name: T
""")
        self.assertEqual(graph.peers, {"A": None, "B": "relay", "C": "relay", "E": None})
        self.assertEqual([link.kind for link in graph.links], ["mesh", "mesh"])
        first, second = graph.views
        self.assertEqual(first.messages, (Message(("A", "B"), "lazy"), Message(("A", "C"), "lazy")))
        self.assertEqual(first.title, second.title)
        self.assertEqual(second.messages, ())

    def test_duplicate_declarations_and_default_view(self):
        graph = parse("""
name: T
peers: [{id: A}, {id: A}, {id: B, role: relay}, {id: B, role: relay}]
links: [{source: A, target: B}, {source: B, target: A, kind: mesh}, {source: A, target: B}]
""")
        self.assertEqual(len(graph.links), 1)
        self.assertEqual(graph.links[0].kind, "mesh")
        self.assertEqual(graph.views[0].title, "T")
        self.assertFalse(graph.views[0].messages)

    def test_yaml_strings_comments_and_identifiers(self):
        source = r'''name: view
peers: [{id: peer-1}, {id: on}, {id: "42"}, {id: 피어}]  # isolated peers
views:
  - title: '단계 #1 "OK" \ <&>'
'''.replace("\n", "\r\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.yml"
            path.write_bytes(source.encode())
            graph = load(path)
        self.assertEqual(set(graph.peers), {"peer-1", "on", "42", "피어"})
        self.assertEqual(graph.views[0].title, '단계 #1 "OK" \\ <&>')
        self.assertEqual(ET.fromstring(render_svg(graph)).find(".//s:text", SVG).text, graph.views[0].title)

    def test_conflicting_links_and_annotations(self):
        for fragment in [
            "links: [{source: A, target: B}, {source: B, target: A, directed: true}]",
            "links: [{source: A, target: A}]",
            "links: [{source: A, target: B, kind: x}, {source: B, target: A, kind: y}]",
            "peers: [{id: A, role: source}, {id: A, role: relay}]",
        ]:
            with self.subTest(fragment=fragment), self.assertRaises(FigureError):
                parse("name: T\n" + fragment)

    def test_bad_hop_reports_field_and_source_position(self):
        source = """name: T
peers: [{id: C}]
links: [{source: A, target: B, directed: true}]
views:
  - title: Round
    messages:
      - path: [A, B, C]
"""
        for path, peer_index, column, detail in [
            ("A, B, C", 1, 19, "B -> C"),
            ("B, A", 0, 16, "B -> A"),
            ("A, B, X", 2, 22, "unknown peer 'X'"),
        ]:
            with self.subTest(path=path), self.assertRaises(FigureError) as raised:
                parse(source.replace("A, B, C", path), source="case.yaml")
            error = raised.exception
            self.assertEqual((error.source, error.line, error.column), ("case.yaml", 7, column))
            self.assertEqual(error.path, ("views", 0, "messages", 0, "path", peer_index))
            self.assertIn("Round", str(error))
            self.assertIn(detail, str(error))

    def test_invalid_yaml_and_document_shapes(self):
        for source in [
            "", "[]", "name: [", "name: T", "name: T\nname: U\npeers: [{id: A}]",
            "name: T\n---\nname: U", "!!python/name:builtins.str", "name: T\nnodes: [A]",
            "name: T\npeers: A", "name: T\npeers: [true]", "name: T\npeers: [{id: 42}]",
            "name: T\nlinks: [{source: A}]", "name: T\nlinks: [{source: A, target: B, directed: 'false'}]",
            "name: T\nviews: [{title: 1}]", "name: T\nviews: [{title: Test, messages: [{path: AB}]}]",
            "name: T\nviews: [{title: Test, messages: [{path: [A]}]}]",
        ]:
            with self.subTest(source=source), self.assertRaises(FigureError):
                parse(source)

    def test_inline_placement_points_to_the_stylesheet(self):
        source = "name: T\nlinks: [{source: A, target: B}]\nviews: [{title: V, messages: [{path: [A, B], placement: outside}]}]"
        with self.assertRaisesRegex(FigureError, r"\.meta\.yaml") as raised:
            parse(source)
        self.assertEqual(raised.exception.path, ("views", 0, "messages", 0, "placement"))

    def test_mapping_and_yaml_load_the_same_data(self):
        peers = [{"id": "B", "role": "relay"}]
        data = {"name": "T", "peers": peers, "links": [{"source": "A", "target": "B"}]}
        graph = from_dict(data)
        yaml_graph = parse("name: T\npeers: [{id: B, role: relay}]\nlinks: [{source: A, target: B}]")
        self.assertEqual(render_svg(graph), render_svg(yaml_graph))
        self.assertEqual(peers, [{"id": "B", "role": "relay"}])
        with self.assertRaises(FigureError) as raised:
            from_dict({"name": "T", "links": [{}]})
        self.assertEqual(raised.exception.path, ("links", 0, "source"))

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
        svg = render_svg(load(DOCS / "message-placement.yaml"))
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
        graph = parse("""
name: T
links:
  - {source: A, target: B}
  - {source: A, target: C}
  - {source: A, target: D}
  - {source: B, target: D}
  - {source: C, target: D, directed: true}
views:
  - title: V
    messages: [{path: [D, B], kind: request}, {path: [C, D], kind: request}]
""")
        style = load_style(DOCS / "message-placement.meta.yaml")
        panel = ET.fromstring(render_svg(graph, style=style)).find("s:g[@class='panel']", SVG)

        def points(path):
            return re.findall(r"[-\d.]+,[-\d.]+", path.get("d"))

        links = {(g.get("data-source"), g.get("data-target")): points(g[0])
                 for g in panel.findall("s:g[@class='link']", SVG)}
        backward, forward = panel.findall(".//s:path[@data-placement='overlay']", SVG)
        self.assertEqual(points(backward), list(reversed(links["B", "D"])))
        self.assertEqual(points(forward), links["C", "D"])

    def test_explicit_overlays_reserve_the_link_for_both_directions(self):
        graph = parse("""
name: T
links: [{source: A, target: B}]
views:
  - title: V
    messages:
      - {path: [B, A]}
      - {path: [A, B], kind: retry}
      - {path: [A, B], kind: request}
      - {path: [A, B], kind: request}
  - {title: W, messages: [{path: [A, B]}]}
""")
        style = load_style(DOCS / "message-placement.meta.yaml")
        paths = ET.fromstring(render_svg(graph, style=style)).findall(".//s:path[@data-placement]", SVG)
        self.assertEqual([p.get("data-placement") for p in paths],
                         ["outside", "outside", "overlay", "overlay", "overlay"])
        self.assertEqual(len({p.get("d") for p in paths[2:]}), 1)

    def test_guide_examples_and_svg_match(self):
        # Keep the figure, downloadable source, and guide example in sync.
        guide = (DOCS / "figure-yaml.md").read_text(encoding="utf-8")
        code = guide.split("```yaml\n", 1)[1].split("```", 1)[0]
        self.assertEqual(code, (DOCS / "gossip.yaml").read_text(encoding="utf-8"))
        graph = load(DOCS / "gossip.yaml")
        network = Topology("Gossip")
        for a, b in [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]:
            network.add_link(a, b)
        for peer, role in [("A", "source"), ("B", "relay"), ("C", "relay"), ("D", "destination")]:
            network.set_role(peer, role)
        network.add_view("Via B", [Message(("A", "B", "D"), "eager")])
        network.add_view("Via C", [Message(("A", "C", "D"), "lazy")])
        svg = render_svg(graph)
        self.assertEqual(svg, render_svg(network, style=graph.style))
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
        graph = parse("""
name: T
peers: [{id: A, role: source}]
links:
  - {source: A, target: B, directed: true, kind: up}
  - {source: B, target: A, directed: true, kind: down}
views:
  - title: Both
    messages:
      - {path: [A, B], kind: normal}
      - {path: [A, B], kind: retry}
      - {path: [B, A], kind: normal}
""")
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

import math
import random
import tempfile
import unittest
from itertools import combinations
from pathlib import Path
from xml.etree import ElementTree as ET

from pgure import FigureError, GroupStyle, Style, Topology, from_dict, load, parse, render_svg


def edges_in(graph, group_id):
    members = set(graph.groups[group_id].members)
    return {(link.source, link.target) for link in graph.links if link.source in members}


class GenerationTests(unittest.TestCase):
    def test_default_model_and_seed(self):
        graph = parse("name: Sample\ngroups: [{id: A, n: 13}]")
        group = graph.groups["A"]
        self.assertEqual(tuple(graph.peers), tuple(f"A-{i}" for i in range(1, 14)))
        self.assertEqual((group.domain, group.params, graph.seed), ("er", {"p": 0.25}, 0))
        duplicate = Topology("Sample")
        duplicate.add_group("A", 13)
        self.assertEqual(duplicate.links, graph.links)

    def test_seeds_are_independent_of_order_and_global_random_state(self):
        specs = [{"id": "A", "n": 24}, {"id": "B", "n": 17, "seed": -1}]

        def build(seed, groups):
            return from_dict({"name": "Sample", "seed": seed, "groups": groups})

        before = random.getstate()
        original = build(42, specs)
        reordered = build(42, [{"id": "Extra", "n": 5}, *reversed(specs)])
        changed = build(43, specs)
        self.assertEqual(original.groups["B"].seed, -1)
        self.assertEqual(original.groups["A"].seed, reordered.groups["A"].seed)
        self.assertEqual(edges_in(original, "A"), edges_in(reordered, "A"))
        self.assertNotEqual(edges_in(original, "A"), edges_in(changed, "A"))
        self.assertEqual(edges_in(original, "B"), edges_in(changed, "B"))
        self.assertEqual(random.getstate(), before)
        for group in reordered.groups.values():
            self.assertTrue(all(b in group.members for a, b in edges_in(reordered, group.id)))

    def test_model_parameters_and_small_groups(self):
        for domain, n, params, expected in [
            ("er", 10, {"p": 0}, 0), ("er", 10, {"p": 1e-20}, 0), ("ER", 10, {"p": 1}, 45),
            ("ws", 2, {}, 0), ("WS", 9, {"k": 4, "beta": 1}, 18),
            ("ba", 10, {"m": 2}, 16), ("ring", 1, {}, 0), ("ring", 2, {}, 1),
            ("ring", 8, {}, 8), ("mesh", 1, {}, 0), ("mesh", 5, {}, 10),
        ]:
            with self.subTest(domain=domain, n=n, params=params):
                graph = Topology("Sample")
                graph.add_group("P", n, domain=domain, params=params)
                self.assertEqual(len(graph.peers), n)
                self.assertEqual(len(graph.links), expected)
                self.assertTrue(all(not e.directed and e.source != e.target for e in graph.links))
        lattice = Topology("Regular")
        lattice.add_group("W", 20, domain="ws", params={"k": 4, "beta": 0}, seed=3)
        rewired = Topology("Rewired")
        rewired.add_group("W", 20, domain="ws", params={"k": 4, "beta": 1}, seed=3)
        expected = {tuple(sorted((f"W-{i+1}", f"W-{(i+j)%20+1}"))) for i in range(20) for j in (1, 2)}
        self.assertEqual(edges_in(lattice, "W"), expected)
        self.assertNotEqual(edges_in(rewired, "W"), expected)
        self.assertEqual(len(lattice.links), len(rewired.links))

    def test_roles_and_messages_can_reference_generated_ids(self):
        graph = parse("""name: Demo
peers: [{id: R-1, role: source}, {id: external}]
views: [{title: One hop, messages: [{path: [R-1, R-2]}]}]
links: [{source: R-2, target: R-1, kind: local}]
groups: [{id: R, domain: ring, n: 3}]
""")
        self.assertEqual(graph.peers["R-1"], "source")
        self.assertEqual(len(graph.links), 3)
        root = ET.fromstring(render_svg(graph))
        self.assertIsNotNone(root.find(".//{*}g[@data-kind='local']"))
        self.assertIsNotNone(root.find(".//{*}g[@data-path='R-1 R-2']"))
        self.assertIsNotNone(root.find(".//{*}g[@data-id='external']"))
        self.assertEqual(root.find(".//{*}g[@data-id='R-1']/{*}text").text, "1")
        self.assertEqual(root.find(".//{*}g[@data-id='R-1']/{*}title").text, "R-1")

    def test_invalid_inputs_identify_the_field(self):
        for update, field in [
            ({"n": True}, ("n",)), ({"n": 0}, ("n",)), ({"n": 1.5}, ("n",)),
            ({"domain": "unknown"}, ("domain",)), ({"params": []}, ("params",)),
            ({"seed": None}, ("seed",)), ({"seed": True}, ("seed",)),
            ({"params": {"p": 1.1}}, ("params", "p")),
            ({"domain": "ws", "params": {"k": 3}}, ("params", "k")),
            ({"domain": "ws", "params": {"k": 8}}, ("params", "k")),
            ({"domain": "ws", "params": {"beta": -0.1}}, ("params", "beta")),
            ({"domain": "er", "params": {"beta": 0.5}}, ("params", "beta")),
            ({"domain": "ba", "params": {"m": 0}}, ("params", "m")),
        ]:
            with self.subTest(update=update), self.assertRaises(FigureError) as error:
                from_dict({"name": "Demo", "groups": [{"id": "A", "n": 8, **update}]})
            self.assertEqual(error.exception.path, ("groups", 0, *field))
        with self.assertRaises(FigureError) as error:
            parse("name: T\nseed: false\ngroups: [{id: A, n: 1}]")
        self.assertEqual((error.exception.path, error.exception.line), (("seed",), 2))

    def test_conflicts_leave_existing_graph_intact(self):
        graph = Topology("Demo")
        graph.add_group("A", 3, domain="mesh")
        graph.add_peer("B-2")
        for name in ("A", "B"):
            with self.assertRaises(ValueError):
                graph.add_group(name, 4)
        self.assertEqual(tuple(graph.groups), ("A",))
        self.assertEqual(set(graph.peers), {"A-1", "A-2", "A-3", "B-2"})
        self.assertEqual(len(graph.links), 3)


def coordinates(panel):
    return {peer.get("data-id"): (float(peer.find("{*}circle").get("cx")),
                                  float(peer.find("{*}circle").get("cy")))
            for peer in panel.findall("{*}g[@class='peer']")}


class GroupLayoutTests(unittest.TestCase):
    def test_sparse_spring_figure_keeps_peers_legible_on_a_compact_canvas(self):
        graph = Topology("Sparse", seed=77)
        graph.add_group("E", 100)
        svg = ET.fromstring(render_svg(graph, style=Style(group_default=GroupStyle(layout="spring"))))
        points = coordinates(svg.find("{*}g"))
        radius = float(svg.find(".//{*}circle").get("r"))
        self.assertGreater(min(math.dist(a, b) for a, b in combinations(points.values(), 2)), 2 * radius)
        self.assertLess(max(int(svg.get(axis)) for axis in ("width", "height")), 3000)

    def test_layout_changes_positions_and_preserves_links_across_views(self):
        graph = parse("name: Demo\ngroups: [{id: A, n: 9}]\nviews: [{title: First}, {title: Second}]")
        original = graph.links
        samples = []
        for method in ("circle", "grid", "spring"):
            style = Style(group_default=GroupStyle(layout=method))
            svg = render_svg(graph, style=style)
            first, second = ET.fromstring(svg).findall("{*}g[@class='panel']")
            points = coordinates(first)
            self.assertEqual(points, coordinates(second))
            self.assertEqual(len(set(points.values())), 9)
            self.assertEqual(render_svg(graph, style=style), svg)
            self.assertEqual(graph.links, original)
            samples.append(points)
        self.assertEqual(len({x for x, y in samples[1].values()}), 3)
        self.assertEqual(len({y for x, y in samples[1].values()}), 3)
        self.assertNotEqual(samples[0], samples[1])
        self.assertNotIn(samples[2], samples[:2])

    def test_arrangement_order_and_frames(self):
        graph = parse("name: Demo\ngroups: [{id: Z, n: 1}, {id: B, n: 5}, {id: A, n: 3}]")
        for arrange, expected in [("row", [(0, 0), (1, 0), (2, 0)]),
                                  ("column", [(0, 0), (0, 1), (0, 2)]),
                                  ("grid", [(0, 0), (1, 0), (0, 1)])]:
            with self.subTest(arrange=arrange):
                panel = ET.fromstring(render_svg(graph, style=Style(group_arrangement=arrange))).find("{*}g")
                frames = panel.findall("{*}g[@class='group']")
                self.assertEqual([f.get("data-group") for f in frames], ["Z", "B", "A"])
                points = coordinates(panel)
                origins = []
                for frame in frames:
                    rect = frame.find("{*}rect")
                    x, y, w, h = [float(rect.get(key)) for key in ("x", "y", "width", "height")]
                    origins.append((x, y))
                    for peer in graph.groups[frame.get("data-group")].members:
                        px, py = points[peer]
                        self.assertTrue(x < px < x + w and y < py < y + h)
                xs, ys = (sorted(set(axis)) for axis in zip(*origins))
                self.assertEqual([(xs.index(x), ys.index(y)) for x, y in origins], expected)

    def test_companion_group_rules_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "demo.yaml"
            sheet = source.with_suffix(".meta.yaml")
            source.write_text("name: Demo\ngroups: [{id: A, n: 4}, {id: B, n: 4}]")
            sheet.write_text("groups:\n  default: {layout: grid, fill: ivory}\n"
                             "  ids: {A: {layout: spring, stroke: teal}}\n  arrange: column\n")
            graph = load(source)
            self.assertEqual(graph.style.groups["A"].layout, "spring")
            self.assertEqual(graph.style.group_default.layout, "grid")
            a, b = ET.fromstring(render_svg(graph)).findall(".//{*}g[@class='group']/{*}rect")
            self.assertEqual((a.get("fill"), b.get("fill"), a.get("stroke")), ("ivory", "ivory", "teal"))
            for text, path in [
                ("  ids: {A: {layout: invalid}}", ("groups", "ids", "A", "layout")),
                ("  arrange: invalid", ("groups", "arrange")),
            ]:
                sheet.write_text("groups:\n" + text)
                with self.assertRaises(FigureError) as error:
                    load(source)
                self.assertEqual((error.exception.path, error.exception.line), (path, 2))

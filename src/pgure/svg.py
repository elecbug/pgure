"""Render a topology and its views as a standalone SVG."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .model import Topology


@dataclass(frozen=True)
class Stroke:
    color: str
    dash: str = ""


@dataclass(frozen=True)
class Style:
    """Map peer roles to fill colors and link/message classes to SVG strokes."""

    peer_fills: Mapping[str, str] = field(default_factory=dict)
    links: Mapping[str, Stroke] = field(default_factory=dict)
    messages: Mapping[str, Stroke] = field(default_factory=dict)


_LINK = Stroke("#778794")
_MESSAGE = Stroke("#145f91")
_INK = "#213547"
_Point = tuple[float, float]
# XML 1.0 permits fewer characters than a Python string.
_INVALID_XML = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def _layout(graph: Topology) -> tuple[dict[str, _Point], float, int, int]:
    # Breadth-first layers place peers with the same distance in one column.
    adjacency = {peer: set() for peer in graph.peers}
    for link in graph.links:
        adjacency[link.source].add(link.target)
        adjacency[link.target].add(link.source)
    columns: dict[int, list[str]] = defaultdict(list)
    seen = set()
    for root in sorted(adjacency):
        if root in seen:
            continue
        queue = deque([(root, 0)])
        seen.add(root)
        while queue:
            peer, level = queue.popleft()
            columns[level].append(peer)
            for neighbor in sorted(adjacency[peer] - seen):
                seen.add(neighbor)
                queue.append((neighbor, level + 1))

    radius = max(16, 5 * max(map(len, graph.peers)) + 5)
    dx, dy = 2 * radius + 70, 2 * radius + 34
    width = max(210, 2 * radius + 76 + (len(columns) - 1) * dx)
    height = 2 * radius + 90 + (max(map(len, columns.values())) - 1) * dy
    positions = {}
    for level, column in columns.items():
        x = width / 2 + (level - (len(columns) - 1) / 2) * dx
        for row, peer in enumerate(column):
            y = height / 2 + 13 + (row - (len(column) - 1) / 2) * dy
            positions[peer] = (x, y)
    return positions, radius, width, height


def _arrowhead(group: ET.Element, start: _Point, control: _Point, end: _Point,
               color: str, filled: bool) -> None:
    # Interpolating along the two control segments gives the curve's tangent.
    t = 0.53 if filled else 0.85
    x1 = (1 - t) * start[0] + t * control[0]
    y1 = (1 - t) * start[1] + t * control[1]
    x2 = (1 - t) * control[0] + t * end[0]
    y2 = (1 - t) * control[1] + t * end[1]
    x = (1 - t) * x1 + t * x2
    y = (1 - t) * y1 + t * y2
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    base_x, base_y = x - 8 * ux, y - 8 * uy
    left = f"{base_x - 4 * uy:.2f},{base_y + 4 * ux:.2f}"
    right = f"{base_x + 4 * uy:.2f},{base_y - 4 * ux:.2f}"
    path = f"M{left} L{x:.2f},{y:.2f} L{right}"
    ET.SubElement(group, "path", d=path + (" Z" if filled else ""),
                  stroke=color, fill=color if filled else "none", **{"stroke-width": "1.5"})


def _edge(group: ET.Element, start: _Point, end: _Point, radius: float, stroke: Stroke,
          *, arrow: bool, message: bool = False, bend: float = 0) -> None:
    x, y = start
    dx, dy = end[0] - x, end[1] - y
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    # Bend same-column links around the intervening peers. Different curves
    # and arrowheads keep the link direction legible under a message overlay.
    if dx == 0 and abs(dy) > 2 * radius + 35:
        bend -= math.copysign(min(length * 0.4, radius + 50), dy)
    cx, cy = x + dx / 2 + nx * bend, y + dy / 2 + ny * bend

    def boundary(point: _Point) -> _Point:
        vx, vy = cx - point[0], cy - point[1]
        scale = radius / math.hypot(vx, vy)
        return point[0] + vx * scale, point[1] + vy * scale

    ax, ay = boundary(start)
    bx, by = boundary(end)
    path = ET.SubElement(group, "path", d=f"M{ax:.2f},{ay:.2f} Q{cx:.2f},{cy:.2f} {bx:.2f},{by:.2f}",
                         fill="none", stroke=stroke.color,
                         **{"stroke-width": "2.5" if message else "1.4"})
    if stroke.dash:
        path.set("stroke-dasharray", stroke.dash)
    if arrow:
        _arrowhead(group, (ax, ay), (cx, cy), (bx, by), stroke.color, message)


def _label(parent: ET.Element, text: str, x: float, y: float, size: int) -> ET.Element:
    node = ET.SubElement(parent, "text", x=f"{x:g}", y=f"{y:g}", fill=_INK,
                         **{"text-anchor": "middle", "font-size": str(size)})
    node.text = text
    return node


def render_svg(graph: Topology, *, style: Style | None = None) -> str:
    """Return an SVG document with shared coordinates and one panel per view."""
    graph.validate()
    style = Style() if style is None else style
    positions, radius, width, height = _layout(graph)
    views = graph.views
    total_width = width * len(views)
    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width=str(total_width),
                     height=str(height), viewBox=f"0 0 {total_width} {height}",
                     **{"font-family": "DejaVu Sans, sans-serif"})
    ET.SubElement(svg, "title").text = graph.name
    ET.SubElement(svg, "rect", width="100%", height="100%", fill="white")
    for index, view in enumerate(views):
        panel = ET.SubElement(svg, "g", {"class": "panel", "transform": f"translate({index * width} 0)"})
        title = _INVALID_XML.sub("�", view.title)
        label = _label(panel, title, width / 2, 25, 16)
        if len(title) * 12 > width - 24:
            label.set("textLength", str(width - 24))
            label.set("lengthAdjust", "spacingAndGlyphs")
        for link in graph.links:
            group = ET.SubElement(panel, "g", {"class": "link", "data-source": link.source,
                                               "data-target": link.target,
                                               "data-directed": str(link.directed).lower()})
            if link.kind is not None:
                group.set("data-kind", link.kind)
            stroke = style.links.get(link.kind, _LINK) if link.kind else _LINK
            _edge(group, positions[link.source], positions[link.target], radius, stroke,
                  arrow=link.directed, bend=10 if link.directed else 0)
        # Separate messages sharing a hop so all of their styles remain visible.
        counts = Counter(hop for route in view.messages for hop in zip(route.path, route.path[1:]))
        drawn: Counter[tuple[str, str]] = Counter()
        for route in view.messages:
            group = ET.SubElement(panel, "g", {"class": "message", "data-path": " ".join(route.path)})
            if route.kind is not None:
                group.set("data-kind", route.kind)
            stroke = style.messages.get(route.kind, _MESSAGE) if route.kind else _MESSAGE
            for a, b in zip(route.path, route.path[1:]):
                bend = 30.0
                if counts[a, b] > 1:
                    bend = 20 + 30 * drawn[a, b] / (counts[a, b] - 1)
                _edge(group, positions[a], positions[b], radius, stroke,
                      arrow=True, message=True, bend=bend)
                drawn[a, b] += 1
        for peer, (x, y) in positions.items():
            role = graph.peers[peer]
            group = ET.SubElement(panel, "g", {"class": "peer", "data-id": peer})
            if role is not None:
                group.set("data-role", role)
            fill = style.peer_fills.get(role, "white") if role else "white"
            ET.SubElement(group, "circle", cx=f"{x:g}", cy=f"{y:g}", r=f"{radius:g}",
                          fill=fill, stroke=_INK, **{"stroke-width": "1.6"})
            _label(group, peer, x, y + 5, 14)
    return ET.tostring(svg, encoding="unicode")

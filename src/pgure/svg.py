"""Render a topology and its views as a standalone SVG."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict, deque
from xml.etree import ElementTree as ET

from .group_layout import layout_groups
from .model import Topology
from .style import INK, Stroke, Style


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
               color: str, filled: bool, scale: float) -> None:
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
    base_x, base_y = x - 8 * scale * ux, y - 8 * scale * uy
    left = f"{base_x - 4 * scale * uy:.2f},{base_y + 4 * scale * ux:.2f}"
    right = f"{base_x + 4 * scale * uy:.2f},{base_y - 4 * scale * ux:.2f}"
    path = f"M{left} L{x:.2f},{y:.2f} L{right}"
    ET.SubElement(group, "path", d=path + (" Z" if filled else ""),
                  stroke=color, fill=color if filled else "none", **{"stroke-width": f"{1.5 * scale:g}"})


def _link_bend(start: _Point, end: _Point, radius: float, directed: bool) -> float:
    bend = 10.0 if directed else 0.0
    dy = end[1] - start[1]
    if start[0] == end[0] and abs(dy) > 2 * radius + 35:
        # Bypass intervening peers in the same column.
        bend -= math.copysign(min(abs(dy) * 0.4, radius + 50), dy)
    return bend


def _outside_bend(start: _Point, end: _Point, center: _Point,
                  link_bend: float, distance: float) -> float:
    side = link_bend
    if not side:
        # Pick the normal pointing away from the center of the peer layout.
        dx, dy = end[0] - start[0], end[1] - start[1]
        side = dx * (start[1] - center[1]) - dy * (start[0] - center[0])
    return link_bend + math.copysign(distance, side or 1.0)


def _edge(group: ET.Element, start: _Point, end: _Point, radius: float, stroke: Stroke,
          *, bend: float, arrow: bool, message: bool = False) -> ET.Element:
    x, y = start
    dx, dy = end[0] - x, end[1] - y
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    cx, cy = x + dx / 2 + nx * bend, y + dy / 2 + ny * bend

    def boundary(point: _Point) -> _Point:
        vx, vy = cx - point[0], cy - point[1]
        scale = radius / math.hypot(vx, vy)
        return point[0] + vx * scale, point[1] + vy * scale

    ax, ay = boundary(start)
    bx, by = boundary(end)
    path = ET.SubElement(group, "path", d=f"M{ax:.2f},{ay:.2f} Q{cx:.2f},{cy:.2f} {bx:.2f},{by:.2f}",
                         fill="none")
    base_width = 2.5 if message else 1.4
    width = _apply_stroke(path, stroke, base_width)
    if arrow and width > 0:
        _arrowhead(group, (ax, ay), (cx, cy), (bx, by), stroke.color, message, width / base_width)
    return path


def _apply_stroke(node: ET.Element, stroke: Stroke, fallback_width: float) -> float:
    width = fallback_width if stroke.width is None else stroke.width
    node.set("stroke", stroke.color)
    node.set("stroke-width", f"{width:g}")
    if stroke.dash:
        node.set("stroke-dasharray", stroke.dash)
    if stroke.round_caps:
        node.set("stroke-linecap", "round")
    return width


def _label(parent: ET.Element, text: str, x: float, y: float, size: int, color: str = INK) -> ET.Element:
    node = ET.SubElement(parent, "text", x=f"{x:g}", y=f"{y:g}", fill=color,
                         **{"text-anchor": "middle", "font-size": str(size)})
    node.text = text
    return node


def render_svg(graph: Topology, *, style: Style | None = None, scale: float = 1) -> str:
    """Return a standalone SVG. Scale multiplies its output dimensions."""
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be a positive finite number")
    graph.validate()
    style = graph.style if style is None else style
    frames, labels = [], {}
    if graph.groups:
        positions, radius, width, height, frames, labels = layout_groups(graph, style)
    else:
        positions, radius, width, height = _layout(graph)
    links_by_hop = {}
    bends = {}
    for link in graph.links:
        a, b = link.source, link.target
        bend = _link_bend(positions[a], positions[b], radius, link.directed)
        links_by_hop[a, b] = link
        bends[a, b] = bend
        if not link.directed:
            links_by_hop[b, a] = link
            bends[b, a] = -bend
    # Leave room on the panel boundary for arcs around long vertical links.
    if not frames and any(abs(bend) > 10 for bend in bends.values()):
        margin = 26
        width += 2 * margin
        positions = {peer: (x + margin, y) for peer, (x, y) in positions.items()}
    xs, ys = zip(*positions.values())
    center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    centers = {}
    for frame in frames:
        local_center = (frame.x + frame.width / 2, frame.y + (frame.height + 22) / 2)
        centers.update(dict.fromkeys(frame.positions, local_center))
    views = graph.views
    total_width = width * len(views)
    output_width = max(1, round(total_width * scale))
    output_height = max(1, round(height * scale))
    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width=str(output_width),
                     height=str(output_height), viewBox=f"0 0 {total_width} {height}",
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
        for frame in frames:
            region = ET.SubElement(panel, "g", {"class": "group"})
            if frame.group:
                region.set("data-group", frame.group.id)
                region.set("data-domain", frame.group.domain)
            rect = ET.SubElement(region, "rect", x=f"{frame.x:g}", y=f"{frame.y:g}",
                                 width=str(frame.width), height=str(frame.height), rx="6", fill=frame.style.fill)
            _apply_stroke(rect, frame.style.border, 1)
            _label(region, frame.title, frame.x + frame.width / 2, frame.y + 22, 14, frame.style.label_color)
        for link in graph.links:
            group = ET.SubElement(panel, "g", {"class": "link", "data-source": link.source,
                                               "data-target": link.target,
                                               "data-directed": str(link.directed).lower()})
            if link.kind is not None:
                group.set("data-kind", link.kind)
            stroke = style.links.get(link.kind, style.link_default) if link.kind else style.link_default
            _edge(group, positions[link.source], positions[link.target], radius, stroke,
                  arrow=link.directed, bend=bends[link.source, link.target])
        uses = Counter()
        occupied = set()
        for route in view.messages:
            for hop in zip(route.path, route.path[1:]):
                link = links_by_hop[hop]
                uses[link] += 1
                if style.placement_for(route.kind, link.kind) == "overlay":
                    occupied.add(link)
        outside_count = Counter()
        for route in view.messages:
            group = ET.SubElement(panel, "g", {"class": "message", "data-path": " ".join(route.path)})
            if route.kind is not None:
                group.set("data-kind", route.kind)
            stroke = style.messages.get(route.kind, style.message_default) if route.kind else style.message_default
            for a, b in zip(route.path, route.path[1:]):
                link = links_by_hop[a, b]
                placement = style.placement_for(route.kind, link.kind)
                if placement == "auto":
                    placement = "outside" if link in occupied else "overlay"
                bend = bends[a, b]
                if placement == "outside":
                    distance = 30 + 26 * outside_count[link] / max(1, uses[link] - 1)
                    hop_center = centers.get(a, center) if centers.get(a) == centers.get(b) else center
                    bend = _outside_bend(positions[a], positions[b], hop_center, bend, distance)
                    outside_count[link] += 1
                else:
                    occupied.add(link)
                path = _edge(group, positions[a], positions[b], radius, stroke,
                             arrow=True, message=True, bend=bend)
                path.set("data-placement", placement)
        for peer, (x, y) in positions.items():
            role = graph.peers[peer]
            group = ET.SubElement(panel, "g", {"class": "peer", "data-id": peer})
            if role is not None:
                group.set("data-role", role)
            peer_style = style.peers.get(role, style.peer_default) if role else style.peer_default
            fill = style.peer_fills.get(role, peer_style.fill) if role else peer_style.fill
            circle = ET.SubElement(group, "circle", cx=f"{x:g}", cy=f"{y:g}", r=f"{radius:g}", fill=fill)
            _apply_stroke(circle, peer_style.border, 1.6)
            _label(group, labels.get(peer, peer), x, y + 5, 14, peer_style.label_color)
            if peer in labels:
                ET.SubElement(group, "title").text = peer
    return ET.tostring(svg, encoding="unicode")

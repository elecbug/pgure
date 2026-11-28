"""Position generated groups in independent, labeled regions of a figure."""

import math
from collections import defaultdict
from dataclasses import dataclass
from itertools import accumulate

import networkx as nx

from .generation import Group
from .model import Topology
from .style import GroupStyle, Style


@dataclass
class Frame:
    group: Group | None
    style: GroupStyle
    title: str
    positions: dict[str, tuple[float, float]]
    width: int
    height: int
    x: float = 0
    y: float = 0


def _space_spring(points, spacing):
    import numpy as np
    from scipy.spatial import KDTree

    coords = np.array(list(points.values()), dtype=float)
    distances, _ = KDTree(coords).query(coords, k=2)
    nearest = distances[:, 1].min()
    if nearest == 0:
        return None
    # A close pair or a distant isolate should not enlarge the entire canvas.
    extent = np.ptp(coords, axis=0).max()
    scale = 2 * math.sqrt(len(coords)) / extent
    if scale * nearest >= 1:
        return dict(zip(points, coords * (spacing / nearest)))
    coords *= scale
    # Move colliding pairs apart in units of one desired center-to-center distance.
    for _ in range(100):
        pairs = KDTree(coords).query_pairs(1, output_type="ndarray")
        if not pairs.size:
            break
        a, b = pairs.T
        delta = coords[a] - coords[b]
        lengths = np.linalg.norm(delta, axis=1)
        shortest = lengths.min()
        if shortest >= 0.99:
            break
        if shortest == 0:
            return None
        shift = delta * ((1 - lengths) / (2 * lengths))[:, None]
        moves = np.zeros_like(coords)
        np.add.at(moves, a, shift)
        np.add.at(moves, b, -shift)
        coords += moves / np.maximum(1, np.linalg.norm(moves, axis=1, keepdims=True))
    # Restore exact clearance after the finite relaxation pass.
    distances, _ = KDTree(coords).query(coords, k=2)
    nearest = distances[:, 1].min()
    if nearest == 0:
        return None
    coords *= spacing / nearest
    return dict(zip(points, coords))


def _positions(members, links, method, seed, spacing):
    n = len(members)
    if n == 1:
        return {members[0]: (0, 0)}
    if method == "circle":
        radius = spacing / (2 * math.sin(math.pi / n))
        return {peer: (radius * math.sin(2 * math.pi * i / n),
                       -radius * math.cos(2 * math.pi * i / n)) for i, peer in enumerate(members)}
    if method == "spring":
        network = nx.Graph()
        network.add_nodes_from(members)
        network.add_edges_from(links)
        points = nx.spring_layout(network, seed=seed % (2**32))
        spaced = _space_spring(points, spacing)
        if spaced is not None:
            return spaced
    columns = math.ceil(math.sqrt(n))
    return {peer: (i % columns * spacing, i // columns * spacing) for i, peer in enumerate(members)}


def layout_groups(graph: Topology, style: Style):
    owners = {peer: g.id for g in graph.groups.values() for peer in g.members}
    labels = {peer: str(i) for g in graph.groups.values() for i, peer in enumerate(g.members, 1)}
    radius = max(16, 5 * max(len(labels.get(p, p)) for p in graph.peers) + 5)
    internal_links = defaultdict(list)
    for link in graph.links:
        owner = owners.get(link.source)
        if owner == owners.get(link.target):
            internal_links[owner].append((link.source, link.target))

    sections = [(g, g.members) for g in graph.groups.values()]
    other = tuple(peer for peer in graph.peers if peer not in owners)
    if other:
        sections.append((None, other))
    frames = []
    for group, members in sections:
        key = group.id if group else None
        rule = style.groups.get(key, style.group_default)
        seed = group.seed if group else graph.seed
        points = _positions(members, internal_links[key], rule.layout, seed, 2 * radius + 22)
        xs, ys = zip(*points.values())
        left, top = min(xs), min(ys)
        span = max(xs) - left
        margin = radius + 26
        title = f"{group.id} · {group.domain.upper()}" if group else "Other peers"
        width = max(math.ceil(span) + 2 * margin, 10 * len(title) + 24)
        height = math.ceil(max(ys) - top) + 2 * margin + 22
        local = {peer: (x - left + (width - span) / 2, y - top + margin + 22)
                 for peer, (x, y) in points.items()}
        frames.append(Frame(group, rule, title, local, width, height))

    columns = {"row": len(frames), "column": 1,
               "grid": math.ceil(math.sqrt(len(frames)))}[style.group_arrangement]
    col_widths = [max(f.width for f in frames[col::columns]) for col in range(columns)]
    row_heights = [max(f.height for f in frames[i:i + columns]) for i in range(0, len(frames), columns)]
    gap = 14
    lefts = list(accumulate((w + gap for w in col_widths), initial=gap))
    tops = list(accumulate((h + gap for h in row_heights), initial=40))
    positions = {}
    for i, frame in enumerate(frames):
        row, col = divmod(i, columns)
        frame.x, frame.y = lefts[col], tops[row]
        dx = frame.x + (col_widths[col] - frame.width) / 2
        dy = frame.y + (row_heights[row] - frame.height) / 2
        positions.update({p: (x + dx, y + dy) for p, (x, y) in frame.positions.items()})
        frame.width, frame.height = col_widths[col], row_heights[row]
    return positions, radius, lefts[-1], tops[-1], frames, labels

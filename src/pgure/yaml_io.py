"""Load a figure from YAML or an equivalent Python mapping."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import replace
from functools import partial
from pathlib import Path
from sys import float_info

from ruamel.yaml import YAML, YAMLError
from ruamel.yaml.nodes import MappingNode, SequenceNode

from .generation import _GroupError
from .model import Message, Topology, _RouteError, _identifier
from .style import ARRANGEMENTS, LAYOUTS, PLACEMENTS, Stroke, Style


_Path = tuple[str | int, ...]


class FigureError(ValueError):
    """Invalid figure data, with a field path and source coordinates when available."""

    def __init__(self, detail: str, path: _Path = (), *, source: str | None = None,
                 line: int | None = None, column: int | None = None):
        self.detail, self.path, self.source = detail, path, source
        self.line, self.column = line, column
        location = "".join(f"[{key}]" if isinstance(key, int) else f".{key}" for key in path)
        where = source or ""
        if line is not None:
            where += f":{line}:{column}"
        if location:
            where = f"{where} {location.lstrip('.')}".strip()
        super().__init__(f"{where}: {detail}" if where else detail)


@contextmanager
def _at(path: _Path):
    """Attach a data path to validation errors raised by the shared model."""
    try:
        yield
    except ValueError as error:
        raise FigureError(str(error), path) from error


def _record(value, path, required, optional):
    if not isinstance(value, Mapping):
        raise FigureError("expected a mapping", path)
    for field in required:
        if field not in value:
            raise FigureError(f"missing required field {field!r}", (*path, field))
    for field in value:
        if field not in required and field not in optional:
            raise FigureError(f"unknown field {field!r}", (*path, str(field)))
    return value


def _sequence(value, path):
    if not isinstance(value, (list, tuple)):
        raise FigureError("expected a sequence", path)
    return value


def _records(parent, field, parent_path, required, optional):
    path = (*parent_path, field)
    for i, entry in enumerate(_sequence(parent.get(field, []), path)):
        at = (*path, i)
        yield _record(entry, at, required, optional), at


def from_dict(data: Mapping) -> Topology:
    """Construct and validate a topology from a figure mapping."""
    _record(data, (), ("name",), ("seed", "groups", "peers", "links", "views"))
    try:
        graph = Topology(data["name"], seed=data.get("seed", 0))
    except _GroupError as error:
        raise FigureError(str(error), error.field) from error
    except ValueError as error:
        raise FigureError(str(error), ("name",)) from error

    for group, at in _records(data, "groups", (), ("id", "n"), ("domain", "params", "seed")):
        if "params" in group and not isinstance(group["params"], Mapping):
            raise FigureError("expected a mapping", (*at, "params"))
        if "seed" in group and group["seed"] is None:
            raise FigureError("seed must be an integer", (*at, "seed"))
        try:
            graph.add_group(group["id"], group["n"], domain=group.get("domain", "er"),
                            params=group.get("params"), seed=group.get("seed"))
        except _GroupError as error:
            raise FigureError(str(error), (*at, *error.field)) from error
        except ValueError as error:
            raise FigureError(str(error), (*at, "id")) from error

    for peer, at in _records(data, "peers", (), ("id",), ("role",)):
        with _at((*at, "id")):
            graph.add_peer(peer["id"])
        if peer.get("role") is not None:
            with _at((*at, "role")):
                graph.set_role(peer["id"], peer["role"])

    for link, at in _records(data, "links", (), ("source", "target"), ("directed", "kind")):
        directed = link.get("directed", False)
        if not isinstance(directed, bool):
            raise FigureError("expected a boolean", (*at, "directed"))
        with _at(at):
            graph.add_link(link["source"], link["target"], directed=directed, kind=link.get("kind"))

    for view, at in _records(data, "views", (), ("title",), ("messages",)):
        title = view["title"]
        if not isinstance(title, str):
            raise FigureError("expected a string", (*at, "title"))
        messages = []
        for entry, message_at in _records(view, "messages", at, ("path",), ("kind", "placement")):
            if "placement" in entry:
                raise FigureError("move placement to the companion .meta.yaml under messages or links",
                                  (*message_at, "placement"))
            path = _sequence(entry["path"], (*message_at, "path"))
            with _at(message_at):
                messages.append(Message(tuple(path), entry.get("kind")))
        try:
            graph.add_view(title, messages)
        except _RouteError as error:
            field = (*at, "messages", error.message_index, "path", error.peer_index)
            raise FigureError(f"in view {title!r}: {error}", field) from error

    with _at(()):
        graph.validate()
    return graph


_LINES = {
    "solid": ("", False), "dashed": ("6 3", False),
    "dotted": ("0 3", True), "dash-dot": ("6 3 1 3", False),
}
_LINE_ALIASES = {"-": "solid", "--": "dashed", ":": "dotted", "-.": "dash-dot"}


def _number(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= float_info.max:
        raise FigureError("expected a finite nonnegative number", path)
    return value


def _line(value, path):
    if isinstance(value, str):
        name = _LINE_ALIASES.get(value, value)
        if name in _LINES:
            return _LINES[name]
    elif isinstance(value, list):
        parts = [_number(n, (*path, i)) for i, n in enumerate(value)]
        if any(parts):
            return " ".join(f"{n:g}" for n in parts), False
    raise FigureError("expected solid, dashed, dotted, dash-dot, or a nonzero dash sequence", path)


def _color(data, field, default, path):
    color = data.get(field, default)
    if not isinstance(color, str) or not color.strip() or not color.isprintable():
        raise FigureError("expected a color string, e.g. \"#145f91\"", (*path, field))
    return color


def _stroke(data, base, path, color_field, *, placement=None):
    color = _color(data, color_field, base.color, path)
    width = _number(data["width"], (*path, "width")) if "width" in data else base.width
    dash, round_caps = _line(data["line"], (*path, "line")) if "line" in data else (base.dash, base.round_caps)
    return Stroke(color, dash, width, round_caps, placement=placement)


def _edge_rule(data, base, path):
    _record(data, path, (), ("color", "width", "line", "placement"))
    placement = data.get("placement")
    if "placement" in data and placement not in PLACEMENTS:
        raise FigureError("expected auto, overlay, or outside", (*path, "placement"))
    # Placement depends on both the message and its current link, so resolve it per hop.
    return _stroke(data, base, path, "color", placement=placement)


def _shape_rule(data, base, path, *, group=False):
    properties = ("fill", "stroke", "width", "line", "label_color")
    _record(data, path, (), (*properties, "layout") if group else properties)
    if group:
        layout = data.get("layout", base.layout)
        if layout not in LAYOUTS:
            raise FigureError("expected circle, grid, or spring", (*path, "layout"))
        base = replace(base, layout=layout)
    return replace(base, fill=_color(data, "fill", base.fill, path),
                   border=_stroke(data, base.border, path, "stroke"),
                   label_color=_color(data, "label_color", base.label_color, path))


def _rules(sheet, category, selector, base, compile_rule, *, extra_fields=()):
    group = _record(sheet.get(category, {}), (category,), (), ("default", selector, *extra_fields))
    default = compile_rule(group.get("default", {}), base, (category, "default"))
    rules = group.get(selector, {})
    if not isinstance(rules, Mapping):
        raise FigureError("expected a mapping", (category, selector))
    resolved = {}
    for name, props in rules.items():
        path = (category, selector, str(name))
        with _at(path):
            _identifier(name)
        resolved[name] = compile_rule(props, default, path)
    return default, resolved


def _style_from_dict(data):
    _record(data, (), (), ("peers", "links", "messages", "groups"))
    base = Style()
    peer, peers = _rules(data, "peers", "roles", base.peer_default, _shape_rule)
    link, links = _rules(data, "links", "kinds", base.link_default, _edge_rule)
    message, messages = _rules(data, "messages", "kinds", base.message_default, _edge_rule)
    group, groups = _rules(data, "groups", "ids", base.group_default,
                           partial(_shape_rule, group=True),
                           extra_fields=("arrange",))
    arrange = data.get("groups", {}).get("arrange", base.group_arrangement)
    if arrange not in ARRANGEMENTS:
        raise FigureError("expected grid, row, or column", ("groups", "arrange"))
    return Style(peers=peers, links=links, messages=messages, groups=groups,
                 group_default=group, group_arrangement=arrange,
                 peer_default=peer, link_default=link, message_default=message)


def _field_mark(text: str, path: _Path):
    # Consult the YAML node marks only when reporting a semantic error.
    node = YAML(typ="safe", pure=True).compose(text)
    for key in path:
        if isinstance(node, MappingNode):
            child = next((value for field, value in node.value if field.value == key), None)
        elif isinstance(node, SequenceNode) and isinstance(key, int):
            child = node.value[key]
        else:
            break
        if child is None:
            break
        node = child
    return node.start_mark if node is not None else None


def _parse_document(text, source, construct):
    try:
        data = YAML(typ="safe", pure=True).load(text)
    except YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        raise FigureError(getattr(error, "problem", None) or str(error), source=source,
                          line=mark.line + 1 if mark else None,
                          column=mark.column + 1 if mark else None) from error
    try:
        return construct(data)
    except FigureError as error:
        mark = _field_mark(text, error.path)
        raise FigureError(error.detail, error.path, source=source,
                          line=mark.line + 1 if mark else None,
                          column=mark.column + 1 if mark else None) from error


def parse(text: str, *, source: str = "<string>") -> Topology:
    """Read one YAML figure from a string."""
    return _parse_document(text, source, from_dict)


def load_style(path: str | Path) -> Style:
    """Load a YAML stylesheet for use with any topology."""
    path = Path(path)
    return _parse_document(path.read_text(encoding="utf-8"), str(path), _style_from_dict)


def load(path: str | Path, *, meta: str | Path | None = None) -> Topology:
    """Load a figure and its sibling <stem>.meta.yaml, or a specified stylesheet."""
    path = Path(path)
    graph = parse(path.read_text(encoding="utf-8"), source=str(path))
    if meta is not None:
        graph.style = load_style(meta)
    else:
        companion = path.with_suffix(".meta.yaml")
        if companion.is_file():
            graph.style = load_style(companion)
    return graph

"""Load a figure from YAML or an equivalent Python mapping."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

from ruamel.yaml import YAML, YAMLError
from ruamel.yaml.nodes import MappingNode, SequenceNode

from .model import Message, Topology, _RouteError


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
    _record(data, (), ("name",), ("peers", "links", "views"))
    with _at(("name",)):
        graph = Topology(data["name"])

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
            path = _sequence(entry["path"], (*message_at, "path"))
            with _at(message_at):
                messages.append(Message(tuple(path), entry.get("kind"), entry.get("placement")))
        try:
            graph.add_view(title, messages)
        except _RouteError as error:
            field = (*at, "messages", error.message_index, "path", error.peer_index)
            raise FigureError(f"in view {title!r}: {error}", field) from error

    with _at(()):
        graph.validate()
    return graph


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


def parse(text: str, *, source: str = "<string>") -> Topology:
    """Read one YAML figure from a string."""
    try:
        data = YAML(typ="safe", pure=True).load(text)
    except YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        raise FigureError(getattr(error, "problem", None) or str(error), source=source,
                          line=mark.line + 1 if mark else None,
                          column=mark.column + 1 if mark else None) from error
    try:
        return from_dict(data)
    except FigureError as error:
        mark = _field_mark(text, error.path)
        raise FigureError(error.detail, error.path, source=source,
                          line=mark.line + 1 if mark else None,
                          column=mark.column + 1 if mark else None) from error


def load(path: str | Path) -> Topology:
    """Read one UTF-8 YAML figure from a file."""
    path = Path(path)
    return parse(path.read_text(encoding="utf-8"), source=str(path))

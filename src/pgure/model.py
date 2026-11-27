"""Shared topology and message model for Python and YAML figures."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType


PLACEMENTS = ("overlay", "outside")


def _identifier(value: str) -> str:
    if (not isinstance(value, str) or not value or not value.isprintable()
            or any(char.isspace() for char in value)):
        raise ValueError(f"invalid identifier {value!r}")
    return value


@dataclass(frozen=True)
class Message:
    """One path, with an optional message class and placement relative to its links."""

    path: tuple[str, ...]
    kind: str | None = None
    placement: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.path, str):
            raise TypeError("a message path requires a sequence of peer IDs")
        path = tuple(_identifier(peer) for peer in self.path)
        if len(path) < 2:
            raise ValueError("a message needs at least two peers")
        object.__setattr__(self, "path", path)
        if self.kind is not None:
            _identifier(self.kind)
        if self.placement is not None and self.placement not in PLACEMENTS:
            raise ValueError(f"unknown message placement {self.placement!r}; expected overlay or outside")


@dataclass(frozen=True)
class Link:
    source: str
    target: str
    directed: bool
    kind: str | None


@dataclass(frozen=True)
class View:
    title: str
    messages: tuple[Message, ...] = ()


class _RouteError(ValueError):
    """Indexes identify the offending message and peer within its view."""

    def __init__(self, detail: str, message_index: int, peer_index: int):
        super().__init__(detail)
        self.message_index = message_index
        self.peer_index = peer_index


class Topology:
    """Build a figure by declaring peers and links, then adding message views."""

    def __init__(self, name: str):
        self.name = _identifier(name)
        self._peers: dict[str, str | None] = {}
        self._links: dict[tuple[str, str, bool], Link] = {}
        self._views: list[View] = []

    @property
    def peers(self) -> Mapping[str, str | None]:
        """Peer IDs mapped to their optional roles."""
        return MappingProxyType(self._peers)

    @property
    def links(self) -> tuple[Link, ...]:
        return tuple(self._links.values())

    @property
    def views(self) -> tuple[View, ...]:
        return tuple(self._views) or (View(self.name),)

    def add_peer(self, peer: str) -> None:
        self._peers.setdefault(_identifier(peer), None)

    def set_role(self, peer: str, role: str) -> None:
        _identifier(role)
        if peer not in self._peers:
            raise ValueError(f"unknown peer {peer!r}")
        if self._peers[peer] not in (None, role):
            raise ValueError(f"conflicting roles for peer {peer!r}")
        self._peers[peer] = role

    def add_link(self, source: str, target: str, *, directed: bool = False,
                 kind: str | None = None) -> None:
        _identifier(source)
        _identifier(target)
        if kind is not None:
            _identifier(kind)
        if source == target:
            raise ValueError(f"self-link at {source!r}")
        low, high = sorted((source, target))
        if directed:
            conflict = (low, high, False) in self._links
        else:
            conflict = any(key in self._links for key in
                           ((source, target, True), (target, source, True)))
            source, target = low, high
        if conflict:
            raise ValueError(f"overlapping directed and undirected links: {source}, {target}")
        key = (source, target, directed)
        existing = self._links.get(key)
        if existing and existing.kind is not None:
            if kind is not None and existing.kind != kind:
                raise ValueError(f"conflicting link classes for {source}, {target}")
            return
        self._peers.setdefault(source, None)
        self._peers.setdefault(target, None)
        self._links[key] = Link(source, target, directed, kind)

    def add_view(self, title: str, messages: Iterable[Message] = ()) -> None:
        """Append a panel after validating every hop against the declared links."""
        view = View(title, tuple(messages))
        for index, message in enumerate(view.messages):
            for i, peer in enumerate(message.path):
                if peer not in self._peers:
                    raise _RouteError(f"unknown peer {peer!r}", index, i)
                if i:
                    previous = message.path[i - 1]
                    low, high = sorted((previous, peer))
                    if ((previous, peer, True) not in self._links
                            and (low, high, False) not in self._links):
                        raise _RouteError(f"no link for hop {previous} -> {peer}", index, i - 1)
        self._views.append(view)

    def validate(self) -> None:
        if not self._peers:
            raise ValueError(f"topology {self.name!r} needs at least one peer")

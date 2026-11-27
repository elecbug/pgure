"""Read a figure description with source locations for syntax and model errors."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

from .model import IDENTIFIER, KEYWORDS, Message, Topology, _RouteError


class DSLError(ValueError):
    """A diagnostic with a source name, one-based line and column, and optional view."""

    def __init__(self, detail: str, source: str, line: int, column: int, view: str | None):
        self.source, self.line, self.column, self.view = source, line, column, view
        context = f" in view {view!r}" if view is not None else ""
        super().__init__(f"{source}:{line}:{column}{context}: {detail}")


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    line: int
    column: int


_LEXEME = re.compile(
    r'(?P<skip>[ \t]+|\#[^\r\n]*)|(?P<newline>\r?\n)|'
    r'(?P<string>"(?:[^"\\\r\n]|\\["\\])*")|'
    rf'(?P<id>{IDENTIFIER.pattern})|(?P<symbol>--|->|[{{}}:,])|(?P<invalid>.)'
)


def _tokens(text: str) -> Iterator[_Token]:
    line = 1
    line_start = 0
    for match in _LEXEME.finditer(text):
        kind, value = match.lastgroup, match.group()
        if kind == "skip":
            continue
        if kind == "symbol" or (kind == "id" and value in KEYWORDS):
            kind = value
        elif kind == "string":
            value = re.sub(r'\\(["\\])', r'\1', value[1:-1])
        yield _Token(kind, value, line, match.start() - line_start + 1)
        if kind == "newline":
            line += 1
            line_start = match.end()
    yield _Token("EOF", "", line, len(text) - line_start + 1)


@dataclass
class _PendingView:
    title: str
    paths: list[tuple[list[_Token], str | None]] = field(default_factory=list)


class _Parser:
    def __init__(self, text: str, source: str):
        self.source = source
        self.tokens = _tokens(text)
        self.token = next(self.tokens)
        self.view: str | None = None
        self.roles: list[tuple[_Token, str]] = []
        self.views: list[_PendingView] = []

    def fail(self, detail: str, token: _Token) -> NoReturn:
        raise DSLError(detail, self.source, token.line, token.column, self.view)

    def take(self, kind: str) -> _Token:
        token = self.token
        if token.kind != kind:
            if token.kind == "invalid" and token.value == '"':
                self.fail("invalid string escape or missing closing quote", token)
            self.fail(f"expected {kind!r}, found {token.value or token.kind!r}", token)
        if kind != "EOF":
            self.token = next(self.tokens)
        return token

    def names(self, separator: str = ",") -> list[_Token]:
        names = [self.take("id")]
        while self.token.kind == separator:
            self.take(separator)
            names.append(self.take("id"))
        return names

    def tag(self) -> str | None:
        if self.token.kind == ":":
            self.take(":")
            return self.take("id").value
        return None

    def newlines(self) -> None:
        while self.token.kind == "newline":
            self.take("newline")

    def end_statement(self) -> None:
        if self.token.kind != "}":
            self.take("newline")
            self.newlines()

    def read(self) -> Topology:
        self.newlines()
        self.take("topology")
        name = self.take("id")
        graph = Topology(name.value)
        self.take("{")
        self.newlines()
        while self.token.kind not in ("}", "EOF"):
            self.item(graph)
            self.end_statement()
        self.take("}")
        self.newlines()
        self.take("EOF")

        for peer, role in self.roles:
            try:
                graph.set_role(peer.value, role)
            except ValueError as error:
                self.fail(str(error), peer)
        for panel in self.views:
            self.view = panel.title
            messages = (Message(tuple(t.value for t in path), kind) for path, kind in panel.paths)
            try:
                graph.add_view(panel.title, messages)
            except _RouteError as error:
                path, _ = panel.paths[error.message_index]
                self.fail(str(error), path[error.peer_index])
        self.view = None
        try:
            graph.validate()
        except ValueError as error:
            self.fail(str(error), name)
        return graph

    def item(self, graph: Topology) -> None:
        if self.token.kind == "view":
            self.read_view()
            return
        if self.token.kind == "node":
            self.take("node")
            for token in self.names():
                graph.add_peer(token.value)
            return
        peers = self.names()
        if len(peers) > 1 or self.token.kind == ":":
            self.take(":")
            role = self.take("id").value
            self.roles.extend((token, role) for token in peers)
            return
        op = self.token.kind
        if op not in ("--", "->"):
            self.fail("expected a link operator or a peer role", self.token)
        self.take(op)
        targets = self.names()
        kind = self.tag()
        for target in targets:
            try:
                graph.add_link(peers[0].value, target.value, directed=(op == "->"), kind=kind)
            except ValueError as error:
                self.fail(str(error), target)

    def read_view(self) -> None:
        self.take("view")
        self.view = self.take("string").value
        panel = _PendingView(self.view)
        self.take("{")
        self.newlines()
        while self.token.kind not in ("}", "EOF"):
            self.take("send")
            source = self.take("id")
            self.take("->")
            targets = self.names("->")
            if self.token.kind == ",":
                if len(targets) > 1:
                    self.fail("use separate sends for a chain and a fan-out", self.token)
                self.take(",")
                targets.extend(self.names())
                paths = [[source, target] for target in targets]
            else:
                paths = [[source, *targets]]
            if self.token.kind == "->":
                self.fail("use separate sends for a fan-out and a chain", self.token)
            kind = self.tag()
            panel.paths.extend((path, kind) for path in paths)
            self.end_statement()
        self.take("}")
        self.views.append(panel)
        self.view = None


def parse(text: str, *, source: str = "<string>") -> Topology:
    """Parse and validate a DSL document."""
    return _Parser(text, source).read()


def load(path: str | Path) -> Topology:
    """Read a UTF-8 DSL file. Diagnostics include its path."""
    file = Path(path)
    return parse(file.read_bytes().decode("utf-8"), source=str(file))

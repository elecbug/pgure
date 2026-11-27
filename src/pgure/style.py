"""Drawing styles shared by the YAML loader and the renderer."""

from collections.abc import Mapping
from dataclasses import dataclass, field


INK = "#213547"


@dataclass(frozen=True)
class Stroke:
    color: str
    dash: str = ""
    width: float | None = None
    round_caps: bool = False


@dataclass(frozen=True)
class PeerStyle:
    fill: str = "white"
    border: Stroke = Stroke(INK, width=1.6)
    label_color: str = INK


@dataclass(frozen=True)
class Style:
    """Category defaults and resolved rules for peer roles and message/link kinds."""

    peer_fills: Mapping[str, str] = field(default_factory=dict)
    links: Mapping[str, Stroke] = field(default_factory=dict)
    messages: Mapping[str, Stroke] = field(default_factory=dict)
    peers: Mapping[str, PeerStyle] = field(default_factory=dict)
    peer_default: PeerStyle = PeerStyle()
    link_default: Stroke = Stroke("#778794", width=1.4)
    message_default: Stroke = Stroke("#145f91", width=2.5)

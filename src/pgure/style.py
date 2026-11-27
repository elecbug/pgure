"""Drawing styles shared by the YAML loader and the renderer."""

from collections.abc import Mapping
from dataclasses import dataclass, field


INK = "#213547"
PLACEMENTS = ("auto", "overlay", "outside")


@dataclass(frozen=True)
class Stroke:
    color: str
    dash: str = ""
    width: float | None = None
    round_caps: bool = False
    placement: str | None = None

    def __post_init__(self) -> None:
        if self.placement is not None and self.placement not in PLACEMENTS:
            raise ValueError("placement must be auto, overlay, or outside")


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

    def placement_for(self, message_kind: str | None, link_kind: str | None) -> str:
        """Resolve one hop, checking kind rules before category defaults."""
        message = self.messages.get(message_kind) if message_kind is not None else None
        link = self.links.get(link_kind) if link_kind is not None else None
        for rule in (message, link, self.message_default, self.link_default):
            if rule is not None and rule.placement is not None:
                return rule.placement
        return "auto"

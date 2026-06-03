"""TerminalStyle — user-customizable color and font settings for the terminal."""
from __future__ import annotations
from dataclasses import dataclass, field


# Theme defaults — used when the user has not overridden a particular color.
_DEFAULTS: dict[str, dict[str, str]] = {
    "light": {
        "rx_color":              "#116329",   # green text (COL_DATA RX rows)
        "tx_color":              "#0969da",   # blue text  (COL_DATA TX rows)
        "rx_badge_color":        "#1f883d",   # solid badge background RX
        "tx_badge_color":        "#0969da",   # solid badge background TX
        "bg_color":              "#ffffff",
        "alt_bg_color":          "#f6f8fa",
        "trigger_highlight_color": "#f9e2af",
    },
    "dark": {
        "rx_color":              "#3fb950",
        "tx_color":              "#388bfd",
        "rx_badge_color":        "#238636",
        "tx_badge_color":        "#1f6feb",
        "bg_color":              "#1e1e2e",
        "alt_bg_color":          "#181825",
        "trigger_highlight_color": "#f9e2af",
    },
}


def theme_defaults(is_dark: bool) -> dict[str, str]:
    return dict(_DEFAULTS["dark" if is_dark else "light"])


@dataclass
class TerminalStyle:
    """Resolved terminal appearance — colors and font.

    Empty string for any color means "use theme default".  Call
    :func:`resolve` to get a fully-filled copy with theme defaults applied.
    """

    rx_color:               str = ""   # COL_DATA text for RX rows
    tx_color:               str = ""   # COL_DATA text for TX rows
    bg_color:               str = ""   # table background
    trigger_highlight_color: str = ""  # soft-bg accent base
    font_size:              int = 10
    font_family:            str = "Cascadia Code"
    # "wall" | "delta" | "elapsed" | "none"
    timestamp_format:       str = "wall"
    show_ctrl_chars:        bool = False   # legacy: render 0x0D as <CR> etc.
    # ASCII column rendering — overrides show_ctrl_chars when set.
    #   "multiline" — render \r and \n as real line breaks (Docklight style)
    #   "ctrl"      — render 0x00–0x1F / 0x7F as <CR>, <LF>, <NUL>, etc.
    #   "escape"    — legacy: render as literal \r \n \xNN
    ascii_render:           str = "multiline"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "rx_color":               self.rx_color,
            "tx_color":               self.tx_color,
            "bg_color":               self.bg_color,
            "trigger_highlight_color": self.trigger_highlight_color,
            "font_size":              self.font_size,
            "font_family":            self.font_family,
            "timestamp_format":       self.timestamp_format,
            "show_ctrl_chars":        self.show_ctrl_chars,
            "ascii_render":           self.ascii_render,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TerminalStyle":
        # Back-compat: if legacy show_ctrl_chars=True is the only thing set,
        # promote it to ascii_render="ctrl".
        ascii_render = d.get("ascii_render")
        if ascii_render is None:
            ascii_render = "ctrl" if d.get("show_ctrl_chars") else "multiline"
        return cls(
            rx_color=               d.get("rx_color", ""),
            tx_color=               d.get("tx_color", ""),
            bg_color=               d.get("bg_color", ""),
            trigger_highlight_color= d.get("trigger_highlight_color", ""),
            font_size=              int(d.get("font_size", 10)),
            font_family=            d.get("font_family", "Cascadia Code"),
            timestamp_format=       d.get("timestamp_format", "wall"),
            show_ctrl_chars=        bool(d.get("show_ctrl_chars", False)),
            ascii_render=           str(ascii_render),
        )

    # ------------------------------------------------------------------
    # Theme merge
    # ------------------------------------------------------------------

    def resolve(self, is_dark: bool) -> "TerminalStyle":
        """Return a copy with every empty color replaced by its theme default."""
        defaults = theme_defaults(is_dark)
        return TerminalStyle(
            rx_color=               self.rx_color or defaults["rx_color"],
            tx_color=               self.tx_color or defaults["tx_color"],
            bg_color=               self.bg_color or defaults["bg_color"],
            trigger_highlight_color= self.trigger_highlight_color
                                     or defaults["trigger_highlight_color"],
            font_size=        self.font_size,
            font_family=      self.font_family,
            timestamp_format= self.timestamp_format,
            show_ctrl_chars=  self.show_ctrl_chars,
            ascii_render=     self.ascii_render,
        )

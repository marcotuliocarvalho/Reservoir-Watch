"""Color tokens and the Plotly base layout for light and dark mode.

The categorical colors follow a fixed, CVD-validated order. Each region or
subsystem keeps its slot, so a filter never repaints the remaining series.
Status colors are reserved for criticality and always ship with a label.
"""

TOKENS = {
    "light": {
        "surface": "#ffffff",
        "text_primary": "#0b0b0b",
        "text_secondary": "#52514e",
        "text_muted": "#8a8984",
        "grid": "#ecebe7",
        "axis": "#c9c8c2",
        "hover_bg": "#ffffff",
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"],
    },
    "dark": {
        "surface": "#1a1a19",
        "text_primary": "#f0efec",
        "text_secondary": "#c3c2b7",
        "text_muted": "#8f8e86",
        "grid": "#2c2c2a",
        "axis": "#4a4a46",
        "hover_bg": "#262624",
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"],
    },
}

FONT_FAMILY = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"


def tokens(theme: str | None) -> dict:
    return TOKENS["dark" if theme == "dark" else "light"]


STATUS_COLORS = {
    "Crítico": "#d03b3b",
    "Alerta": "#ec835a",
    "Atenção": "#fab219",
    "Normal": "#0ca30c",
    "Sem classificação": "#9a9992",
}

STATUS_ICONS = {
    "Crítico": "▼",
    "Alerta": "◆",
    "Atenção": "↘",
    "Normal": "●",
    "Sem classificação": "○",
}


def group_color(area: str, theme: str | None, order: list[str]) -> str:
    series = tokens(theme)["series"]
    index = order.index(area) if area in order else len(series) - 1
    return series[index % len(series)]


def base_layout(theme: str | None, **overrides) -> dict:
    """Recessive axes and grid, transparent background, unified hover."""
    t = tokens(theme)
    axis = {
        "showgrid": False,
        "zeroline": False,
        "showline": True,
        "linecolor": t["axis"],
        "ticks": "",
        "tickfont": {"color": t["text_secondary"], "size": 12},
        "title": {"font": {"color": t["text_secondary"], "size": 12}},
    }
    layout = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": FONT_FAMILY, "color": t["text_primary"], "size": 13},
        "margin": {"l": 8, "r": 8, "t": 8, "b": 8},
        "xaxis": dict(axis),
        "yaxis": {**axis, "showline": False, "showgrid": True, "gridcolor": t["grid"]},
        "hoverlabel": {
            "bgcolor": t["hover_bg"],
            "bordercolor": t["axis"],
            "font": {"family": FONT_FAMILY, "color": t["text_primary"], "size": 13},
        },
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"color": t["text_secondary"], "size": 12},
            "bgcolor": "rgba(0,0,0,0)",
        },
        "separators": ",.",
        "autosize": True,
    }
    layout.update(overrides)
    return layout

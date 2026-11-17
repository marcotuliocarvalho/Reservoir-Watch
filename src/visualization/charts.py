"""Plotly figure builders. Every builder takes prepared frames and the theme."""

import math

import plotly.graph_objects as go
import polars as pl

from . import geo
from .data import FLOW_COLUMNS, GROUPS, METRICS, STATUS_ORDER
from .theme import STATUS_COLORS, base_layout, group_color, tokens

# Diverging ramp (red <-> blue, gray midpoint at 50%): low volume reads warm.
DIVERGING = {
    "light": ["#b8302f", "#e34948", "#f0a3a2", "#f0efec", "#9ec5f4", "#3987e5", "#184f95"],
    "dark": ["#e66767", "#c23b3b", "#7a3434", "#383835", "#1c5cab", "#3987e5", "#86b6ef"],
}

GRAPH_CONFIG = {"displayModeBar": False, "responsive": True}
MAP_CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": True, "doubleClick": "reset"}


def _number(value: float | None, decimals: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def _rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def empty_figure(theme: str | None, message: str = "Sem dados para os filtros atuais") -> go.Figure:
    t = tokens(theme)
    fig = go.Figure()
    fig.update_layout(
        **base_layout(theme),
        annotations=[{
            "text": message, "showarrow": False, "xref": "paper", "yref": "paper",
            "x": 0.5, "y": 0.5, "font": {"color": t["text_muted"], "size": 14},
        }],
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# ---------- Map ----------
def brazil_map(
    summary: pl.DataFrame,
    points: pl.DataFrame,
    group: str,
    color_mode: str,
    selected: list[str] | None,
    show_points: bool,
    metric: str,
    theme: str | None,
) -> go.Figure:
    """States painted by area (region or subsystem) plus reservoir markers.

    ``color_mode`` "area": one categorical color per area.
    ``color_mode`` "valor": diverging ramp on the mean current value.
    Selecting areas zooms the map to them.
    """
    t = tokens(theme)
    order = GROUPS[group]["order"]
    label = GROUPS[group]["label"]
    values = {row["grupo"]: row for row in summary.iter_rows(named=True)}
    selected = [s for s in (selected or []) if s in order]
    geojson = geo.states_geojson()
    meta = METRICS[metric]
    fig = go.Figure()

    def hover_rows(codes):
        rows = []
        for code in codes:
            row = values.get(geo.area_of(code, group))
            rows.append([
                geo.STATES[code][0],
                geo.area_of(code, group),
                f"{_number(row['valor'])}%" if row else "sem dados",
                row["reservatorios"] if row else 0,
                (row["criticos"] + row["alertas"]) if row else 0,
            ])
        return rows

    hover = (
        "<b>%{customdata[1]}</b> · %{customdata[0]}<br>"
        f"{meta['short']} médio: %{{customdata[2]}}<br>"
        "Reservatórios: %{customdata[3]} · em alerta: %{customdata[4]}"
        "<extra>" + label + "</extra>"
    )

    if color_mode == "valor":
        codes = list(geo.STATES)
        z = [(values.get(geo.area_of(c, group)) or {}).get("valor") for c in codes]
        ramp = DIVERGING["dark" if theme == "dark" else "light"]
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.codarea", locations=codes,
            z=[v if v is not None else 50 for v in z], zmin=0, zmax=100,
            colorscale=[[i / (len(ramp) - 1), c] for i, c in enumerate(ramp)],
            marker={
                "line": {"color": t["surface"], "width": 1},
                "opacity": [1.0 if not selected or geo.area_of(c, group) in selected else 0.35 for c in codes],
            },
            customdata=hover_rows(codes), hovertemplate=hover, showlegend=False,
            colorbar={
                "orientation": "h", "thickness": 8, "len": 0.45, "x": 0.5, "y": 0.02,
                "xanchor": "center", "yanchor": "bottom", "outlinewidth": 0, "ticksuffix": "%",
                "tickvals": [0, 25, 50, 75, 100], "tickfont": {"color": t["text_secondary"], "size": 11},
            },
        ))
    else:
        for area in order:
            codes = geo.states_in([area], group)
            color = group_color(area, theme, order)
            active = not selected or area in selected
            fig.add_trace(go.Choropleth(
                geojson=geojson, featureidkey="properties.codarea", locations=codes,
                z=[1] * len(codes), colorscale=[[0, color], [1, color]], showscale=False,
                marker={
                    "line": {"color": t["surface"], "width": 1.2},
                    # Lighter fills when markers are on, so status colors stay readable.
                    "opacity": (0.42 if show_points else 0.85) if active else 0.12,
                },
                customdata=hover_rows(codes), hovertemplate=hover, name=area, showlegend=False,
            ))

    if show_points and not points.is_empty():
        located = points.drop_nulls(["lat", "lon"])
        for status in STATUS_ORDER:
            part = located.filter(pl.col("status") == status)
            if part.is_empty():
                continue
            capacity = part["capacidade_hm3"].fill_null(0).to_list()
            fig.add_trace(go.Scattergeo(
                lat=part["lat"], lon=part["lon"], mode="markers", name=status,
                marker={
                    "size": [7 + min(14, math.sqrt(c) / 6) for c in capacity],
                    "color": STATUS_COLORS[status],
                    "line": {"color": t["surface"], "width": 1.5},
                    "opacity": 0.95,
                },
                customdata=[
                    [r["id_reservatorio"], r["reservatorio"], r["uf"] or "–", f"{_number(r['volume_atual'])}%"]
                    for r in part.iter_rows(named=True)
                ],
                hovertemplate=(
                    "<b>%{customdata[1]}</b> · %{customdata[2]}<br>"
                    "Volume útil: %{customdata[3]}<br>" + status + "<extra>Reservatório</extra>"
                ),
            ))

    bounds = geo.bounds_of(selected, group) if selected else None
    geo_style = {"projection_type": "mercator", "visible": False, "bgcolor": "rgba(0,0,0,0)"}
    if bounds:
        fig.update_geos(fitbounds=False, lonaxis_range=bounds["lon"], lataxis_range=bounds["lat"], **geo_style)
    else:
        fig.update_geos(fitbounds="locations", **geo_style)

    legend = {
        **base_layout(theme)["legend"],
        "orientation": "h", "y": 0, "yanchor": "top", "x": 0.5, "xanchor": "center",
        "title": {"text": "Status:", "font": {"color": t["text_muted"], "size": 11}, "side": "left"},
        "itemclick": "toggle", "itemdoubleclick": "toggleothers",
    }
    fig.update_layout(
        **base_layout(theme, margin={"l": 0, "r": 0, "t": 0, "b": 28 if show_points else 0}, legend=legend),
        clickmode="event", showlegend=show_points,
        uirevision=f"{group}-{color_mode}-{'-'.join(sorted(selected))}",
    )
    return fig


# ---------- Time series ----------
def _end_labels(ends: list[tuple], t: dict, min_gap: float) -> list[dict]:
    """Value labels at the end of each line, pushed apart so they never overlap."""
    order = sorted(range(len(ends)), key=lambda i: ends[i][1])
    positions, previous = {}, None
    for i in order:
        y = ends[i][1]
        if previous is not None and y - previous < min_gap:
            y = previous + min_gap
        positions[i] = previous = y
    return [
        {
            "x": x, "y": positions[i], "xanchor": "left", "yanchor": "middle",
            "text": f" {_number(value)}%", "showarrow": False,
            "font": {"color": t["text_secondary"], "size": 12},
        }
        for i, (x, value) in enumerate(ends)
    ]


def group_timeseries(daily: pl.DataFrame, group: str, theme: str | None) -> go.Figure:
    """Daily mean per region or subsystem, one line each, direct-labeled at the end."""
    if daily.is_empty():
        return empty_figure(theme)

    t = tokens(theme)
    order = GROUPS[group]["order"]
    fig = go.Figure()
    ends = []
    for area in [a for a in order if a in daily["grupo"].unique().to_list()]:
        series = daily.filter(pl.col("grupo") == area)
        fig.add_trace(go.Scatter(
            x=series["data"], y=series["valor"], name=area, mode="lines",
            line={"color": group_color(area, theme, order), "width": 2},
            hovertemplate="%{y:.1f}%<extra>" + area + "</extra>",
        ))
        ends.append((series["data"][-1], series["valor"][-1]))

    fig.update_layout(
        **base_layout(theme, margin={"l": 8, "r": 56, "t": 32, "b": 8}),
        hovermode="x unified", annotations=_end_labels(ends, t, 0.075 * (daily["valor"].max() or 1)),
    )
    fig.update_yaxes(ticksuffix="%", rangemode="tozero")
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikecolor=t["axis"], spikedash="solid")
    return fig


def flows_timeseries(flows: pl.DataFrame, theme: str | None) -> go.Figure:
    """Total inflow vs outflow over the selected reservoirs (same unit, one axis)."""
    if flows.is_empty():
        return empty_figure(theme)

    t = tokens(theme)
    styles = {
        "vazao_afluente": {"color": "#6250d6" if theme != "dark" else "#9085e9", "width": 2},
        "vazao_defluente": {"color": t["text_muted"], "width": 2, "dash": "dot"},
    }
    fig = go.Figure()
    for column, label in FLOW_COLUMNS.items():
        fig.add_trace(go.Scatter(
            x=flows["data"], y=flows[column], name=label, mode="lines", line=styles[column],
            hovertemplate="%{y:,.0f} m³/s<extra>" + label + "</extra>",
        ))
    fig.update_layout(**base_layout(theme, margin={"l": 8, "r": 8, "t": 32, "b": 8}), hovermode="x unified")
    fig.update_yaxes(ticksuffix=" m³/s", rangemode="tozero", tickformat="~s")
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikecolor=t["axis"])
    return fig


def reservoir_ranking(
    latest: pl.DataFrame, group: str, focus: str | None, theme: str | None, limit: int = 15,
) -> go.Figure:
    """Reservoirs with the lowest current value, colored by area. Click a bar to focus it."""
    if latest.is_empty():
        return empty_figure(theme)

    t = tokens(theme)
    column = GROUPS[group]["column"]
    order = GROUPS[group]["order"]
    rows = latest.head(limit).reverse().with_columns(pl.col(column).fill_null("Sem localização").alias("_area"))
    fig = go.Figure()

    for area in [*order, "Sem localização"]:
        part = rows.filter(pl.col("_area") == area)
        if part.is_empty():
            continue
        is_focus = [rid == focus for rid in part["id_reservatorio"]]
        fig.add_trace(go.Bar(
            x=part["valor"], y=part["reservatorio"], orientation="h", name=area,
            marker={
                "color": group_color(area, theme, order) if area in order else t["text_muted"],
                "cornerradius": 4,
                "line": {
                    "color": [t["text_primary"] if f else t["surface"] for f in is_focus],
                    "width": [2 if f else 0 for f in is_focus],
                },
            },
            customdata=part.select("id_reservatorio", "bacia", "status").rows(),
            text=[f"{_number(v)}%" for v in part["valor"]],
            textposition="outside", textfont={"color": t["text_secondary"], "size": 11}, cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{customdata[1]}<br>%{x:.1f}% · %{customdata[2]}<extra>" + area + "</extra>",
        ))

    fig.update_layout(
        **base_layout(theme, margin={"l": 8, "r": 40, "t": 32, "b": 8}),
        bargap=0.35, barmode="overlay", height=max(320, 26 * rows.height + 60),
    )
    fig.update_yaxes(
        categoryorder="array", categoryarray=rows["reservatorio"].to_list(),
        showgrid=False, showline=False, ticklabelstandoff=8,
    )
    fig.update_xaxes(range=[0, 100], ticksuffix="%", showgrid=True, gridcolor=t["grid"], showline=False)
    return fig


def sparkline(history: pl.DataFrame, metric: str, theme: str | None) -> go.Figure:
    """Compact history of one reservoir for the focus card."""
    series = history.drop_nulls(metric)
    if series.is_empty():
        return empty_figure(theme, "Sem histórico")

    t = tokens(theme)
    color = t["series"][0]
    fig = go.Figure(go.Scatter(
        x=series["data"], y=series[metric], mode="lines",
        line={"color": color, "width": 2}, fill="tozeroy", fillcolor=_rgba(color, 0.12),
        hovertemplate="%{x|%d/%m/%Y}<br>%{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(**base_layout(theme, margin={"l": 0, "r": 0, "t": 4, "b": 0}), showlegend=False, height=120)
    fig.update_yaxes(range=[0, 100], showgrid=False, ticksuffix="%", nticks=3, tickfont={"size": 10})
    fig.update_xaxes(showline=False, tickfont={"size": 10}, nticks=4)
    return fig

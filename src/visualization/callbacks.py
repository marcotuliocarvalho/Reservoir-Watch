"""Interactivity: filters, map selection and zoom, alerts, focus reservoir and theme."""

from datetime import date, timedelta

import polars as pl
from dash import ALL, ClientsideFunction, Dash, Input, Output, State, ctx, html, no_update

from . import charts, geo
from .data import (
    ALERT_BELOW, CRITICAL_BELOW, FAST_DROP, GROUPS, METRICS, Filters, alerts, apply_filters,
    daily_by_group, daily_flows, group_summary, latest_by_reservoir, options,
    reservoir_history, summarize,
)
from .layout import status_badge
from .theme import group_color

FILTER_INPUTS = [
    Input("f-region", "value"),
    Input("f-subsystem", "value"),
    Input("f-ree", "value"),
    Input("f-basin", "value"),
    Input("f-type", "value"),
    Input("f-status", "value"),
    Input("f-range", "value"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
    Input("metric", "value"),
]

ALERT_LIMIT = 12


def _to_date(value) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def _number(value, decimals: int = 1, suffix: str = "") -> str:
    text = charts._number(value, decimals)
    return text if text == "–" else text + suffix


def _signed(value, decimals: int = 1, suffix: str = "") -> str:
    if value is None:
        return "–"
    sign = "+" if value >= 0 else "−"
    return f"{sign}{charts._number(abs(value), decimals)}{suffix}"


def _filters(regions, subsystems, rees, basins, types, statuses, value_range, start, end, metric) -> Filters:
    return Filters(
        regions=regions, subsystems=subsystems, rees=rees, basins=basins, types=types,
        statuses=statuses, start=_to_date(start), end=_to_date(end), metric=metric,
        value_range=tuple(value_range) if value_range else None,
    )


def _toggle(values: list | None, item: str) -> list:
    values = list(values or [])
    if item in values:
        values.remove(item)
    else:
        values.append(item)
    return values


def alert_reason(row: dict) -> str:
    volume, delta = row.get("volume_atual"), row.get("delta_volume_30d")
    parts = []
    if row["status"] == "Crítico":
        parts.append(f"volume {_number(volume, suffix='%')} < {CRITICAL_BELOW:.0f}%")
    elif row["status"] == "Alerta":
        parts.append(f"volume {_number(volume, suffix='%')} < {ALERT_BELOW:.0f}%")
    if delta is not None and delta <= -FAST_DROP:
        parts.append(f"queda de {_number(abs(delta))} p.p. em 30 dias")
    return " e ".join(parts) if parts else "sem gatilhos"


def _stat(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label, className="stat-label"), html.Span(value, className="stat-value")], className="stat")


def _alert_items(rows: pl.DataFrame) -> list:
    if rows.is_empty():
        return [html.P("Nenhum reservatório em alerta para os filtros atuais.", className="muted empty")]
    items = [
        html.Button(
            [
                status_badge(row["status"]),
                html.Div(
                    [
                        html.Span(row["reservatorio"], className="alert-name"),
                        html.Span(
                            f"{row['uf'] or '–'} · {row['regiao'] or 'sem região'} · {alert_reason(row)}",
                            className="alert-reason",
                        ),
                    ],
                    className="alert-text",
                ),
                html.Span(_number(row["volume_atual"], suffix="%"), className="alert-value"),
            ],
            id={"type": "alert-item", "index": row["id_reservatorio"]},
            className="alert-item",
            title="Ver reservatório",
        )
        for row in rows.head(ALERT_LIMIT).iter_rows(named=True)
    ]
    if rows.height > ALERT_LIMIT:
        items.append(html.P(f"+ {rows.height - ALERT_LIMIT} na tabela (filtre por Status)", className="muted more"))
    return items


def _alert_counts(latest: pl.DataFrame) -> list:
    counts = latest["status"].value_counts() if not latest.is_empty() else pl.DataFrame({"status": [], "count": []})
    lookup = dict(zip(counts["status"].to_list(), counts["count"].to_list()))
    return [
        html.Div([status_badge(status), html.Span(str(lookup.get(status, 0)), className="count")], className="alert-count")
        for status in ("Crítico", "Alerta", "Atenção", "Normal")
    ]


def _area_tiles(summary: pl.DataFrame, group: str, selected: list[str], metric: str, theme: str | None) -> list:
    order = GROUPS[group]["order"]
    rows = {row["grupo"]: row for row in summary.iter_rows(named=True)}
    tiles = []
    for area in order:
        row = rows.get(area)
        active = area in (selected or [])
        badges = []
        if row:
            for status, key in (("Crítico", "criticos"), ("Alerta", "alertas"), ("Atenção", "atencao")):
                if row[key]:
                    badges.append(html.Span([status_badge(status), f" {row[key]}"], className="tile-badge"))
        tiles.append(html.Button(
            [
                html.Div(
                    [
                        html.Span(className="swatch", style={"background": group_color(area, theme, order)}),
                        html.Span(area, className="tile-name"),
                    ],
                    className="tile-head",
                ),
                html.Span(_number(row["valor"] if row else None, suffix="%"), className="tile-value"),
                html.Span(f"{METRICS[metric]['short']} médio · {row['reservatorios'] if row else 0} reservatórios", className="tile-note"),
                html.Div(
                    [
                        _stat("Ponderado por capacidade", _number(row["volume_ponderado"] if row else None, suffix="%")),
                        _stat("Variação 30 dias", _signed(row["delta_30d"] if row else None, suffix=" p.p.")),
                    ],
                    className="tile-stats",
                ),
                html.Div(badges or [html.Span("Sem alertas", className="muted")], className="tile-badges"),
            ],
            id={"type": "area-tile", "index": area},
            className="area-tile" + (" is-active" if active else ""),
            **{"aria-pressed": "true" if active else "false"},
        ))
    return tiles


def register_callbacks(app: Dash, df: pl.DataFrame) -> None:
    min_date, max_date = df["data"].min(), df["data"].max()

    # Theme: stored per viewer, defaults to the OS preference.
    app.clientside_callback(
        ClientsideFunction(namespace="hidrico", function_name="toggleTheme"),
        Output("theme", "data"),
        Input("theme-toggle", "n_clicks"),
        State("theme", "data"),
    )

    @app.callback(Output("date-range", "start_date"), Output("date-range", "end_date"), Input("period-quick", "value"))
    def set_period(period):
        if period == "all" or not period:
            return min_date, max_date
        return max(min_date, max_date - timedelta(days=int(period))), max_date

    @app.callback(
        Output("f-region", "value"),
        Output("f-subsystem", "value"),
        Output("f-ree", "value"),
        Output("f-basin", "value"),
        Output("f-type", "value"),
        Output("f-status", "value"),
        Output("f-range", "value"),
        Input("map", "clickData"),
        Input({"type": "area-tile", "index": ALL}, "n_clicks"),
        Input("map-reset", "n_clicks"),
        Input("clear-filters", "n_clicks"),
        State("group", "value"),
        State("f-region", "value"),
        State("f-subsystem", "value"),
        prevent_initial_call=True,
    )
    def select_area(click, _tiles, _reset, _clear, group, regions, subsystems):
        unchanged = (no_update,) * 5
        trigger = ctx.triggered_id
        if trigger == "clear-filters":
            return [], [], [], [], [], [], [0, 100]
        if trigger == "map-reset":
            return [], [], *unchanged

        if isinstance(trigger, dict) and trigger.get("type") == "area-tile":
            if not ctx.triggered or not ctx.triggered[0]["value"]:
                return no_update, no_update, *unchanged
            area = trigger["index"]
        elif trigger == "map":
            point = (click or {}).get("points", [{}])[0]
            if not point.get("location"):  # reservoir marker: handled by the focus callback
                return no_update, no_update, *unchanged
            area = geo.area_of(point["location"], group)
        else:
            return no_update, no_update, *unchanged

        if area is None:
            return no_update, no_update, *unchanged
        if group == "regiao":
            return _toggle(regions, area), no_update, *unchanged
        return no_update, _toggle(subsystems, area), *unchanged

    @app.callback(
        Output("f-ree", "options"),
        Output("f-basin", "options"),
        Output("f-type", "options"),
        Input("f-region", "value"),
        Input("f-subsystem", "value"),
        Input("f-ree", "value"),
    )
    def cascade_options(regions, subsystems, rees):
        scope = apply_filters(df, Filters(regions=regions, subsystems=subsystems))
        basin_scope = apply_filters(scope, Filters(rees=rees))
        return options(scope, "ree"), options(basin_scope, "bacia"), options(scope, "tipo")

    @app.callback(
        Output("period-label", "children"),
        Output("kpi-metric-value", "children"),
        Output("kpi-metric-note", "children"),
        Output("kpi-alerts-value", "children"),
        Output("kpi-alerts-note", "children"),
        Output("kpi-inflow-value", "children"),
        Output("kpi-inflow-note", "children"),
        Output("kpi-outflow-value", "children"),
        Output("kpi-outflow-note", "children"),
        Output("map", "figure"),
        Output("timeseries", "figure"),
        Output("flows", "figure"),
        Output("ranking", "figure"),
        Output("table", "data"),
        Output("alert-counts", "children"),
        Output("alert-list", "children"),
        Output("area-tiles", "children"),
        Output("focus-reservoir", "options"),
        Output("focus-reservoir", "value"),
        *FILTER_INPUTS,
        Input("group", "value"),
        Input("map-color", "value"),
        Input("map-points", "value"),
        Input("theme", "data"),
        State("focus-reservoir", "value"),
    )
    def update_dashboard(
        regions, subsystems, rees, basins, types, statuses, value_range, start, end, metric,
        group, map_color, map_points, theme, focus,
    ):
        filters = _filters(regions, subsystems, rees, basins, types, statuses, value_range, start, end, metric)
        data = apply_filters(df, filters)
        meta = METRICS[metric]
        summary = summarize(data, metric)
        latest = latest_by_reservoir(data, metric)
        alert_rows = alerts(latest)

        # Map and area tiles ignore the area filters so every area stays clickable.
        area_scope = apply_filters(df, filters.replace(regions=None, subsystems=None))
        area_latest = latest_by_reservoir(area_scope, metric)
        area_summary = group_summary(area_latest, group)
        selected = regions if group == "regiao" else subsystems

        if summary.last_date:
            period = f"{filters.start or min_date:%d/%m/%Y} – {filters.end or max_date:%d/%m/%Y}"
            last = f"em {summary.last_date:%d/%m/%Y}"
        else:
            period, last = "Sem dados", ""

        if summary.metric_delta is None:
            delta_note = last
        else:
            arrow = "▲" if summary.metric_delta >= 0 else "▼"
            delta_note = f"{arrow} {_number(abs(summary.metric_delta))} p.p. em 30 dias"

        statuses_now = latest["status"].to_list() if not latest.is_empty() else []
        in_alert = sum(s in ("Crítico", "Alerta") for s in statuses_now)
        balance = (summary.inflow or 0) - (summary.outflow or 0)

        focus_options = [
            {"label": f"{row['reservatorio']} · {row['uf'] or row['subsistema']}", "value": row["id_reservatorio"]}
            for row in latest.sort("reservatorio").iter_rows(named=True)
        ]
        ids = latest["id_reservatorio"].to_list() if not latest.is_empty() else []
        if focus not in ids:
            # Prefer the most critical storage reservoir.
            focus = (alert_rows["id_reservatorio"].to_list() or ids or [None])[0]

        table = latest.with_columns(pl.col("data").dt.strftime("%d/%m/%Y")).to_dicts() if ids else []

        return (
            period,
            _number(summary.metric_value, suffix="%"),
            f"{meta['short']} · {delta_note}",
            str(in_alert),
            f"{statuses_now.count('Crítico')} crítico(s) · {statuses_now.count('Atenção')} em atenção",
            _number(summary.inflow, 0, " m³/s"),
            last,
            _number(summary.outflow, 0, " m³/s"),
            f"Balanço {_signed(balance, 0, ' m³/s')}",
            charts.brazil_map(area_summary, area_latest, group, map_color, selected, bool(map_points), metric, theme),
            charts.group_timeseries(daily_by_group(data, metric, group), group, theme),
            charts.flows_timeseries(daily_flows(data), theme),
            charts.reservoir_ranking(latest, group, focus, theme),
            table,
            _alert_counts(latest),
            _alert_items(alert_rows),
            _area_tiles(area_summary, group, selected, metric, theme),
            focus_options,
            focus,
        )

    @app.callback(
        Output("focus-reservoir", "value", allow_duplicate=True),
        Input("ranking", "clickData"),
        Input("map", "clickData"),
        Input({"type": "alert-item", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def focus_from_click(ranking_click, map_click, _alerts):
        trigger = ctx.triggered_id
        if isinstance(trigger, dict):
            return trigger["index"] if ctx.triggered and ctx.triggered[0]["value"] else no_update
        if trigger not in ("ranking", "map"):
            return no_update
        click = ranking_click if trigger == "ranking" else map_click
        point = (click or {}).get("points", [{}])[0]
        if point.get("location"):  # a state, not a reservoir marker
            return no_update
        customdata = point.get("customdata")
        return customdata[0] if customdata else no_update

    @app.callback(
        Output("focus-body", "children"),
        Output("focus-sparkline", "figure"),
        Input("focus-reservoir", "value"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("metric", "value"),
        Input("theme", "data"),
    )
    def update_focus(reservoir_id, start, end, metric, theme):
        if not reservoir_id:
            return html.P("Nenhum reservatório para os filtros atuais.", className="muted"), charts.empty_figure(theme, "")

        history = apply_filters(reservoir_history(df, reservoir_id), Filters(start=_to_date(start), end=_to_date(end)))
        if history.is_empty():
            return html.P("Sem leituras no período.", className="muted"), charts.empty_figure(theme, "")

        row = latest_by_reservoir(history, metric).row(0, named=True)
        current, delta = row["valor"], row["delta_30d"]
        level = max(0.0, min(100.0, current or 0))
        balance = None
        if row["vazao_afluente"] is not None and row["vazao_defluente"] is not None:
            balance = row["vazao_afluente"] - row["vazao_defluente"]

        tank = html.Div(
            [
                html.Div(className="tank-water", style={"height": f"{level}%"}),
                *[html.Span(className="tank-tick", style={"bottom": f"{tick}%"}) for tick in (25, 50, 75)],
                html.Span(_number(current, suffix="%"), className="tank-value"),
            ],
            className="tank",
            role="img",
            **{"aria-label": f"{METRICS[metric]['label']}: {_number(current, suffix='%')}"},
        )
        location = " · ".join(filter(None, [row["uf"], row["regiao"], row["subsistema"]]))
        body = [
            tank,
            html.Div(
                [
                    html.Div([html.H3(row["reservatorio"]), status_badge(row["status"])], className="focus-title"),
                    html.P(location, className="muted"),
                    html.P(
                        f"Bacia {row['bacia'] or '–'} · rio {row['rio'] or '–'} · REE {row['ree'] or '–'} · tipo {row['tipo']}",
                        className="muted",
                    ),
                    html.P(alert_reason(row), className="focus-reason") if row["status"] in ("Crítico", "Alerta", "Atenção") else None,
                    html.Div(
                        [
                            _stat(METRICS[metric]["label"], _number(current, suffix="%")),
                            _stat("Variação 30 dias", _signed(delta, suffix=" p.p.")),
                            _stat("Afluente", _number(row["vazao_afluente"], 0, " m³/s")),
                            _stat("Defluente", _number(row["vazao_defluente"], 0, " m³/s")),
                            _stat("Balanço", _signed(balance, 0, " m³/s")),
                            _stat("Capacidade útil", _number(row["capacidade_hm3"], 0, " hm³")),
                        ],
                        className="stats",
                    ),
                ],
                className="focus-info",
            ),
        ]
        return body, charts.sparkline(history, metric, theme)

"""Static page structure of the dashboard."""

import polars as pl
from dash import dash_table, dcc, html

from . import charts
from .data import GROUPS, METRICS, REGION_ORDER, STATUS_RULES, SUBSYSTEM_ORDER, options
from .theme import STATUS_ICONS

PERIODS = [
    {"label": "30 days", "value": "30"},
    {"label": "90 days", "value": "90"},
    {"label": "1 year", "value": "365"},
    {"label": "All", "value": "all"},
]

TABLE_COLUMNS = [
    {"name": "Reservoir", "id": "reservatorio"},
    {"name": "Status", "id": "status"},
    {"name": "State", "id": "uf"},
    {"name": "Region", "id": "regiao"},
    {"name": "Subsystem", "id": "subsistema"},
    {"name": "Basin", "id": "bacia"},
    {"name": "Type", "id": "tipo"},
    {"name": "Value (%)", "id": "valor", "type": "numeric", "format": {"specifier": ".1f"}},
    {"name": "Δ 30 days (pp)", "id": "delta_30d", "type": "numeric", "format": {"specifier": "+.1f"}},
    {"name": "Inflow (m³/s)", "id": "vazao_afluente", "type": "numeric", "format": {"specifier": ",.0f"}},
    {"name": "Outflow (m³/s)", "id": "vazao_defluente", "type": "numeric", "format": {"specifier": ",.0f"}},
    {"name": "Last reading", "id": "data"},
]

STATUS_CLASS = {
    "Critical": "critical", "Alert": "serious", "Watch": "warning",
    "Normal": "good", "Unclassified": "none",
}

DROP_ICON = html.Span(className="brand-mark", children=html.Span(className="brand-drop"), **{"aria-hidden": "true"})


def status_badge(status: str | None) -> html.Span:
    status = status or "Unclassified"
    return html.Span(
        f"{STATUS_ICONS[status]} {status}",
        className=f"status status-{STATUS_CLASS[status]}",
        title=STATUS_RULES[status],
    )


def _field(label: str, control, class_name: str = "") -> html.Div:
    return html.Div([html.Label(label, className="field-label"), control], className=f"field {class_name}")


def _card(title, subtitle, body, class_name: str = "", extra=None, card_id: str | None = None) -> html.Section:
    header = [html.Div([html.H2(title), html.P(subtitle, className="card-subtitle") if subtitle else None])]
    if extra is not None:
        header.append(extra)
    props = {"id": card_id} if card_id else {}
    return html.Section([html.Header(header, className="card-header"), body], className=f"card {class_name}", **props)


def _kpi(kpi_id: str, label: str) -> html.Div:
    return html.Div(
        [
            html.Span(label, className="kpi-label"),
            html.Span("–", id=f"{kpi_id}-value", className="kpi-value"),
            html.Span("", id=f"{kpi_id}-note", className="kpi-note"),
        ],
        className="kpi",
        id=kpi_id,
    )


def _graph(graph_id: str, height: int | None = None, config: dict | None = None) -> dcc.Loading:
    style = {"width": "100%"}
    if height:
        style["height"] = f"{height}px"
    return dcc.Loading(
        dcc.Graph(id=graph_id, config=config or charts.GRAPH_CONFIG, style=style),
        type="dot", color="#2a78d6", delay_show=400,
    )


def _status_rules() -> html.Details:
    return html.Details(
        [
            html.Summary("Criticality rules"),
            html.Ul([html.Li([status_badge(status), f" {rule}"]) for status, rule in STATUS_RULES.items()]),
            html.P(
                "Only storage reservoirs (types RCU, RES, RBB) are classified, "
                "always by useful volume. Reference thresholds, not an official ONS criterion.",
                className="muted",
            ),
        ],
        className="rules",
    )


def build_layout(df: pl.DataFrame) -> html.Div:
    min_date, max_date = df["data"].min(), df["data"].max()

    header = html.Header(
        [
            html.Div(
                [
                    DROP_ICON,
                    html.Div([
                        html.H1("Water Dashboard"),
                        html.P("Reservoirs of the Brazilian National Interconnected System · ONS open data", className="subtitle"),
                    ]),
                ],
                className="brand",
            ),
            html.Div(
                [
                    html.Span(id="period-label", className="period-label"),
                    html.Button(
                        [html.Span(className="theme-icon"), html.Span("Theme", className="sr-only")],
                        id="theme-toggle", className="icon-button", title="Toggle light/dark theme",
                    ),
                ],
                className="header-actions",
            ),
        ],
        className="topbar",
    )

    filters = html.Section(
        [
            html.Div(
                [
                    _field("Period", dcc.RadioItems(PERIODS, value="365", id="period-quick", className="chips", inline=True)),
                    _field("Date range", dcc.DatePickerRange(
                        id="date-range", min_date_allowed=min_date, max_date_allowed=max_date,
                        start_date=max(min_date, max_date.replace(year=max_date.year - 1)), end_date=max_date,
                        display_format="MMM D, YYYY", first_day_of_week=0,
                    )),
                    _field("Metric", dcc.RadioItems(
                        [{"label": m["label"], "value": key} for key, m in METRICS.items()],
                        value="volume_util", id="metric", className="chips", inline=True,
                    )),
                    _field("Group by", dcc.RadioItems(
                        [{"label": g["label"], "value": key} for key, g in GROUPS.items()],
                        value="regiao", id="group", className="chips", inline=True,
                    )),
                ],
                className="filter-row",
            ),
            html.Div(
                [
                    _field("Region", dcc.Dropdown(
                        [{"label": r, "value": r} for r in REGION_ORDER], multi=True, id="f-region", placeholder="All",
                    )),
                    _field("Subsystem", dcc.Dropdown(
                        [{"label": s, "value": s} for s in SUBSYSTEM_ORDER], multi=True, id="f-subsystem", placeholder="All",
                    )),
                    _field("REE", dcc.Dropdown(options(df, "ree"), multi=True, id="f-ree", placeholder="All")),
                    _field("Basin", dcc.Dropdown(options(df, "bacia"), multi=True, id="f-basin", placeholder="All")),
                    _field("Type", dcc.Dropdown(options(df, "tipo"), multi=True, id="f-type", placeholder="All")),
                    _field("Status", dcc.Dropdown(
                        [{"label": f"{STATUS_ICONS[s]} {s}", "value": s} for s in STATUS_RULES],
                        multi=True, id="f-status", placeholder="All",
                    )),
                    _field("Current range (%)", dcc.RangeSlider(
                        0, 100, 5, value=[0, 100], id="f-range",
                        marks={0: "0", 25: "25", 50: "50", 75: "75", 100: "100"},
                        tooltip={"placement": "bottom", "always_visible": False},
                    ), "field-range"),
                    html.Button("Clear filters", id="clear-filters", className="text-button"),
                ],
                className="filter-row filter-row-dims",
            ),
        ],
        className="filters card",
        **{"aria-label": "Filters"},
    )

    kpis = html.Section(
        [
            _kpi("kpi-metric", "Current mean"),
            _kpi("kpi-alerts", "Reservoirs in alert"),
            _kpi("kpi-inflow", "Total inflow"),
            _kpi("kpi-outflow", "Total outflow"),
        ],
        className="kpis",
    )

    map_controls = html.Div(
        [
            dcc.RadioItems(
                [{"label": "Color by area", "value": "area"}, {"label": "Color by mean", "value": "valor"}],
                value="area", id="map-color", className="chips chips-sm", inline=True,
            ),
            dcc.Checklist(
                [{"label": "Reservoirs", "value": "on"}], value=["on"], id="map-points",
                className="chips chips-sm", inline=True,
            ),
            html.Button("Show Brazil", id="map-reset", className="text-button text-button-sm"),
        ],
        className="card-controls",
    )
    map_card = _card(
        "Map",
        "Click an area to filter and zoom in; click a point to see the reservoir. "
        "Scroll to zoom; double-click to reset.",
        _graph("map", 480, charts.MAP_CONFIG),
        class_name="card-map",
        extra=map_controls,
    )

    alerts_card = _card(
        "Criticality alerts",
        "Storage reservoirs, by last reading",
        html.Div(
            [
                html.Div(id="alert-counts", className="alert-counts"),
                html.Div(id="alert-list", className="alert-list"),
                _status_rules(),
            ],
            className="alerts",
        ),
        class_name="card-alerts",
    )

    areas_card = _card(
        "Analysis by area",
        "Last reading of each reservoir. Click an area to filter.",
        html.Div(id="area-tiles", className="area-tiles"),
        card_id="areas-card",
    )

    focus = _card(
        "Reservoir in focus",
        "Current state · pick from the list, map, alerts or ranking",
        html.Div(
            [
                dcc.Dropdown(id="focus-reservoir", clearable=False, placeholder="Select a reservoir"),
                html.Div(id="focus-body", className="focus-body"),
                dcc.Graph(id="focus-sparkline", config={"displayModeBar": False}, style={"height": "120px", "width": "100%"}),
            ],
            className="focus",
        ),
        class_name="card-focus",
    )

    return html.Div(
        [
            dcc.Store(id="theme", storage_type="local"),
            header,
            html.Main(
                [
                    filters,
                    kpis,
                    html.Div([map_card, alerts_card], className="grid grid-map"),
                    areas_card,
                    html.Div(
                        [
                            focus,
                            _card("Trend by area", "Simple daily mean across reservoirs", _graph("timeseries", 360)),
                        ],
                        className="grid grid-2",
                    ),
                    html.Div(
                        [
                            _card("Lowest current levels", "15 reservoirs with the lowest value at the last reading", _graph("ranking")),
                            _card("Flows", "Daily sum over the selected reservoirs", _graph("flows", 360)),
                        ],
                        className="grid grid-2",
                    ),
                    _card(
                        "Table",
                        "Last reading of each reservoir",
                        dash_table.DataTable(
                            id="table", columns=TABLE_COLUMNS, page_size=12,
                            sort_action="native", filter_action="native",
                            style_as_list_view=True, style_table={"overflowX": "auto"},
                            style_cell={"fontFamily": "inherit", "fontSize": "13px", "padding": "8px 10px", "textAlign": "left"},
                            style_cell_conditional=[{"if": {"column_type": "numeric"}, "textAlign": "right"}],
                        ),
                        class_name="card-table",
                    ),
                ],
                className="content",
            ),
            html.Footer(
                [
                    "Source: ONS — Reservoir Hydrological Data and Reservoir Registry (dados.ons.org.br). ",
                    "Map: IBGE state mesh. The region comes from the state in the ONS registry; the state–subsystem mapping on the map is approximate.",
                ],
                className="footer",
            ),
        ],
        className="app",
        id="app-root",
    )

"""Static page structure of the dashboard."""

import polars as pl
from dash import dash_table, dcc, html

from . import charts
from .data import GROUPS, METRICS, REGION_ORDER, STATUS_RULES, SUBSYSTEM_ORDER, options
from .theme import STATUS_ICONS

PERIODS = [
    {"label": "30 dias", "value": "30"},
    {"label": "90 dias", "value": "90"},
    {"label": "1 ano", "value": "365"},
    {"label": "Tudo", "value": "all"},
]

BR = {"decimal": ",", "group": "."}

TABLE_COLUMNS = [
    {"name": "Reservatório", "id": "reservatorio"},
    {"name": "Status", "id": "status"},
    {"name": "UF", "id": "uf"},
    {"name": "Região", "id": "regiao"},
    {"name": "Subsistema", "id": "subsistema"},
    {"name": "Bacia", "id": "bacia"},
    {"name": "Tipo", "id": "tipo"},
    {"name": "Valor (%)", "id": "valor", "type": "numeric", "format": {"specifier": ".1f", "locale": BR}},
    {"name": "Δ 30 dias (p.p.)", "id": "delta_30d", "type": "numeric", "format": {"specifier": "+.1f", "locale": BR}},
    {"name": "Afluente (m³/s)", "id": "vazao_afluente", "type": "numeric", "format": {"specifier": ",.0f", "locale": BR}},
    {"name": "Defluente (m³/s)", "id": "vazao_defluente", "type": "numeric", "format": {"specifier": ",.0f", "locale": BR}},
    {"name": "Última leitura", "id": "data"},
]

STATUS_CLASS = {
    "Crítico": "critical", "Alerta": "serious", "Atenção": "warning",
    "Normal": "good", "Sem classificação": "none",
}

DROP_ICON = html.Span(className="brand-mark", children=html.Span(className="brand-drop"), **{"aria-hidden": "true"})


def status_badge(status: str | None) -> html.Span:
    status = status or "Sem classificação"
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
            html.Summary("Regras de criticidade"),
            html.Ul([html.Li([status_badge(status), f" {rule}"]) for status, rule in STATUS_RULES.items()]),
            html.P(
                "Só reservatórios com armazenamento (tipos RCU, RES, RBB) são classificados, "
                "sempre pelo volume útil. Limites de referência, não critério oficial do ONS.",
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
                        html.H1("Painel Hídrico"),
                        html.P("Reservatórios do Sistema Interligado Nacional · dados abertos ONS", className="subtitle"),
                    ]),
                ],
                className="brand",
            ),
            html.Div(
                [
                    html.Span(id="period-label", className="period-label"),
                    html.Button(
                        [html.Span(className="theme-icon"), html.Span("Tema", className="sr-only")],
                        id="theme-toggle", className="icon-button", title="Alternar tema claro/escuro",
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
                    _field("Período", dcc.RadioItems(PERIODS, value="365", id="period-quick", className="chips", inline=True)),
                    _field("Intervalo", dcc.DatePickerRange(
                        id="date-range", min_date_allowed=min_date, max_date_allowed=max_date,
                        start_date=max(min_date, max_date.replace(year=max_date.year - 1)), end_date=max_date,
                        display_format="DD/MM/YYYY", first_day_of_week=1,
                    )),
                    _field("Métrica", dcc.RadioItems(
                        [{"label": m["label"], "value": key} for key, m in METRICS.items()],
                        value="volume_util", id="metric", className="chips", inline=True,
                    )),
                    _field("Agrupar por", dcc.RadioItems(
                        [{"label": g["label"], "value": key} for key, g in GROUPS.items()],
                        value="regiao", id="group", className="chips", inline=True,
                    )),
                ],
                className="filter-row",
            ),
            html.Div(
                [
                    _field("Região", dcc.Dropdown(
                        [{"label": r, "value": r} for r in REGION_ORDER], multi=True, id="f-region", placeholder="Todas",
                    )),
                    _field("Subsistema", dcc.Dropdown(
                        [{"label": s, "value": s} for s in SUBSYSTEM_ORDER], multi=True, id="f-subsystem", placeholder="Todos",
                    )),
                    _field("REE", dcc.Dropdown(options(df, "ree"), multi=True, id="f-ree", placeholder="Todos")),
                    _field("Bacia", dcc.Dropdown(options(df, "bacia"), multi=True, id="f-basin", placeholder="Todas")),
                    _field("Tipo", dcc.Dropdown(options(df, "tipo"), multi=True, id="f-type", placeholder="Todos")),
                    _field("Status", dcc.Dropdown(
                        [{"label": f"{STATUS_ICONS[s]} {s}", "value": s} for s in STATUS_RULES],
                        multi=True, id="f-status", placeholder="Todos",
                    )),
                    _field("Faixa atual (%)", dcc.RangeSlider(
                        0, 100, 5, value=[0, 100], id="f-range",
                        marks={0: "0", 25: "25", 50: "50", 75: "75", 100: "100"},
                        tooltip={"placement": "bottom", "always_visible": False},
                    ), "field-range"),
                    html.Button("Limpar filtros", id="clear-filters", className="text-button"),
                ],
                className="filter-row filter-row-dims",
            ),
        ],
        className="filters card",
        **{"aria-label": "Filtros"},
    )

    kpis = html.Section(
        [
            _kpi("kpi-metric", "Média atual"),
            _kpi("kpi-alerts", "Reservatórios em alerta"),
            _kpi("kpi-inflow", "Vazão afluente total"),
            _kpi("kpi-outflow", "Vazão defluente total"),
        ],
        className="kpis",
    )

    map_controls = html.Div(
        [
            dcc.RadioItems(
                [{"label": "Cor por área", "value": "area"}, {"label": "Cor por média", "value": "valor"}],
                value="area", id="map-color", className="chips chips-sm", inline=True,
            ),
            dcc.Checklist(
                [{"label": "Reservatórios", "value": "on"}], value=["on"], id="map-points",
                className="chips chips-sm", inline=True,
            ),
            html.Button("Ver Brasil", id="map-reset", className="text-button text-button-sm"),
        ],
        className="card-controls",
    )
    map_card = _card(
        "Mapa",
        "Clique numa área para filtrar e aproximar; clique num ponto para ver o reservatório. "
        "Role para zoom; duplo clique volta.",
        _graph("map", 480, charts.MAP_CONFIG),
        class_name="card-map",
        extra=map_controls,
    )

    alerts_card = _card(
        "Alertas de criticidade",
        "Reservatórios com armazenamento, pela última leitura",
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
        "Análise por área",
        "Última leitura de cada reservatório. Clique numa área para filtrar.",
        html.Div(id="area-tiles", className="area-tiles"),
        card_id="areas-card",
    )

    focus = _card(
        "Reservatório em foco",
        "Estado atual · escolha na lista, no mapa, nos alertas ou no ranking",
        html.Div(
            [
                dcc.Dropdown(id="focus-reservoir", clearable=False, placeholder="Selecione um reservatório"),
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
                            _card("Evolução por área", "Média diária simples entre reservatórios", _graph("timeseries", 360)),
                        ],
                        className="grid grid-2",
                    ),
                    html.Div(
                        [
                            _card("Menores níveis atuais", "15 reservatórios com menor valor na última leitura", _graph("ranking")),
                            _card("Vazões", "Soma diária dos reservatórios selecionados", _graph("flows", 360)),
                        ],
                        className="grid grid-2",
                    ),
                    _card(
                        "Tabela",
                        "Última leitura de cada reservatório",
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
                    "Fonte: ONS — Dados Hidrológicos de Reservatórios e cadastro de Reservatórios (dados.ons.org.br). ",
                    "Mapa: malha de UFs do IBGE. A região vem da UF do cadastro ONS; a associação estado–subsistema no mapa é aproximada.",
                ],
                className="footer",
            ),
        ],
        className="app",
        id="app-root",
    )

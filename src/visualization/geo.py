"""Brazilian states (IBGE mesh), IBGE regions and SIN subsystems.

Mesh source: IBGE API v3 (malhas/paises/BR, intrarregiao=UF, qualidade=minima).

The state -> subsystem assignment is an approximation of the SIN electrical
areas, used only to paint and select areas on the map. Reservoir regions come
from the state in the ONS registry (CEG code), not from this table.
"""

import json
from functools import lru_cache
from pathlib import Path

GEOJSON_PATH = Path(__file__).parent / "static" / "brasil_uf.geojson"

REGION_ORDER = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]

# IBGE state code -> (UF, IBGE region, SIN subsystem)
STATES = {
    "11": ("RO", "Norte", "Sudeste/Centro-Oeste"),
    "12": ("AC", "Norte", "Sudeste/Centro-Oeste"),
    "13": ("AM", "Norte", "Norte"),
    "14": ("RR", "Norte", "Norte"),
    "15": ("PA", "Norte", "Norte"),
    "16": ("AP", "Norte", "Norte"),
    "17": ("TO", "Norte", "Norte"),
    "21": ("MA", "Nordeste", "Norte"),
    "22": ("PI", "Nordeste", "Nordeste"),
    "23": ("CE", "Nordeste", "Nordeste"),
    "24": ("RN", "Nordeste", "Nordeste"),
    "25": ("PB", "Nordeste", "Nordeste"),
    "26": ("PE", "Nordeste", "Nordeste"),
    "27": ("AL", "Nordeste", "Nordeste"),
    "28": ("SE", "Nordeste", "Nordeste"),
    "29": ("BA", "Nordeste", "Nordeste"),
    "31": ("MG", "Sudeste", "Sudeste/Centro-Oeste"),
    "32": ("ES", "Sudeste", "Sudeste/Centro-Oeste"),
    "33": ("RJ", "Sudeste", "Sudeste/Centro-Oeste"),
    "35": ("SP", "Sudeste", "Sudeste/Centro-Oeste"),
    "41": ("PR", "Sul", "Sul"),
    "42": ("SC", "Sul", "Sul"),
    "43": ("RS", "Sul", "Sul"),
    "50": ("MS", "Centro-Oeste", "Sudeste/Centro-Oeste"),
    "51": ("MT", "Centro-Oeste", "Sudeste/Centro-Oeste"),
    "52": ("GO", "Centro-Oeste", "Sudeste/Centro-Oeste"),
    "53": ("DF", "Centro-Oeste", "Sudeste/Centro-Oeste"),
}

UF_REGION = {uf: region for uf, region, _ in STATES.values()}

GROUP_INDEX = {"regiao": 1, "subsistema": 2}


def _signed_area(ring: list) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0, *_), (x1, y1, *_) in zip(ring, ring[1:]))


def _orient(ring: list, clockwise: bool) -> list:
    is_clockwise = _signed_area(ring) < 0
    return ring if is_clockwise == clockwise else ring[::-1]


def _rewind(geometry: dict) -> dict:
    """Clockwise outer rings, counter-clockwise holes (what Plotly/d3 expect).

    The IBGE mesh follows RFC 7946 (the opposite winding), which makes Plotly
    fill the whole globe instead of the state.
    """
    def polygon(rings):
        return [_orient(ring, clockwise=(i == 0)) for i, ring in enumerate(rings)]

    if geometry["type"] == "Polygon":
        return {**geometry, "coordinates": polygon(geometry["coordinates"])}
    if geometry["type"] == "MultiPolygon":
        return {**geometry, "coordinates": [polygon(p) for p in geometry["coordinates"]]}
    return geometry


@lru_cache(maxsize=1)
def states_geojson() -> dict:
    with GEOJSON_PATH.open(encoding="utf-8") as file:
        data = json.load(file)
    for feature in data["features"]:
        feature["geometry"] = _rewind(feature["geometry"])
    return data


def _points(geometry: dict):
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    for polygon in polygons:
        for lon, lat, *_ in polygon[0]:
            yield lon, lat


@lru_cache(maxsize=1)
def _state_bounds() -> dict[str, tuple[float, float, float, float]]:
    bounds = {}
    for feature in states_geojson()["features"]:
        points = list(_points(feature["geometry"]))
        lons, lats = [p[0] for p in points], [p[1] for p in points]
        bounds[feature["properties"]["codarea"]] = (min(lons), max(lons), min(lats), max(lats))
    return bounds


def area_of(state_code: str, group: str) -> str | None:
    """Region or subsystem of an IBGE state code."""
    state = STATES.get(str(state_code))
    return state[GROUP_INDEX[group]] if state else None


def states_in(areas: list[str], group: str) -> list[str]:
    return [code for code, state in STATES.items() if state[GROUP_INDEX[group]] in areas]


def bounds_of(areas: list[str], group: str, pad: float = 0.08) -> dict | None:
    """Longitude/latitude ranges that frame the given areas, with padding."""
    codes = states_in(areas, group)
    if not codes:
        return None
    boxes = [_state_bounds()[code] for code in codes if code in _state_bounds()]
    lon0, lon1 = min(b[0] for b in boxes), max(b[1] for b in boxes)
    lat0, lat1 = min(b[2] for b in boxes), max(b[3] for b in boxes)
    dlon, dlat = (lon1 - lon0) * pad + 0.5, (lat1 - lat0) * pad + 0.5
    return {"lon": [lon0 - dlon, lon1 + dlon], "lat": [lat0 - dlat, lat1 + dlat]}

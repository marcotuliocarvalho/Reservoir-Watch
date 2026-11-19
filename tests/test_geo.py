from src.visualization import geo


def test_rewind_outer_ring_clockwise_and_holes_counter_clockwise():
    counter_clockwise = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    geometry = {"type": "Polygon", "coordinates": [counter_clockwise, counter_clockwise]}

    outer, hole = geo._rewind(geometry)["coordinates"]

    assert geo._signed_area(outer) < 0
    assert geo._signed_area(hole) > 0


def test_states_geojson_has_every_state():
    codes = {f["properties"]["codarea"] for f in geo.states_geojson()["features"]}
    assert codes == set(geo.STATES)


def test_area_of():
    assert geo.area_of("31", "regiao") == "Sudeste"
    assert geo.area_of("31", "subsistema") == "Sudeste/Centro-Oeste"
    assert geo.area_of("99", "regiao") is None


def test_bounds_of_frames_the_south():
    bounds = geo.bounds_of(["Sul"], "regiao")
    lon0, lon1 = bounds["lon"]
    lat0, lat1 = bounds["lat"]
    assert lon0 < -57 < -48 < lon1
    assert lat0 < -33 < -22 < lat1
    assert geo.bounds_of(["Nowhere"], "regiao") is None

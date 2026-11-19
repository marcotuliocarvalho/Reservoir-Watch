"""Chart builders that order or pick reservoirs."""

from src.visualization import charts, data


def _ranked_names(fig):
    return fig.layout.yaxis.categoryarray


def test_ranking_lists_lowest_at_the_top(dashboard_df):
    latest = data.latest_by_reservoir(dashboard_df, "volume_util")
    names = _ranked_names(charts.reservoir_ranking(latest, "regiao", None, None))

    # Plotly draws the first category at the bottom, so the top bar is the last one.
    assert names[-1] == latest["reservatorio"][0]


def test_ranking_highest_lists_highest_at_the_top(dashboard_df):
    latest = data.latest_by_reservoir(dashboard_df, "volume_util")
    names = _ranked_names(charts.reservoir_ranking(latest, "regiao", None, None, highest=True))

    assert names[-1] == latest["reservatorio"][-1]
    assert list(names) == latest["reservatorio"].to_list()[-len(names):]

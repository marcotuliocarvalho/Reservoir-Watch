"""Smoke tests: the Dash app builds and serves its layout."""

import pytest

from src.visualization.app import create_app


@pytest.fixture
def client(dashboard_df):
    app = create_app(df=dashboard_df)
    return app.server.test_client()


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Water Dashboard" in response.data


def test_layout_and_callbacks_are_served(client):
    layout = client.get("/_dash-layout")
    dependencies = client.get("/_dash-dependencies")

    assert layout.status_code == 200
    assert dependencies.status_code == 200
    assert len(dependencies.get_json()) > 0

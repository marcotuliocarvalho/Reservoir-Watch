"""WSGI entry point for production servers.

Run with: gunicorn src.visualization.wsgi:server
The dataset location comes from HIDRIC_DATA_DIR (see data.resolve_sources).
"""

from .app import create_app

app = create_app()
server = app.server

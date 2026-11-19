"""Run with: python -m src.visualization [--source PATH] [--port 8050] [--debug]

PATH can be a Parquet file, a directory or a glob pattern. Without it, the
dashboard reads HIDRIC_DATA_DIR, then ./data, then ./arquivo.parquet.
"""

import argparse

from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Painel Hídrico (Dash)")
    parser.add_argument("--source", help="arquivo, diretório ou glob de arquivos Parquet")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app(args.source)
    app.run(host=args.host, port=args.port, debug=args.debug, dev_tools_disable_version_check=True)


if __name__ == "__main__":
    main()

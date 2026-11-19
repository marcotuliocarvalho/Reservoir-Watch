"""Run with: python -m src.visualization [--source PATH] [--port 8050] [--debug]

PATH can be a Parquet file, a directory or a glob pattern. Without it, the
dashboard reads HIDRIC_DATA_DIR, then ./data.

``--export FILE`` writes the prepared dataset to FILE and exits, without
starting the server.
"""

import argparse

from .app import create_app
from .data import export_dataset


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Water Dashboard (Dash)")
    parser.add_argument("--source", help="Parquet file, directory or glob pattern")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--export", metavar="FILE", help="Write the prepared dataset to FILE and exit")
    args = parser.parse_args(argv)

    if args.export:
        print(f"Wrote {export_dataset(args.export, args.source)}")
        return

    app = create_app(args.source)
    app.run(host=args.host, port=args.port, debug=args.debug, dev_tools_disable_version_check=True)


if __name__ == "__main__":
    main()

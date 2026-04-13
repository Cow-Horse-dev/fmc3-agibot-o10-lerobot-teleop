#!/usr/bin/env python3

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import socketserver
from pathlib import Path


class HDWebRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve Unity WebGL assets with the headers HDWebClient expects."""

    def end_headers(self) -> None:
        if self.path.endswith(".unityweb"):
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Cache-Control", "no-cache")
        elif self.path.endswith(".wasm"):
            self.send_header("Cache-Control", "no-cache")

        super().end_headers()

    def guess_type(self, path: str) -> str:
        if path.endswith(".js.unityweb"):
            return "application/javascript"
        if path.endswith(".wasm.unityweb"):
            return "application/wasm"
        if path.endswith(".data.unityweb"):
            return "application/octet-stream"
        return super().guess_type(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve HDWebClient with Unity headers")
    parser.add_argument("--web-dir", required=True, help="HDWebClient directory")
    parser.add_argument("--port", type=int, default=8088, help="HTTP port")
    parser.add_argument(
        "--server-url",
        required=True,
        help="WebSocket URL written into server-config.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    web_dir = Path(args.web_dir).expanduser().resolve()
    config_path = web_dir / "server-config.json"
    config_path.write_text(
        json.dumps({"serverUrl": args.server_url}, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )

    handler = functools.partial(HDWebRequestHandler, directory=os.fspath(web_dir))

    class ThreadingTCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    with ThreadingTCPServer(("", args.port), handler) as httpd:
        print(f"HDWebClient serverUrl set to {args.server_url}")
        print(f"Open http://127.0.0.1:{args.port}/ in your browser")
        httpd.serve_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

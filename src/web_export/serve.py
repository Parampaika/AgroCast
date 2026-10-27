"""Локальный сервер для разработки сайта web/ без кэширования (чтобы правки JS сразу были видны).

Запуск: uv run python -I src/web_export/serve.py [порт]
"""
import functools
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web"


class NoCache(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    print(f"http://localhost:{port}")
    ThreadingHTTPServer(("", port), functools.partial(NoCache, directory=str(WEB))).serve_forever()

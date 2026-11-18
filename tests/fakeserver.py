"""テスト用の偽 HTTP サーバー(標準ライブラリ http.server)。実際のサービスには接続しない。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit


class FakeServer:
    def __init__(self):
        self.routes = {}      # path -> (status, body(bytes|dict|callable), headers)
        self.requests = []    # dict(path, query, headers)
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                parts = urlsplit(self.path)
                outer.requests.append({"path": parts.path, "query": parse_qs(parts.query), "headers": dict(self.headers)})
                route = outer.routes.get(parts.path)
                if route is None:
                    status, body, headers = 404, b"nf", {}
                else:
                    status, body, headers = route
                    if callable(body):
                        body = body(outer.requests[-1])
                inm = self.headers.get("If-None-Match")
                if inm and headers.get("ETag") == inm:
                    self.send_response(304)
                    self.end_headers()
                    return
                if isinstance(body, (dict, list)):
                    body = json.dumps(body).encode()
                if isinstance(body, str):
                    body = body.encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"
        self.thread = threading.Thread(target=lambda: self.httpd.serve_forever(poll_interval=0.01), daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()

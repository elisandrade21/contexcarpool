"""Traffic audit: a logging reverse proxy in front of the ranking service.
Every request the page makes to its own origin is written to out/traffic_audit/requests.jsonl
(method, path, body). Requests to other origins (map tiles) are not seen here; the page lists them itself
through the Resource Timing API (see the audit notes).
Usage: python3 traffic_proxy.py <listen port> <service port>"""
import http.server, json, os, sys, time, urllib.request

LISTEN, TARGET = int(sys.argv[1]), int(sys.argv[2])
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "traffic_audit")
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "requests.jsonl"), "a")

class H(http.server.BaseHTTPRequestHandler):
    def _go(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        LOG.write(json.dumps({"t": time.time(), "method": self.command, "path": self.path,
                              "body": body.decode("utf-8", "replace")}) + "\n"); LOG.flush()
        req = urllib.request.Request(f"http://127.0.0.1:{TARGET}{self.path}", data=body or None, method=self.command,
                                     headers={k: v for k, v in self.headers.items() if k.lower() in ("content-type",)})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data, code, ctype = r.read(), r.status, r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            data, code, ctype = e.read(), e.code, e.headers.get("Content-Type", "")
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)
    do_GET = do_POST = _go
    def log_message(self, *a): pass

http.server.ThreadingHTTPServer(("127.0.0.1", LISTEN), H).serve_forever()

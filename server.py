"""Minimal HTTP server: static files + two API endpoints."""
import json, os
from http.server import HTTPServer, SimpleHTTPRequestHandler

from astro import tonight
from nudge import make_nudge

# --- Config ---
LAT = 12.9716
LON = 77.5946
TZ_HOURS = 5.5
MODEL = "gemma3:1b"
PORT = 8000

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/api/tonight":
            self._json_response(tonight(LAT, LON, tz_hours=TZ_HOURS))
        elif self.path == "/api/nudge":
            data = tonight(LAT, LON, tz_hours=TZ_HOURS)
            text = make_nudge(data, model=MODEL)
            self._json_response({"text": text})
        else:
            super().do_GET()

    def _json_response(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


if __name__ == "__main__":
    os.makedirs(STATIC_DIR, exist_ok=True)
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Look Up running at http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

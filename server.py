"""Minimal HTTP server: static files + two API endpoints."""
import json, math, os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from astro import tonight
from nudge import make_nudge

# --- Config ---
LAT = 12.9716
LON = 77.5946
MODEL = "gemma3:1b"
PORT = 8000

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _parse_lat_lon(qs):
    """Parse and validate lat/lon query parameters.
    Returns (lat, lon, None) on success or (None, None, error_msg) on failure.
    If neither is supplied, returns default (LAT, LON, None).
    """
    has_lat = "lat" in qs
    has_lon = "lon" in qs
    if not has_lat and not has_lon:
        return LAT, LON, None
    if not (has_lat and has_lon):
        return None, None, "Both lat and lon parameters are required"

    try:
        lat = float(qs["lat"][0])
        lon = float(qs["lon"][0])
    except (ValueError, IndexError):
        return None, None, "lat and lon must be numbers"

    if math.isnan(lat) or math.isinf(lat) or not (-90.0 <= lat <= 90.0):
        return None, None, "lat must be between -90 and 90"
    if math.isnan(lon) or math.isinf(lon) or not (-180.0 <= lon <= 180.0):
        return None, None, "lon must be between -180 and 180"

    return lat, lon, None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/tonight":
            lat, lon, err = _parse_lat_lon(qs)
            if err:
                self._error_response(400, err)
                return
            self._json_response(tonight(lat, lon))
        elif parsed.path == "/api/nudge":
            lat, lon, err = _parse_lat_lon(qs)
            if err:
                self._error_response(400, err)
                return
            data = tonight(lat, lon)
            text = make_nudge(data, model=MODEL)
            self._json_response({"text": text})
        else:
            super().do_GET()

    def _json_response(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error_response(self, status, message):
        self._json_response({"error": message}, status=status)

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

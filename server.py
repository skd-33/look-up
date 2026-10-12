"""Minimal HTTP server: static files + API endpoints."""
import json, math, os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from astro import tonight
from nudge import make_nudge, make_reflection

# --- Config ---
LAT = 12.9716
LON = 77.5946
MODEL = "qwen2.5:1.5b"
PORT = 8000

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
VALID_TONES = {"calm", "excited", "poetic"}


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
            tone = qs.get("tone", ["calm"])[0].lower()
            if tone not in VALID_TONES:
                tone = "calm"
            data = tonight(lat, lon)
            text = make_nudge(data, model=MODEL, tone=tone)
            self._json_response({"text": text})
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/reflect":
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw_body)
            except (ValueError, json.JSONDecodeError):
                self._error_response(400, "Invalid JSON body")
                return

            user_text = payload.get("text", "")
            lat = payload.get("lat", LAT)
            lon = payload.get("lon", LON)
            tone = payload.get("tone", "calm")
            if tone not in VALID_TONES:
                tone = "calm"

            try:
                lat = float(lat)
                lon = float(lon)
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    lat, lon = LAT, LON
            except (ValueError, TypeError):
                lat, lon = LAT, LON

            data = tonight(lat, lon)
            reply = make_reflection(user_text, data, model=MODEL, tone=tone)
            self._json_response({"response": reply})
        else:
            self._error_response(404, "Not Found")

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

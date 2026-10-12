"""Minimal HTTP server: static files + API endpoints. Stdlib only."""
import json, math, os, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from astro import tonight
from nudge import (make_nudge, make_nudge_stream, make_reflection,
                   make_ask, make_ask_stream, make_journal_entry, warmup,
                   MODEL as DEFAULT_MODEL)

# --- Config ---
LAT = 12.9716
LON = 77.5946
PORT = 8000

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
VALID_TONES = {"calm", "excited", "poetic"}

# Server-wide active model (mutable)
_active_model = DEFAULT_MODEL
_model_lock = threading.Lock()


def get_model():
    with _model_lock:
        return _active_model


def set_model(m):
    global _active_model
    with _model_lock:
        _active_model = m


def _parse_lat_lon(qs):
    """Parse and validate lat/lon query parameters."""
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


def _read_json_body(handler, max_len=4096):
    """Read and parse JSON body from a POST request."""
    try:
        length = int(handler.headers.get("Content-Length", 0))
        if length > max_len:
            return None, "Request body too large"
        raw = handler.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw), None
    except (ValueError, json.JSONDecodeError):
        return None, "Invalid JSON body"


def _fetch_ollama_models():
    """Fetch installed models from Ollama."""
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = []
            for m in data.get("models", []):
                name = m.get("name", "")
                if name:
                    models.append(name)
            return models
    except Exception:
        return []


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
            stream = qs.get("stream", ["0"])[0] == "1"
            data = tonight(lat, lon)
            model = get_model()

            if stream:
                self._stream_response(make_nudge_stream(data, model=model, tone=tone))
            else:
                text = make_nudge(data, model=model, tone=tone)
                self._json_response({"text": text, "model": model})

        elif parsed.path == "/api/models":
            models = _fetch_ollama_models()
            self._json_response({"models": models, "active": get_model()})

        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/reflect":
            payload, err = _read_json_body(self)
            if err:
                self._error_response(400, err)
                return
            user_text = payload.get("text", "")
            lat = payload.get("lat", LAT)
            lon = payload.get("lon", LON)
            tone = payload.get("tone", "calm")
            if tone not in VALID_TONES:
                tone = "calm"
            try:
                lat, lon = float(lat), float(lon)
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    lat, lon = LAT, LON
            except (ValueError, TypeError):
                lat, lon = LAT, LON

            data = tonight(lat, lon)
            model = get_model()

            # Generate journal entry
            target = None
            from nudge import pick_target
            target = pick_target(data)
            target_facts = {}
            if target:
                target_facts = {
                    "name": target["name"],
                    "direction": target.get("direction", ""),
                    "best_time": target.get("best_time", ""),
                    "appearance": target.get("appearance", ""),
                    "natural_position": target.get("natural_position", ""),
                }

            reply = make_reflection(user_text, data, model=model, tone=tone)
            journal = make_journal_entry(user_text, target_facts, model=model)
            self._json_response({
                "response": reply,
                "journal": journal,
                "object": target["name"] if target else "",
                "model": model,
            })

        elif parsed.path == "/api/ask":
            payload, err = _read_json_body(self)
            if err:
                self._error_response(400, err)
                return
            question = (payload.get("question", "") or "")[:200]
            lat = payload.get("lat", LAT)
            lon = payload.get("lon", LON)
            stream = payload.get("stream", False)
            try:
                lat, lon = float(lat), float(lon)
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    lat, lon = LAT, LON
            except (ValueError, TypeError):
                lat, lon = LAT, LON

            data = tonight(lat, lon)
            model = get_model()

            if stream:
                self._stream_response(make_ask_stream(question, data, model=model, timeout=15))
            else:
                answer = make_ask(question, data, model=model, timeout=15)
                self._json_response({"answer": answer, "model": model})

        elif parsed.path == "/api/set-model":
            payload, err = _read_json_body(self)
            if err:
                self._error_response(400, err)
                return
            model_name = payload.get("model", "")
            if not model_name:
                self._error_response(400, "model is required")
                return
            set_model(model_name)
            self._json_response({"active": get_model()})

        else:
            self._error_response(404, "Not Found")

    def _json_response(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_response(self, generator):
        """Stream text chunks without Content-Length for typing effect."""
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for chunk in generator:
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _error_response(self, status, message):
        self._json_response({"error": message}, status=status)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


if __name__ == "__main__":
    os.makedirs(STATIC_DIR, exist_ok=True)

    # Warm up the model in a background thread
    def _warmup():
        model = get_model()
        print(f"[warmup] Sending warmup request to {model}...")
        ok = warmup(model)
        if ok:
            print(f"[warmup] {model} is warm and ready.")
        else:
            print(f"[warmup] Could not reach Ollama. Nudges will use template fallback.")

    t = threading.Thread(target=_warmup, daemon=True)
    t.start()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Look Up running at http://127.0.0.1:{PORT}")
    print(f"Active model: {get_model()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

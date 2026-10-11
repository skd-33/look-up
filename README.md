# Look Up

An offline stargazing companion that tells you what to look at tonight.

## Setup

```sh
pip install -r requirements.txt
python setup.py          # downloads de421.bsp if missing
```

## Run

```sh
python server.py
# open http://127.0.0.1:8000
```

Needs [Ollama](https://ollama.com) running locally with `gemma3:1b` for
AI-written nudges. Works without it — a template sentence fills in.

Edit `LAT`, `LON`, `TZ_HOURS` at the top of `server.py` for your location.

## Architecture

```
setup.py           download de421.bsp (only network script)
astro.py           tonight(lat, lon) -> planets, moon, sun times
nudge.py           make_nudge(data) -> short text via Ollama
server.py          stdlib http.server, /api/tonight, /api/nudge
static/index.html  one-file frontend, inline CSS + JS + SVG
```

- **Backend**: Python stdlib `http.server`, Skyfield with local
  `de421.bsp`, `load.timescale(builtin=True)`. Zero runtime network calls.
- **LLM**: Ollama POST to `localhost:11434`, 15 s timeout, template fallback.
- **Frontend**: single HTML file, no build step, no CDN, no external URLs.
  Layered SVG scene with parallax, CSS star twinkle, 20-min go-outside timer.
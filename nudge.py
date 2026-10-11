"""Generate a short stargazing nudge via local Ollama, with fallback."""
import json, urllib.request, urllib.error

OLLAMA_URL = "http://localhost:11434/api/generate"

SYSTEM_PROMPT = (
    "You are a friendly stargazing friend. Write 2-3 short sentences in plain words, "
    "first person, warm tone. Name the single most striking visible object, say where "
    "to look and when, and gently invite the person outside. Use ONLY the facts given "
    "in the JSON. Never invent times or positions."
)


def _pick_best(data):
    """Choose the most striking visible object from the data."""
    visible = [o for o in data.get("objects", []) if o.get("visible")]
    if not visible:
        return None
    # Prefer lowest (brightest) magnitude
    return min(visible, key=lambda o: o.get("magnitude", 99))


def _fallback(data):
    """Plain template sentence when Ollama is unavailable."""
    best = _pick_best(data)
    if not best:
        return "The sky is mostly quiet tonight. Still, step outside and breathe in the dark."
    return (
        f"{best['name']} is up tonight at about {best['altitude']}° in the {best['direction']}. "
        f"Best around {best['best_time']}. Worth a look — grab a jacket and head out."
    )


def make_nudge(data, model="gemma3:1b", timeout=15):
    """Call Ollama to generate a nudge. Falls back to template on failure."""
    best = _pick_best(data)
    if not best:
        return _fallback(data)

    user_msg = f"Tonight's sky data: {json.dumps(data, indent=None)}"
    payload = json.dumps({
        "model": model,
        "prompt": user_msg,
        "system": SYSTEM_PROMPT,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            text = body.get("response", "").strip()
            if text:
                return text
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    return _fallback(data)


if __name__ == "__main__":
    from astro import tonight
    sky = tonight(12.9716, 77.5946, tz_hours=5.5)
    print("=== Sky data ===")
    print(json.dumps(sky, indent=2))
    print("\n=== Nudge ===")
    print(make_nudge(sky))

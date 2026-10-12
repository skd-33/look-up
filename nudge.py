"""Generate natural stargazing nudges and reflections via local Qwen 2.5 1.5B, with strict fact control and validation."""
import json, urllib.request, urllib.error

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:1.5b"

TONE_GUIDES = {
    "calm": "warm, quiet, and inviting",
    "excited": "enthusiastic and wonder-filled",
    "poetic": "lyrical, reflective, and contemplative",
}

ALL_PLANETS = ["venus", "mars", "jupiter", "saturn", "moon"]
ROBOTIC_PHRASES = ["here is", "here's", "as an", "as a", "i will", "hello there", "in the direction", "at an altitude of"]


def _clean_text(text):
    if not text:
        return ""
    # Strip emojis and non-standard symbols
    cleaned = "".join(
        ch for ch in text
        if ord(ch) < 0x2600 or (0x2800 <= ord(ch) < 0x1F000)
    ).strip()
    # Strip wrapping quotes if LLM added them
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def pick_target(data):
    """Pick the single most striking visible object."""
    visible = [o for o in data.get("objects", []) if o.get("visible")]
    if not visible:
        return None
    return min(visible, key=lambda o: o.get("magnitude", 99))


def _fallback_nudge(target, tone="calm"):
    if not target:
        return "The night sky is mostly quiet tonight. Still, step outside, look up, and breathe in the dark."

    name = target["name"]
    pos = target.get("natural_position", f"in the {target.get('direction', 'eastern')} sky")

    if tone == "excited":
        return f"Look up tonight—{name} is shining {pos}! Step outside and take in its brilliant glow."
    elif tone == "poetic":
        return f"{name} rests quietly {pos} tonight. Step into the dark and let its gentle light find you."
    else:
        return f"{name} is {pos} tonight. Step outside and see if you can spot its steady light."


def _validate_nudge(text, target):
    """Validate that model output contains target object, is concise, and doesn't hallucinate."""
    if not text or len(text) < 20 or len(text) > 260:
        return False
    lower = text.lower()

    if target:
        # Must mention the target
        if target["name"].lower() not in lower:
            return False
        # Must NOT mention any other planet
        for p in ALL_PLANETS:
            if p != target["name"].lower() and p in lower:
                return False

    # Check for robotic/awkward template phrases
    for phrase in ROBOTIC_PHRASES:
        if phrase in lower:
            return False

    return True


def make_nudge(data, model=MODEL, tone="calm", timeout=12):
    """Generate 1-2 natural sentences via Qwen 2.5 1.5B with verified facts."""
    target = pick_target(data)
    fallback = _fallback_nudge(target, tone)

    if not target:
        return fallback

    guide = TONE_GUIDES.get(tone.lower(), TONE_GUIDES["calm"])
    target_name = target["name"]
    pos = target.get("natural_position", f"in the {target.get('direction', 'eastern')} sky")
    time_phrase = target.get("natural_time", target.get("best_time", "tonight"))
    appearance = target.get("appearance", "a steady celestial light")

    prompt = f"""You are a stargazing companion. Write 1 or 2 short, natural sentences in spoken English inviting someone outside tonight.
The tone should be {guide}.

Facts:
- Target: {target_name}
- Where: {pos}
- When: {time_phrase}
- What to look for: {appearance}

Rules:
- 1 or 2 sentences ONLY.
- Natural, spoken English (example: "{target_name} is {pos} tonight. Step outside and see if you can spot its steady light.").
- No robotic introductions like "Here's your nudge", "I think", or "The {target_name}".
- No emojis.
- Only mention {target_name}. Do not mention any other planet or star.
"""

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.5,
            "top_p": 0.9,
        },
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            raw_text = body.get("response", "")
            text = _clean_text(raw_text)
            if _validate_nudge(text, target):
                return text
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    return fallback


def make_reflection(user_text, data, model=MODEL, tone="calm", timeout=12):
    """Reply to user's observation with 1-2 encouraging sentences based only on facts."""
    target = pick_target(data)
    warm_fallback = "Thank you for stepping outside tonight. Even a quiet glance at the sky stays with you."

    if not user_text or not user_text.strip():
        return warm_fallback

    guide = TONE_GUIDES.get(tone.lower(), TONE_GUIDES["calm"])
    target_name = target["name"] if target else "the night sky"
    appearance = target.get("appearance", "steady light") if target else "quiet stars"
    pos = target.get("natural_position", "overhead") if target else "the sky"

    prompt = f"""The person just spent time stargazing outside and shared what they observed:
"{user_text.strip()}"

Verified facts about tonight's sky:
- Main object: {target_name} ({appearance}, {pos})

Reply in 1 or 2 warm, encouraging sentences in a {guide} voice.
Rules:
- 1 or 2 sentences ONLY.
- Never state anything about the sky that contradicts or goes beyond the verified facts.
- If they saw clouds or missed it, validate their effort warmly.
- No emojis. Plain text only.
"""

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.6,
            "top_p": 0.9,
        },
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            raw_text = body.get("response", "")
            text = _clean_text(raw_text)
            if text and len(text) > 10 and len(text) < 280:
                return text
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    return warm_fallback


if __name__ == "__main__":
    from astro import tonight
    sky = tonight(12.9716, 77.5946)
    print("=== Nudge (Calm) ===")
    print(make_nudge(sky, tone="calm"))
    print("\n=== Nudge (Excited) ===")
    print(make_nudge(sky, tone="excited"))
    print("\n=== Nudge (Poetic) ===")
    print(make_nudge(sky, tone="poetic"))
    print("\n=== Reflection ===")
    print(make_reflection("I stepped outside and saw a bright light in the east", sky, tone="calm"))

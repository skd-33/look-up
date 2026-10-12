"""Generate natural stargazing nudges and reflections via local LLM, with strict fact control and validation."""
import json, os, urllib.request, urllib.error

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = os.environ.get("LOOKUP_MODEL", "qwen2.5:1.5b")

TONE_GUIDES = {
    "calm": "warm, quiet, and inviting",
    "excited": "enthusiastic and wonder-filled",
    "poetic": "lyrical, reflective, and contemplative",
}

# Fixed mission lines tied to each object
MISSIONS = {
    "Venus": [
        "See if you can spot it before it sets.",
        "Watch how it outshines everything else in the sky.",
        "Notice how steady its light is compared to the stars.",
    ],
    "Mars": [
        "Look for its reddish tint among the white stars.",
        "See how its colour deepens closer to the horizon.",
        "Try to spot it with your bare eyes first.",
    ],
    "Jupiter": [
        "See if you can spot any faint dots nearby — those are its moons.",
        "Notice how it barely twinkles compared to the stars.",
        "Watch how bright it is even in a light-polluted sky.",
    ],
    "Saturn": [
        "See if you can spot its faint golden glow.",
        "Imagine the rings you can't quite see from here.",
        "Notice how calm and steady its light is.",
    ],
    "Moon": [
        "Look at the terminator line where light meets dark.",
        "See if you can spot the Sea of Tranquility with your eyes.",
        "Notice how the earthshine lights the dark side faintly.",
    ],
}

DEFAULT_MISSIONS = [
    "Step outside and take in its steady light.",
    "Give your eyes a few minutes to adjust, then look again.",
    "See how many other objects you can spot nearby.",
]

ALL_OBJECT_NAMES = ["venus", "mars", "jupiter", "saturn", "moon"]

ROBOTIC_PHRASES = ["here is", "here's", "as an", "as a", "i will", "hello there",
                   "in the direction", "at an altitude of", "certainly", "sure!"]


def _clean_text(text):
    if not text:
        return ""
    cleaned = "".join(
        ch for ch in text
        if ord(ch) < 0x2600 or (0x2800 <= ord(ch) < 0x1F000)
    ).strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def pick_target(data):
    """Pick the single most striking visible object."""
    visible = [o for o in data.get("objects", []) if o.get("visible")]
    if not visible:
        return None
    return min(visible, key=lambda o: o.get("magnitude", 99))


def _pick_mission(target):
    """Pick a mission line from the fixed list for this target."""
    import hashlib
    from datetime import date
    name = target["name"] if target else ""
    missions = MISSIONS.get(name, DEFAULT_MISSIONS)
    # Deterministic but changes daily
    seed = hashlib.md5(f"{name}-{date.today().isoformat()}".encode()).hexdigest()
    idx = int(seed[:8], 16) % len(missions)
    return missions[idx]


def _fallback_nudge(target, tone="calm"):
    if not target:
        return "The night sky is mostly quiet tonight. Still, step outside, look up, and breathe in the dark."

    name = target["name"]
    pos = target.get("natural_position", f"in the {target.get('direction', 'eastern')} sky")
    direction = target.get("direction", "")
    best_time = target.get("best_time", "tonight")
    mission = _pick_mission(target)

    if tone == "excited":
        return f"Look up tonight — {name} is shining {pos}! Best around {best_time}, look {direction}. {mission}"
    elif tone == "poetic":
        return f"{name} rests quietly {pos} tonight, best around {best_time}. Look {direction}. {mission}"
    else:
        return f"{name} is {pos} tonight, best around {best_time}. Look {direction}. {mission}"


def _validate_nudge(text, target):
    """Validate that model output contains target, direction, best time and doesn't hallucinate."""
    if not text or len(text) < 20 or len(text) > 350:
        return False
    lower = text.lower()

    if target:
        # Must mention the target name
        if target["name"].lower() not in lower:
            return False
        # Must mention direction or position
        direction = target.get("direction", "")
        if direction and direction.lower() not in lower:
            # Also accept natural_position mention
            nat_pos = target.get("natural_position", "")
            if nat_pos and not any(word in lower for word in nat_pos.lower().split()[:3]):
                return False
        # Must mention best time
        best_time = target.get("best_time", "")
        if best_time and best_time.lower() not in lower:
            return False
        # Must NOT mention any other planet/object
        for p in ALL_OBJECT_NAMES:
            if p != target["name"].lower() and p in lower:
                return False

    for phrase in ROBOTIC_PHRASES:
        if phrase in lower:
            return False

    return True


def _validate_ask_answer(text, data):
    """Validate that ask answer only references objects in tonight's data."""
    if not text or len(text) < 5:
        return False
    lower = text.lower()
    known_names = set()
    for obj in data.get("objects", []):
        known_names.add(obj["name"].lower())
    # Add star names if present
    for obj in data.get("stars", []):
        known_names.add(obj["name"].lower())
    # Check for hallucinated objects
    phantom_objects = ["mercury", "uranus", "neptune", "pluto"]
    for name in phantom_objects:
        if name in lower and name not in known_names:
            return False
    return True


ASK_FALLBACK = "I only know tonight's sky from the data on this page."


def make_nudge(data, model=None, tone="calm", timeout=12):
    """Generate 2-3 natural sentences via LLM with verified facts."""
    if model is None:
        model = MODEL
    target = pick_target(data)
    fallback = _fallback_nudge(target, tone)

    if not target:
        return fallback

    guide = TONE_GUIDES.get(tone.lower(), TONE_GUIDES["calm"])
    target_name = target["name"]
    pos = target.get("natural_position", f"in the {target.get('direction', 'eastern')} sky")
    time_phrase = target.get("best_time", "tonight")
    direction = target.get("direction", "E")
    appearance = target.get("appearance", "a steady celestial light")
    mission = _pick_mission(target)

    prompt = f"""You are a stargazing companion. Rewrite the following template in 2 or 3 short, natural, spoken-English sentences.
The tone should be {guide}.

Template: "{target_name} is {pos} tonight, best around {time_phrase}. Look {direction}. {mission}"

Facts you MUST include:
- Object name: {target_name}
- Direction: {direction}
- Best time: {time_phrase}
- What to look for: {appearance}

Rules:
- 2 or 3 sentences ONLY.
- Natural, spoken English.
- You MUST mention {target_name}, the direction {direction}, and the time {time_phrase}.
- No robotic introductions like "Here's your nudge" or "Certainly!".
- No emojis.
- Only mention {target_name}. Do not mention any other planet, moon, or star.
"""

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.4,
            "num_predict": 90,
        },
        "keep_alive": "30m",
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


def make_nudge_stream(data, model=None, tone="calm", timeout=15):
    """Generator: yields text chunks from Ollama streaming, then validates at end."""
    if model is None:
        model = MODEL
    target = pick_target(data)
    fallback = _fallback_nudge(target, tone)

    if not target:
        yield fallback
        return

    guide = TONE_GUIDES.get(tone.lower(), TONE_GUIDES["calm"])
    target_name = target["name"]
    pos = target.get("natural_position", f"in the {target.get('direction', 'eastern')} sky")
    time_phrase = target.get("best_time", "tonight")
    direction = target.get("direction", "E")
    appearance = target.get("appearance", "a steady celestial light")
    mission = _pick_mission(target)

    prompt = f"""You are a stargazing companion. Rewrite the following template in 2 or 3 short, natural, spoken-English sentences.
The tone should be {guide}.

Template: "{target_name} is {pos} tonight, best around {time_phrase}. Look {direction}. {mission}"

Facts you MUST include:
- Object name: {target_name}
- Direction: {direction}
- Best time: {time_phrase}
- What to look for: {appearance}

Rules:
- 2 or 3 sentences ONLY.
- Natural, spoken English.
- You MUST mention {target_name}, the direction {direction}, and the time {time_phrase}.
- No robotic introductions like "Here's your nudge" or "Certainly!".
- No emojis.
- Only mention {target_name}. Do not mention any other planet, moon, or star.
"""

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.4,
            "num_predict": 90,
        },
        "keep_alive": "30m",
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    full_text = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                if token:
                    full_text += token
                    yield token
                if chunk.get("done"):
                    break
    except (urllib.error.URLError, TimeoutError, OSError):
        if not full_text:
            yield fallback
            return

    # Post-stream validation
    cleaned = _clean_text(full_text)
    if not _validate_nudge(cleaned, target):
        yield "\n__REPLACE__" + fallback


def make_ask(question, data, model=None, timeout=15):
    """Answer a user question using only tonight's sky data."""
    if model is None:
        model = MODEL
    if not question or len(question.strip()) == 0:
        return ASK_FALLBACK

    tonight_json = json.dumps({
        "objects": data.get("objects", []),
        "stars": data.get("stars", []),
        "sunset": data.get("sunset"),
        "sunrise": data.get("sunrise"),
        "date": data.get("date"),
    }, indent=2)

    prompt = f"""You are a stargazing assistant. Answer the user's question using ONLY the sky data below. 
If the answer is not in the data, say exactly: "I only know tonight's sky from the data on this page."

Tonight's sky data:
{tonight_json}

User's question: {question.strip()[:200]}

Rules:
- At most 3 sentences.
- Only mention objects in the data. Do not invent objects not listed.
- Plain text, no emojis, no markdown.
"""

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 90,
        },
        "keep_alive": "30m",
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
            if text and _validate_ask_answer(text, data):
                return text
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    return ASK_FALLBACK


def make_ask_stream(question, data, model=None, timeout=15):
    """Generator: stream answer to a user question."""
    if model is None:
        model = MODEL
    if not question or len(question.strip()) == 0:
        yield ASK_FALLBACK
        return

    tonight_json = json.dumps({
        "objects": data.get("objects", []),
        "stars": data.get("stars", []),
        "sunset": data.get("sunset"),
        "sunrise": data.get("sunrise"),
        "date": data.get("date"),
    }, indent=2)

    prompt = f"""You are a stargazing assistant. Answer the user's question using ONLY the sky data below. 
If the answer is not in the data, say exactly: "I only know tonight's sky from the data on this page."

Tonight's sky data:
{tonight_json}

User's question: {question.strip()[:200]}

Rules:
- At most 3 sentences.
- Only mention objects in the data. Do not invent objects not listed.
- Plain text, no emojis, no markdown.
"""

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.3,
            "num_predict": 90,
        },
        "keep_alive": "30m",
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    full_text = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                if token:
                    full_text += token
                    yield token
                if chunk.get("done"):
                    break
    except (urllib.error.URLError, TimeoutError, OSError):
        if not full_text:
            yield ASK_FALLBACK
            return

    # Post-stream validation
    cleaned = _clean_text(full_text)
    if not _validate_ask_answer(cleaned, data):
        yield "\n__REPLACE__" + ASK_FALLBACK


def make_reflection(user_text, data, model=None, tone="calm", timeout=12):
    """Reply to user's observation with 1-2 encouraging sentences based only on facts."""
    if model is None:
        model = MODEL
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
            "temperature": 0.4,
            "num_predict": 90,
        },
        "keep_alive": "30m",
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


def make_journal_entry(user_text, target_facts, model=None, timeout=12):
    """Create a 2-3 line first-person journal entry from user's words and target facts."""
    if model is None:
        model = MODEL
    fallback = f"I stepped outside tonight. {user_text.strip()[:200]}"

    prompt = f"""Write a 2-3 line first-person journal entry for a stargazer. Use ONLY the observer's own words and the facts below.

Observer said: "{user_text.strip()[:200]}"

Facts:
{json.dumps(target_facts, indent=2)}

Rules:
- First person ("I saw...", "Tonight I...").
- 2-3 sentences ONLY.
- Use only the observer's words and the given facts. Do not invent details.
- Plain text, no emojis, no markdown.
"""

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.4,
            "num_predict": 90,
        },
        "keep_alive": "30m",
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
            if text and len(text) > 10 and len(text) < 400:
                return text
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    return fallback


def warmup(model=None):
    """Send a short warmup request to Ollama to keep the model loaded."""
    if model is None:
        model = MODEL
    payload = json.dumps({
        "model": model,
        "prompt": "Hi",
        "stream": False,
        "options": {"num_predict": 1},
        "keep_alive": "30m",
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    from astro import tonight
    sky = tonight(12.9716, 77.5946)
    print("=== Nudge (Calm) ===")
    print(make_nudge(sky, tone="calm"))
    print("\n=== Nudge (Excited) ===")
    print(make_nudge(sky, tone="excited"))
    print("\n=== Nudge (Poetic) ===")
    print(make_nudge(sky, tone="poetic"))
    print("\n=== Ask ===")
    print(make_ask("What's the brightest thing tonight?", sky))
    print("\n=== Reflection ===")
    print(make_reflection("I stepped outside and saw a bright light in the east", sky, tone="calm"))

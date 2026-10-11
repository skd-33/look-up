"""Generate stargazing nudges and reflections via local Ollama, with validation and fallback."""
import json, urllib.request, urllib.error

OLLAMA_URL = "http://localhost:11434/api/generate"

TONE_STYLES = {
    "calm": "You are a calm, grounded stargazing companion with a gentle, serene voice.",
    "excited": "You are an enthusiastic stargazing companion who loves the wonder of the cosmos with vibrant energy.",
    "poetic": "You are a reflective, contemplative stargazing companion with a lyrical, evocative voice.",
}

MISSIONS = {
    "Venus": "Look toward {direction} around {best_time} at {altitude}° altitude for a brilliant beacon that doesn't flicker. Give your eyes 10 minutes to adjust to the dusk.",
    "Mars": "Look toward {direction} around {best_time} at {altitude}° altitude for its distinctive warm amber glow. Give your eyes 10 minutes to let your dark vision sharpen.",
    "Jupiter": "Look toward {direction} around {best_time} at {altitude}° altitude for a steady cream-colored jewel brighter than nearby stars. Give your eyes 10 minutes to take in its light.",
    "Saturn": "Look toward {direction} around {best_time} at {altitude}° altitude for a quiet golden-yellow ember. Allow your eyes about 10 minutes to adjust to the dark.",
    "Moon": "Look toward {direction} for the {phase} ({illumination}% illuminated) around {best_time} at {altitude}° altitude. Give your eyes 10 minutes to adapt.",
    "Quiet Sky": "Step outside into the dark away from screens, give your eyes 10 to 15 minutes to adjust, and watch for faint drifting stars.",
}

ALL_PLANET_NAMES = ["Venus", "Mars", "Jupiter", "Saturn", "Moon"]


def pick_target_and_mission(data):
    """Pick the single most striking visible object and format its mission line."""
    visible = [o for o in data.get("objects", []) if o.get("visible")]
    if not visible:
        return None, MISSIONS["Quiet Sky"]

    best = min(visible, key=lambda o: o.get("magnitude", 99))
    template = MISSIONS.get(best["name"], MISSIONS["Quiet Sky"])
    mission = template.format(
        direction=best.get("direction", "the sky"),
        best_time=best.get("best_time", "tonight"),
        altitude=best.get("altitude", 30),
        phase=best.get("phase", "crescent"),
        illumination=best.get("illumination", 50),
    )
    return best, mission


def _fallback_nudge(best, mission):
    if not best:
        return f"The night sky is quiet tonight. {mission}"
    return (
        f"{best['name']} is visible tonight at about {best['altitude']}° in the {best['direction']}, "
        f"best around {best['best_time']}. {mission} Step outside and look up."
    )


def _validate_nudge(text, best):
    """Validate that model output contains target object and does not hallucinate non-visible bodies."""
    if not text or len(text) < 20:
        return False
    lower = text.lower()
    if best:
        if best["name"].lower() not in lower:
            return False
        for name in ALL_PLANET_NAMES:
            if name != best["name"] and name.lower() in lower:
                return False
    return True


def _clean_text(text):
    if not text:
        return ""
    # Strip emojis and non-standard symbols
    return "".join(
        ch for ch in text
        if ord(ch) < 0x2600 or (0x2800 <= ord(ch) < 0x1F000)
    ).strip()


def make_nudge(data, model="gemma3:1b", tone="calm", timeout=15):
    """Generate rewritten nudge and mission via Ollama with strict fact control and validation."""
    best, mission = pick_target_and_mission(data)
    fallback = _fallback_nudge(best, mission)

    style = TONE_STYLES.get(tone.lower(), TONE_STYLES["calm"])
    system_prompt = (
        f"{style} "
        "Write 2-3 short sentences in plain words, first person, warm tone. No emojis. "
        "Name the single visible object, say where to look and when, and describe the mission. "
        "Use ONLY the facts given below. Never invent times, directions, or objects not in the facts."
    )

    facts = {
        "visible_target": best["name"] if best else "None",
        "direction": best.get("direction") if best else None,
        "altitude_degrees": best.get("altitude") if best else None,
        "best_time": best.get("best_time") if best else None,
        "mission_line": mission,
    }

    payload = json.dumps({
        "model": model,
        "prompt": f"Facts to rewrite:\n{json.dumps(facts, indent=2)}",
        "system": system_prompt,
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
            text = _clean_text(body.get("response", ""))
            if _validate_nudge(text, best):
                return text
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    return fallback


def make_reflection(user_text, data, model="gemma3:1b", tone="calm", timeout=15):
    """Reply to user's observation with 1-2 encouraging sentences based only on facts."""
    best, mission = pick_target_and_mission(data)
    warm_fallback = "Thank you for stepping outside tonight. Even a quiet glance at the sky stays with you."

    if not user_text or not user_text.strip():
        return warm_fallback

    style = TONE_STYLES.get(tone.lower(), TONE_STYLES["calm"])
    system_prompt = (
        f"{style} "
        "The person just returned from stargazing and shared what they saw. "
        "Reply in 1-2 warm, encouraging sentences. No emojis. "
        "Use ONLY the facts provided about the sky. Never state anything about the sky that is not in the facts."
    )

    facts = {
        "user_observed": user_text.strip(),
        "target_object": best["name"] if best else "open sky",
        "direction": best.get("direction") if best else "overhead",
        "altitude": best.get("altitude") if best else 45,
    }

    payload = json.dumps({
        "model": model,
        "prompt": f"Observation:\n{json.dumps(facts, indent=2)}",
        "system": system_prompt,
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
            text = _clean_text(body.get("response", ""))
            if text and len(text) > 10:
                return text
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    return warm_fallback


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from astro import tonight
    sky = tonight(12.9716, 77.5946)
    print("=== Target & Mission ===")
    t, m = pick_target_and_mission(sky)
    print("Target:", t["name"] if t else None)
    print("Mission:", m)
    print("\n=== Nudge (Calm) ===")
    print(make_nudge(sky, tone="calm"))
    print("\n=== Reflection Test ===")
    print(make_reflection("I saw a steady white light near the east horizon", sky, tone="calm"))

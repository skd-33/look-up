"""Compute tonight's visible sky objects using local de421.bsp only."""
import os, math
from datetime import datetime, timedelta, timezone, tzinfo

from skyfield.api import Loader, Star, wgs84
from skyfield.almanac import find_discrete, sunrise_sunset

DIR = os.path.dirname(os.path.abspath(__file__))

BODIES = {
    "Venus": {
        "id": "venus",
        "base_mag": -4.4,
        "appearance": "a brilliant, steady diamond-like light",
    },
    "Mars": {
        "id": "mars",
        "base_mag": 1.0,
        "appearance": "a warm, reddish-orange ember",
    },
    "Jupiter": {
        "id": "jupiter barycenter",
        "base_mag": -2.5,
        "appearance": "a brilliant, steady cream-colored light",
    },
    "Saturn": {
        "id": "saturn barycenter",
        "base_mag": 0.5,
        "appearance": "a gentle, golden-yellow ember",
    },
    "Moon": {
        "id": "moon",
        "base_mag": -12.0,
        "appearance": "the silver glow of the moon",
    },
}

MOON_PHASES = [
    "New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
    "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent",
]

COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


class _FixedOffset(tzinfo):
    def __init__(self, hours):
        self._offset = timedelta(hours=hours)
        self._name = f"UTC{'+' if hours >= 0 else ''}{hours}"
    def utcoffset(self, dt):
        return self._offset
    def tzname(self, dt):
        return self._name
    def dst(self, dt):
        return timedelta(0)


def _compass(az_deg):
    idx = int((az_deg + 11.25) / 22.5) % 16
    return COMPASS[idx]


def _natural_position(alt, az):
    comp = _compass(az)
    comp_map = {
        "N": "northern", "NNE": "north-northeastern", "NE": "northeastern", "ENE": "east-northeastern",
        "E": "eastern", "ESE": "east-southeastern", "SE": "southeastern", "SSE": "south-southeastern",
        "S": "southern", "SSW": "south-southwestern", "SW": "southwestern", "WSW": "west-southwestern",
        "W": "western", "WNW": "west-northwestern", "NW": "northwestern", "NNW": "north-northwestern",
    }
    dir_name = comp_map.get(comp, "eastern")
    if alt >= 70:
        return f"high overhead in the {dir_name} sky"
    elif alt >= 35:
        return f"high in the {dir_name} sky"
    elif alt >= 15:
        return f"mid-way up in the {dir_name} sky"
    else:
        return f"low in the {dir_name} sky"


def _natural_time(dt):
    h = dt.hour
    if h in (23, 0, 1):
        return "around midnight"
    elif 4 <= h <= 6:
        return f"before dawn (around {dt.strftime('%I:%M %p').lstrip('0')})"
    elif 18 <= h <= 21:
        return f"in the evening (around {dt.strftime('%I:%M %p').lstrip('0')})"
    else:
        return f"around {dt.strftime('%I:%M %p').lstrip('0')}"


def _moon_phase(elongation_deg):
    """Return phase name and illumination % from Sun-Earth-Moon elongation."""
    illum = (1 - math.cos(math.radians(elongation_deg))) / 2 * 100
    idx = int((elongation_deg + 22.5) / 45) % 8
    return MOON_PHASES[idx], round(illum, 1)


def tonight(lat, lon, tz_hours=None):
    """Return dict of tonight's sky for a given location using local de421.bsp."""
    load = Loader(DIR)
    ts = load.timescale(builtin=True)
    eph = load("de421.bsp")

    earth = eph["earth"]
    sun_body = eph["sun"]

    if tz_hours is not None:
        tz = _FixedOffset(tz_hours)
    else:
        tz = datetime.now().astimezone().tzinfo

    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now(tz)
    today = now_local.date()

    # Search window: sunset to next sunrise
    # If opened after midnight (e.g. before 6am), the night started yesterday evening
    if now_local.hour < 6:
        ref_date = today - timedelta(days=1)
    else:
        ref_date = today

    start_local = datetime(ref_date.year, ref_date.month, ref_date.day, 16, 0, tzinfo=tz)
    end_local = start_local + timedelta(hours=15)  # covers until 7am next morning

    t0 = ts.from_datetime(start_local)
    t1 = ts.from_datetime(end_local)
    t_now = ts.from_datetime(now_utc)

    observer = earth + wgs84.latlon(lat, lon)

    # Sun rise/set across full night window
    f = sunrise_sunset(eph, wgs84.latlon(lat, lon))
    times, events = find_discrete(t0, t1, f)
    sunset_str = sunrise_str = None
    for t_ev, ev in zip(times, events):
        local = t_ev.utc_datetime().astimezone(tz)
        if ev == 0 and sunset_str is None:
            sunset_str = local.strftime("%I:%M %p")
        elif ev == 1 and sunrise_str is None:
            sunrise_str = local.strftime("%I:%M %p")

    # Step through night window in 10-min increments
    steps = 90
    t_steps = ts.linspace(t0, t1, steps + 1)

    objects = []

    for name, info in BODIES.items():
        body = eph[info["id"]]

        # Current position right now
        now_app = observer.at(t_now).observe(body).apparent()
        now_alt_deg, now_az_deg, _ = now_app.altaz()
        now_alt = now_alt_deg.degrees
        now_az = now_az_deg.degrees

        best_alt = -90
        best_time = None
        best_az = 0

        for t_step in t_steps:
            sun_app = observer.at(t_step).observe(sun_body).apparent()
            if sun_app.altaz()[0].degrees > -6:
                continue

            app = observer.at(t_step).observe(body).apparent()
            alt_deg, az_deg, _ = app.altaz()
            alt_val = alt_deg.degrees
            az_val = az_deg.degrees

            if alt_val > 10 and alt_val > best_alt:
                best_alt = alt_val
                best_az = az_val
                best_time = t_step

        # Fine-tune best_time to nearest minute within +/- 15 min window
        if best_time is not None:
            best_dt = best_time.utc_datetime()
            refine_start = ts.from_datetime(best_dt - timedelta(minutes=15))
            refine_end = ts.from_datetime(best_dt + timedelta(minutes=15))
            for t_fine in ts.linspace(refine_start, refine_end, 31):
                sun_alt = observer.at(t_fine).observe(sun_body).apparent().altaz()[0].degrees
                if sun_alt > -6:
                    continue
                alt_deg, az_deg, _ = observer.at(t_fine).observe(body).apparent().altaz()
                if alt_deg.degrees > best_alt:
                    best_alt = alt_deg.degrees
                    best_az = az_deg.degrees
                    best_time = t_fine

        visible = bool((best_alt > 10) and (best_time is not None))

        obj = {
            "name": name,
            "visible": visible,
            "magnitude": float(info["base_mag"]),
            "current_altitude": round(float(now_alt), 1),
            "current_azimuth": round(float(now_az), 1),
            "current_direction": _compass(now_az),
            "is_up_now": bool(now_alt > 0),
            "appearance": info["appearance"],
        }

        if visible:
            local_best = best_time.utc_datetime().astimezone(tz)
            delta = (best_time.utc_datetime() - now_utc).total_seconds() / 60
            obj["best_time"] = local_best.strftime("%I:%M %p")
            obj["direction"] = _compass(best_az)
            obj["altitude"] = round(float(best_alt), 1)
            obj["azimuth"] = round(float(best_az), 1)
            obj["minutes_to_peak"] = int(round(delta))
            obj["natural_position"] = _natural_position(best_alt, best_az)
            obj["natural_time"] = _natural_time(local_best)

        if name == "Moon":
            moon_app = observer.at(t_now).observe(body).apparent()
            sun_app = observer.at(t_now).observe(sun_body).apparent()
            elong = moon_app.separation_from(sun_app).degrees
            phase_name, illum = _moon_phase(elong)
            obj["phase"] = phase_name
            obj["illumination"] = illum

        objects.append(obj)

    # Window minutes: until the single best-visible object peaks
    visible_objects = [o for o in objects if o.get("visible")]
    best_visible_target = min(visible_objects, key=lambda o: o.get("magnitude", 99)) if visible_objects else None
    window_mins = best_visible_target.get("minutes_to_peak") if best_visible_target else None

    return {
        "date": now_local.strftime("%a %d %b, %I:%M %p"),
        "sunset": sunset_str,
        "sunrise": sunrise_str,
        "objects": objects,
        "window_minutes": window_mins,
    }


if __name__ == "__main__":
    import json
    data = tonight(12.9716, 77.5946)
    print(json.dumps(data, indent=2))

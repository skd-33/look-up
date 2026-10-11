"""Compute tonight's visible sky objects using local de421.bsp only."""
import os, math
from datetime import datetime, timedelta, timezone, tzinfo

from skyfield.api import Loader, Star, wgs84
from skyfield.almanac import find_discrete, sunrise_sunset

DIR = os.path.dirname(os.path.abspath(__file__))

BODIES = {
    "Venus":   {"id": "venus",   "base_mag": -4.4},
    "Mars":    {"id": "mars",    "base_mag": 1.0},
    "Jupiter": {"id": "jupiter barycenter", "base_mag": -2.5},
    "Saturn":  {"id": "saturn barycenter",  "base_mag": 0.5},
    "Moon":    {"id": "moon",    "base_mag": -12.0},
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


def _moon_phase(elongation_deg):
    """Return phase name and illumination % from Sun-Earth-Moon elongation."""
    illum = (1 - math.cos(math.radians(elongation_deg))) / 2 * 100
    idx = int((elongation_deg + 22.5) / 45) % 8
    return MOON_PHASES[idx], round(illum, 1)


def tonight(lat, lon, tz_hours=None):
    """Return dict of tonight's sky for a given location.

    tz_hours: UTC offset in hours (e.g. 5.5 for IST). If None, estimated from lon.
    """
    load = Loader(DIR)
    ts = load.timescale(builtin=True)
    eph = load("de421.bsp")

    earth = eph["earth"]
    sun_body = eph["sun"]

    if tz_hours is None:
        tz_hours = round(lon / 15 * 2) / 2  # nearest half-hour
    tz = _FixedOffset(tz_hours)

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)
    today = now_local.date()

    # Build a search window that covers "tonight"
    if now_local.hour < 6:
        # Currently in the small hours — cover rest of this night
        start_local = now_local.replace(second=0, microsecond=0)
        end_local = datetime(today.year, today.month, today.day, 6, 0, tzinfo=tz)
        # For sunset/sunrise, look back to yesterday 4pm
        sun_search_start = datetime(today.year, today.month, today.day, 16, 0, tzinfo=tz) - timedelta(days=1)
    elif now_local.hour < 12:
        # Morning — show tonight (upcoming evening)
        start_local = datetime(today.year, today.month, today.day, 16, 0, tzinfo=tz)
        end_local = start_local + timedelta(hours=14)
        sun_search_start = start_local
    else:
        # Afternoon/evening — tonight starts at 4pm today
        start_local = datetime(today.year, today.month, today.day, 16, 0, tzinfo=tz)
        end_local = start_local + timedelta(hours=14)
        sun_search_start = start_local

    sun_search_end = end_local + timedelta(hours=2)

    t0 = ts.from_datetime(start_local)
    t1 = ts.from_datetime(end_local)

    observer = earth + wgs84.latlon(lat, lon)

    # Sun rise/set — use broader window to catch both
    f = sunrise_sunset(eph, wgs84.latlon(lat, lon))
    ts0 = ts.from_datetime(sun_search_start)
    ts1 = ts.from_datetime(sun_search_end)
    times, events = find_discrete(ts0, ts1, f)
    sunset_str = sunrise_str = None
    for t_ev, ev in zip(times, events):
        local = t_ev.utc_datetime().astimezone(tz)
        if ev == 0:  # sunset
            sunset_str = local.strftime("%I:%M %p")
        else:        # sunrise
            sunrise_str = local.strftime("%I:%M %p")

    # Check each body across the night window in 10-min steps
    window_hours = (end_local - start_local).total_seconds() / 3600
    steps = max(int(window_hours * 6), 12)
    t_steps = ts.linspace(t0, t1, steps + 1)

    t_now = ts.from_datetime(now_utc)

    objects = []
    best_peak_minutes = None  # window_minutes tracking

    for name, info in BODIES.items():
        body = eph[info["id"]]
        best_alt = -90
        best_time = None
        best_az = 0

        for t_step in t_steps:
            # Check sun altitude — need civil twilight (sun below -6°)
            sun_app = observer.at(t_step).observe(sun_body).apparent()
            sun_alt_deg = sun_app.altaz()[0].degrees
            if sun_alt_deg > -6:
                continue

            app = observer.at(t_step).observe(body).apparent()
            alt_deg, az_deg, _ = app.altaz()
            alt_val = alt_deg.degrees
            az_val = az_deg.degrees

            if alt_val > 10 and alt_val > best_alt:
                best_alt = alt_val
                best_az = az_val
                best_time = t_step

        visible = best_alt > 10 and best_time is not None

        obj = {"name": name, "visible": visible}
        if visible:
            local_best = best_time.utc_datetime().astimezone(tz)
            obj["best_time"] = local_best.strftime("%I:%M %p")
            obj["direction"] = _compass(best_az)
            obj["altitude"] = round(best_alt, 1)
            obj["magnitude"] = info["base_mag"]

            # window_minutes: minutes from now until this object peaks
            delta = (best_time.utc_datetime() - now_utc).total_seconds() / 60
            obj["minutes_to_peak"] = round(delta)
            if best_peak_minutes is None or abs(delta) < abs(best_peak_minutes):
                best_peak_minutes = delta

        if name == "Moon":
            moon_app = observer.at(t_now).observe(body).apparent()
            sun_app = observer.at(t_now).observe(sun_body).apparent()
            elong = moon_app.separation_from(sun_app).degrees
            phase_name, illum = _moon_phase(elong)
            obj["phase"] = phase_name
            obj["illumination"] = illum

        objects.append(obj)

    return {
        "date": now_local.strftime("%a %d %b, %I:%M %p"),
        "sunset": sunset_str,
        "sunrise": sunrise_str,
        "objects": objects,
        "window_minutes": round(best_peak_minutes) if best_peak_minutes else None,
    }


if __name__ == "__main__":
    import json
    data = tonight(12.9716, 77.5946, tz_hours=5.5)
    print(json.dumps(data, indent=2))

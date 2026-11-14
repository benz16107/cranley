"""The sun's path over an address, the days worth tracing, and clear-sky irradiance. No network.

Sun position is the NOAA solar calculator (geometry.georef.sun_position, about 0.1 degree for 1900-2100); this module
only samples it over days and a year and adds the clear-sky beam and diffuse light that solar_roof weighs by.
"""
from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

import numpy as np

from ..geometry.georef import guess_timezone, sun_position

# Fixed dates for the solstices and equinoxes: within a day of the true dates for 2000-2100, which moves the sun by
# under 0.4 degrees of declination at the equinoxes and almost nothing at the solstices.
KEY_DAYS = (("march_equinox", "March equinox", 3, 20), ("june_solstice", "June solstice", 6, 21),
            ("september_equinox", "September equinox", 9, 22), ("december_solstice", "December solstice", 12, 21))
SOLAR_CONSTANT = 1361.0  # W/m2, Kopp and Lean 2011


def key_days(day: dt.date) -> list[tuple[str, str, dt.date]]:
    """(id, label, date): the given day first, then the equinoxes and solstices of its year (a key day that is the
    given day appears once)."""
    out = [("day", f"{day:%b} {day.day}", day)]
    for key, label, m, d in KEY_DAYS:
        k = dt.date(day.year, m, d)
        if k == day:
            out[0] = (key, label, k)
        else:
            out.append((key, label, k))
    return out


def zone(lon: float, tz: str | None = None) -> ZoneInfo:
    return ZoneInfo(tz or guess_timezone(lon))


def day_path(lat: float, lon: float, day: dt.date, step_min: int = 10, tz: str | None = None) -> list[tuple]:
    """(local time, azimuth, elevation) at the middle of each `step_min` slot of the day while the sun is up."""
    z = zone(lon, tz)
    t0 = dt.datetime.combine(day, dt.time(0, 0), z)
    out = []
    for m in range(0, 24 * 60, step_min):
        t = t0 + dt.timedelta(minutes=m + step_min / 2)
        az, el = sun_position(t, lat, lon)
        if el > 0:
            out.append((t - dt.timedelta(minutes=step_min / 2), az, el))
    return out


def year_path(lat: float, lon: float, year: int, step_h: float = 1.0) -> dict:
    """Sun azimuth and elevation (degrees, numpy arrays) every `step_h` hours of a year, sun up only, plus the
    clear-sky beam (dni) and diffuse (dhi) in W/m2 and the hours each sample stands for."""
    t0 = dt.datetime(year, 1, 1, tzinfo=dt.UTC)
    n = int(365 * 24 / step_h)
    az, el = np.empty(n), np.empty(n)
    for i in range(n):
        az[i], el[i] = sun_position(t0 + dt.timedelta(hours=(i + 0.5) * step_h), lat, lon)
    up = el > 0.5
    dni, dhi = clear_sky(el[up])
    return {"az": az[up], "el": el[up], "dni": dni, "dhi": dhi, "hours": step_h}


def clear_sky(el_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Clear-sky direct normal and diffuse horizontal irradiance in W/m2 from sun elevation.

    Beam: Meinel and Meinel (1976), DNI = S * 0.7 ** (AM ** 0.678), with the Kasten and Young (1989) air mass.
    Diffuse: a flat 10% of the beam on a horizontal surface's terms, a common rule for clear skies. Used only as
    a ratio between roof orientations (solar_roof scales by a PVWatts yield), so the absolute level drops out."""
    el = np.asarray(el_deg, float)
    zen = 90 - el
    am = 1 / (np.cos(np.radians(zen)) + 0.50572 * (96.07995 - zen) ** -1.6364)
    dni = SOLAR_CONSTANT * 0.7 ** (am ** 0.678)
    dhi = 0.1 * dni
    return dni, dhi


def cos_incidence(sun_az, sun_el, surf_az: float, tilt: float) -> np.ndarray:
    """Cosine of the angle between the sun and a surface's normal; the surface faces `surf_az` (compass degrees)
    tilted `tilt` degrees from flat (90 is a wall). Negative when the sun is behind the surface."""
    a, e = np.radians(sun_az), np.radians(sun_el)
    sa, t = math.radians(surf_az), math.radians(tilt)
    return np.sin(e) * math.cos(t) + np.cos(e) * math.sin(t) * np.cos(a - sa)


def off_normal(sun_az, surf_az: float):
    """Horizontal angle in degrees between the sun and the direction a wall faces, 0 to 180."""
    return np.abs((np.asarray(sun_az) - surf_az + 180) % 360 - 180)

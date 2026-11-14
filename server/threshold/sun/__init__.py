"""Sun and orientation, shared by sun_rooms, solar_roof and anyone who needs which way a window faces.

    key_days(day)                       the day plus the equinoxes and solstices of its year
    day_path(lat, lon, day)             (local time, azimuth, elevation) while the sun is up (NOAA algorithm)
    year_path(lat, lon, year)           a year of sun positions with clear-sky beam and diffuse light
    cos_incidence / off_normal          sun against a surface or a wall
    horizon.grid / horizon.horizon      the surface model round a point and the skyline it makes from a point
    window_points(plan) / window_sun    each exterior window's facing, height and hours of direct sun
    facing, azimuth_of, compass         re-exported from geometry.georef (the settled compass convention)
"""
from ..geometry.georef import azimuth_of, compass, facing, sun_position, to_enu, to_latlon
from . import horizon
from .path import clear_sky, cos_incidence, day_path, key_days, off_normal, year_path, zone
from .windows import window_points, window_sun

__all__ = ["azimuth_of", "clear_sky", "compass", "cos_incidence", "day_path", "facing", "horizon", "key_days",
           "off_normal", "sun_position", "to_enu", "to_latlon", "window_points", "window_sun", "year_path", "zone"]

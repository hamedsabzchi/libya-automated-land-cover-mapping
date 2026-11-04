"""Handle incomplete browser viewport messages without changing study geometry."""
import math
from ipyleaflet import Map


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def valid_bounds(value):
    try:
        (south, west), (north, east) = value
        return (all(finite_number(x) for x in (south, west, north, east))
                and -90 <= south < north <= 90 and west < east)
    except (TypeError, ValueError):
        return False


def view_for_bounds(bounds, width=640, height=440):
    """Compute an initial Web Mercator view without waiting for browser events."""
    if not valid_bounds(bounds):
        raise ValueError('The study-area display bounds are invalid.')
    (south, west), (north, east) = bounds
    def mercator(lat):
        lat = max(-85.05112878, min(85.05112878, lat))
        return (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2
    y0, y1 = mercator(north), mercator(south)
    span_x, span_y = (east-west)/360, y1-y0
    zoom = math.floor(math.log2(min(width/(256*max(span_x, 1e-12)),
                                   height/(256*max(span_y, 1e-12)))))
    lat = math.degrees(math.atan(math.sinh(math.pi*(1-y0-y1))))
    return (lat, (west+east)/2), max(1, min(18, zoom))


class NotebookMap(Map):
    """Retain the last finite viewport until the frontend has a valid view.

    ipyleaflet 0.20's update_bounds initializes east/west to infinities when
    no Leaflet view is available. JSON transport can turn these into null.
    They describe browser layout, not Earth Engine geometry. Never make
    Float traits nullable or replace missing positions with fake coordinates.
    """
    def set_state(self, sync_data):
        state = dict(sync_data)
        for group in (('south', 'north', 'east', 'west'),
                      ('bottom', 'top', 'right', 'left')):
            if any(name in state and not finite_number(state[name]) for name in group):
                # Discard the whole related group to avoid a half-updated box.
                for name in group:
                    state.pop(name, None)
        super().set_state(state)

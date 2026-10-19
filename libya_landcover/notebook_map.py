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

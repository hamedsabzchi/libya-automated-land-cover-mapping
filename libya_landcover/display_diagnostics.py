"""Explicit single-tile check of an existing layer, never mapping or export.

No retries, redirects or prefetch. A PNG response proves neither visible colours
nor browser rendering, and does not validate full study-area coverage.
"""
import json
import math
from urllib.parse import urlsplit
import requests
from .map_view import error_detail


def check_display_tile(template, center, zoom, *, get=None):
    parts = urlsplit(template)
    if (parts.scheme != 'https' or parts.hostname not in {
            'earthengine.googleapis.com', 'earthengine-highvolume.googleapis.com'}
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise ValueError('Use the Earth Engine layer supplied by the open map.')
    if (len(center) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in center)
            or type(zoom) not in (int, float) or not math.isfinite(zoom) or not 0 <= zoom <= 22):
        raise ValueError('Wait for the map viewport to settle, then try again.')
    lat, lon = center
    lat = max(-85.05112878, min(85.05112878, lat))
    lon = (lon + 180) % 360 - 180
    z = int(zoom)
    n = 2 ** z
    x = min(n - 1, max(0, math.floor((lon + 180) / 360 * n)))
    y = min(n - 1, max(0, math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)))
    url = template.format(x=x, y=y, z=z)
    result = {'scope': 'one_display_tile_from_colab', 'tile': {'z': z, 'x': x, 'y': y},
              'browser_rendering_verified': False, 'full_area_verified': False}
    try:
        with (get or requests.get)(url, timeout=(5, 20), allow_redirects=False, stream=True) as response:
            result['http_status'] = response.status_code
            body = bytearray()
            for chunk in response.iter_content(chunk_size=4096):
                body.extend(chunk[:65536 - len(body)])
                if len(body) >= 65536:
                    break
            if response.status_code == 200 and body.startswith(b'\x89PNG\r\n\x1a\n'):
                result.update(state='png_response', message='Earth Engine returned PNG data for one display tile. This does not verify visible colours, browser rendering or the full study area.')
            else:
                result.update(state='http_error' if response.status_code != 200 else 'unexpected_response',
                              message='The display-tile request did not return PNG data. Share these details; do not create the map again.')
                try:
                    payload = json.loads(body)
                    error = payload.get('error', {}) if isinstance(payload, dict) else {}
                    detail = error.get('message') if isinstance(error, dict) else None
                    if detail:
                        result['detail'] = error_detail(detail)
                except (ValueError, UnicodeDecodeError):
                    pass
    except requests.Timeout:
        result.update(state='timeout', message='One display tile did not respond within the check timeout. This alone does not identify the cause. Do not restart mapping or repeatedly reload.')
    except requests.RequestException as exc:
        result.update(state='connection_error', error_type=type(exc).__name__,
                      message='Colab could not retrieve this display tile. Share these details; browser delivery may differ.')
    return result

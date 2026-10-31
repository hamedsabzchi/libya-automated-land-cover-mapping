"""Single display request, bounded evidence, no real network or model work."""
import json
import unittest
from unittest.mock import Mock
import requests
from libya_landcover.display_diagnostics import check_display_tile

URL = 'https://earthengine.googleapis.com/v1/projects/example/maps/temporary/tiles/{z}/{x}/{y}?token=private'

def reply(status, body):
    response = Mock(status_code=status)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.iter_content.return_value = [body]
    return Mock(return_value=response)

class DisplayCheckTests(unittest.TestCase):
    def test_png_is_single_tile_evidence_not_whole_map_success(self):
        get = reply(200, b'\x89PNG\r\n\x1a\nexample')
        result = check_display_tile(URL, [0, 0], 2, get=get)
        self.assertEqual(result['tile'], {'z': 2, 'x': 2, 'y': 2})
        self.assertEqual(result['state'], 'png_response')
        self.assertFalse(result['browser_rendering_verified'])
        self.assertFalse(result['full_area_verified'])
        get.assert_called_once_with(URL.format(z=2, x=2, y=2), timeout=(5, 20), allow_redirects=False, stream=True)
        self.assertNotIn('private', json.dumps(result))
    def test_error_codes_and_sanitized_service_detail(self):
        for status in (401, 403, 429, 500):
            get = reply(status, json.dumps({'error': {'message': 'Error https://example.test/?token=secret access_token=hidden'}}).encode())
            result = check_display_tile(URL, [32.8, 13.2], 8, get=get)
            self.assertEqual(result['http_status'], status)
            self.assertEqual(result['state'], 'http_error')
            self.assertNotIn('secret', result['detail'])
            self.assertNotIn('hidden', result['detail'])
            get.assert_called_once()
    def test_timeout_has_no_retry_or_unproven_quota_diagnosis(self):
        get = Mock(side_effect=requests.Timeout('private URL'))
        result = check_display_tile(URL, [32.8, 13.2], 8, get=get)
        self.assertEqual(result['state'], 'timeout')
        self.assertNotIn('quota', result['message'])
        self.assertNotIn('private', json.dumps(result))
        get.assert_called_once()
    def test_redirect_html_and_success_without_png_are_not_images(self):
        for status in (302, 200):
            result = check_display_tile(URL, [32.8, 13.2], 8, get=reply(status, b'<html>private error</html>'))
            self.assertNotEqual(result['state'], 'png_response')
            self.assertNotIn('private', json.dumps(result))
    def test_untrusted_host_and_invalid_viewport_make_no_request(self):
        get = Mock()
        for url, center, zoom in [('https://example.com/{z}/{x}/{y}', [0, 0], 1), (URL, [float('nan'), 0], 1), (URL, [0, 0], 23)]:
            with self.assertRaises(ValueError):
                check_display_tile(url, center, zoom, get=get)
        get.assert_not_called()

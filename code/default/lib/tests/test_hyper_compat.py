import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'noarch'))

from hyper_compat import HTTPHeaderMap, Encoder, Decoder


class TestHTTPHeaderMap(unittest.TestCase):
    def test_str_key_str_value(self):
        h = HTTPHeaderMap()
        h[':status'] = '200'
        self.assertEqual(h[':status'], b'200')
        self.assertEqual(h[b':status'], b'200')

    def test_bytes_key_bytes_value(self):
        h = HTTPHeaderMap()
        h[b'Content-Length'] = b'1234'
        self.assertEqual(h[b'Content-Length'], b'1234')
        self.assertEqual(h['content-length'], b'1234')

    def test_bytes_key_get_str_key(self):
        h = HTTPHeaderMap()
        h['Server'] = 'nginx'
        self.assertEqual(h[b'server'], b'nginx')
        self.assertEqual(h['Server'], b'nginx')

    def test_contains_str_and_bytes(self):
        h = HTTPHeaderMap()
        h[':status'] = '200'
        self.assertIn(':status', h)
        self.assertIn(b':status', h)

    def test_get_with_default(self):
        h = HTTPHeaderMap()
        self.assertEqual(h.get(b'X-Cost', -1), -1)
        self.assertEqual(h.get('X-Cost', -1), -1)

    def test_get_returns_bytes(self):
        h = HTTPHeaderMap()
        h['X-Cost'] = '0.342'
        val = h.get('X-Cost', -1)
        self.assertIsInstance(val, bytes)
        self.assertEqual(float(val), 0.342)

    def test_get_returns_bytes_for_bytes_key(self):
        h = HTTPHeaderMap()
        h['X-Cost'] = '0.342'
        val = h.get(b'X-Cost', -1)
        self.assertIsInstance(val, bytes)
        self.assertEqual(float(val), 0.342)

    def test_content_length_value_is_bytes(self):
        h = HTTPHeaderMap()
        h['Content-Length'] = '1024'
        val = h.get('Content-Length')
        self.assertIsInstance(val, bytes)
        self.assertEqual(int(val), 1024)

    def test_content_length_bytes_set(self):
        h = HTTPHeaderMap()
        h[b'Content-Length'] = b'2048'
        val = h.get(b'Content-Length')
        self.assertIsInstance(val, bytes)
        self.assertEqual(int(val), 2048)

    def test_hpack_decoder_integration(self):
        decoder = Decoder()
        encoded = encoder = Encoder()
        encoded = encoder.encode([(':status', '200'), ('content-length', '1024')])
        headers = decoder.decode(encoded)
        h = HTTPHeaderMap(dict(headers))
        self.assertEqual(h[b':status'], b'200')
        self.assertEqual(h[':status'], b'200')
        status_val = h.get(b':status', -1)
        self.assertEqual(int(status_val), 200)
        cl_val = h.get('content-length')
        self.assertEqual(int(cl_val), 1024)

    def test_xcost_arithmetic(self):
        h = HTTPHeaderMap()
        h['X-Cost'] = '0.342'
        xcost = h.get('X-Cost', -1)
        if isinstance(xcost, (bytes, bytearray)):
            xcost = float(xcost)
        rtt = 1.5 - xcost
        self.assertAlmostEqual(rtt, 1.158)

    def test_xcost_not_present(self):
        h = HTTPHeaderMap()
        xcost = h.get('X-Cost', -1)
        self.assertEqual(xcost, -1)


class TestHTTPHeaderValuesInArithmetic(unittest.TestCase):
    """Tests that simulate the exact code paths in http2_stream.py and http1.py
    where header values are used in arithmetic operations."""

    def test_h2_xcost_float_subtraction(self):
        h = HTTPHeaderMap()
        h['X-Cost'] = '0.342'
        xcost = h.get('X-Cost', -1)
        if isinstance(xcost, (bytes, bytearray)):
            xcost = float(xcost)
        elif isinstance(xcost, list):
            xcost = float(xcost[0])
        whole_cost = 1.5
        rtt = whole_cost - xcost
        self.assertAlmostEqual(rtt, 1.158)

    def test_h2_xcost_default_subtraction(self):
        h = HTTPHeaderMap()
        xcost = h.get('X-Cost', -1)
        if isinstance(xcost, (bytes, bytearray)):
            xcost = float(xcost)
        elif isinstance(xcost, list):
            xcost = float(xcost[0])
        whole_cost = 1.5
        rtt = whole_cost - xcost
        self.assertAlmostEqual(rtt, 2.5)

    def test_h2_content_length_get_and_int(self):
        h = HTTPHeaderMap()
        h['Content-Length'] = '262144'
        length = h.get('Content-Length', None)
        if isinstance(length, (bytes, bytearray)):
            length = int(length)
        elif isinstance(length, list):
            length = int(length[0])
        self.assertEqual(int(length), 262144)

    def test_h2_status_int(self):
        h = HTTPHeaderMap()
        h[':status'] = '200'
        status = int(h[':status'])
        self.assertEqual(status, 200)

    def test_h2_status_404(self):
        h = HTTPHeaderMap()
        h[':status'] = '404'
        status = int(h[b':status'])
        self.assertEqual(status, 404)

    def test_h1_response_headers_xcost(self):
        headers = {b'X-Cost': b'0.5'}
        xcost_raw = headers.get(b'X-Cost', -1)
        if isinstance(xcost_raw, (bytes, bytearray)):
            xcost = float(xcost_raw)
        elif isinstance(xcost_raw, list):
            xcost = float(xcost_raw[0])
        else:
            xcost = float(xcost_raw)
        self.assertAlmostEqual(xcost, 0.5)
        rtt = 1.0 - xcost
        self.assertAlmostEqual(rtt, 0.5)

    def test_h1_response_headers_xcost_default(self):
        headers = {}
        xcost_raw = headers.get(b'X-Cost', -1)
        if isinstance(xcost_raw, (bytes, bytearray)):
            xcost = float(xcost_raw)
        elif isinstance(xcost_raw, list):
            xcost = float(xcost_raw[0])
        else:
            xcost = float(xcost_raw)
        self.assertEqual(xcost, -1.0)

    def test_hpack_roundtrip_xcost(self):
        encoder = Encoder()
        decoder = Decoder()
        encoded = encoder.encode([
            (':status', '200'),
            ('x-cost', '0.342'),
            ('content-length', '1024'),
        ])
        headers = decoder.decode(encoded)
        h = HTTPHeaderMap(dict(headers))

        xcost = h.get('X-Cost', -1)
        if isinstance(xcost, (bytes, bytearray)):
            xcost = float(xcost)
        elif isinstance(xcost, list):
            xcost = float(xcost[0])
        whole_cost = 1.5
        rtt = whole_cost - xcost
        self.assertAlmostEqual(rtt, 1.158)

        length = h.get('Content-Length', None)
        if isinstance(length, (bytes, bytearray)):
            length = int(length)
        elif isinstance(length, list):
            length = int(length[0])
        self.assertEqual(int(length), 1024)


class TestHTTP2StreamKeyError(unittest.TestCase):
    def test_stream_id_not_in_streams_after_close(self):
        streams = {1: 'stream_a', 3: 'stream_b'}
        del streams[1]
        self.assertNotIn(1, streams)
        with self.assertRaises(KeyError):
            _ = streams[1]


if __name__ == '__main__':
    unittest.main()

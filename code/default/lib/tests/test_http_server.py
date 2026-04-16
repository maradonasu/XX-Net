import unittest
import utils
import http_client as simple_http_client
import http_server

class HttpClientTest(unittest.TestCase):
    def test_get(self):
        server = http_server.HTTPServer(('', 8880), http_server.TestHttpServer, ".")
        server.start()

        client = simple_http_client.Client(timeout=5)
        url = "http://localhost:8880/test"
        res = client.request("GET", url)
        self.assertEqual(res.status, 200)
        content = utils.to_str(res.text)
        print(content)

        server.shutdown()

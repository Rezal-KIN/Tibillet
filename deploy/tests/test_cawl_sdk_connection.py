"""Exercise the real SDK transport with fake credentials against localhost."""
import importlib.util
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from payment_providers.cawl import CawlConfiguration, CawlGateway


@unittest.skipUnless(importlib.util.find_spec('onlinepayments'), 'CAWL SDK is not installed')
class CawlSdkConnectionTests(unittest.TestCase):
    def test_gateway_can_send_a_request_with_the_real_sdk(self):
        paths = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                paths.append(self.path)
                body = json.dumps({'result': 'OK'}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        configuration = CawlConfiguration(
            merchant_id='example-merchant', api_key_id='example-key', api_secret='example-secret',
            webhook_key_id='example-webhook-key', webhook_secret='example-webhook-secret', test_mode=True,
        )
        try:
            endpoint = f'http://127.0.0.1:{server.server_port}'
            with patch.object(CawlConfiguration, 'endpoint', property(lambda _self: endpoint)):
                with CawlGateway(configuration).merchant() as merchant:
                    response = merchant.services().test_connection()
            self.assertEqual(response.result, 'OK')
            self.assertEqual(paths, ['/v2/example-merchant/services/testconnection'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()

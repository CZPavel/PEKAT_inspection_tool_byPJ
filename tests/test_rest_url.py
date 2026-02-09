import base64
import json

import requests

from pektool.clients.rest_client import RestClient


def test_parse_context_header():
    client = RestClient("127.0.0.1", 8000, api_key="", api_key_location="query", api_key_name="api_key")
    payload = {"ok": True}
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

    response = requests.Response()
    response._content = b""
    response.status_code = 200
    response.headers["ContextBase64utf"] = encoded

    context = client._parse_context(response, context_in_body=False, response_type="image")
    assert context == payload

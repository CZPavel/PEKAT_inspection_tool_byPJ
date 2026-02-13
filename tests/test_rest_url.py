import base64
import json

import requests

from pektool.clients.rest_client import RestClient


def test_parse_context_header():
    client = RestClient("127.0.0.1", 8000, api_key="", api_key_location="query", api_key_name="api_key")
    payload = {"ok": True}
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    image = b"\x89PNG\x01\x02"

    response = requests.Response()
    response._content = image
    response.status_code = 200
    response.headers["ContextBase64utf"] = encoded

    context = client._parse_context(response, context_in_body=False, response_type="image")
    _, image_bytes = client._parse_response(response, context_in_body=False, response_type="image")
    assert context == payload
    assert image_bytes == image


def test_parse_context_in_body():
    client = RestClient("127.0.0.1", 8000, api_key="", api_key_location="query", api_key_name="api_key")
    payload = {"result": False, "completeTime": 0.1}
    image = b"\x89PNG\x00\x00"
    context_blob = json.dumps(payload).encode("utf-8")

    response = requests.Response()
    response._content = image + context_blob
    response.status_code = 200
    response.headers["ImageLen"] = str(len(image))

    context = client._parse_context(response, context_in_body=True, response_type="annotated_image")
    _, image_bytes = client._parse_response(response, context_in_body=True, response_type="annotated_image")
    assert context == payload
    assert image_bytes == image

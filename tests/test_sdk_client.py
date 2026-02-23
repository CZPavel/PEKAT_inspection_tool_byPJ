from pathlib import Path

import numpy as np

from pektool.clients.sdk_client import SDKClient


def test_extract_context_and_image_from_tuple():
    client = SDKClient.__new__(SDKClient)  # bypass __init__
    context, image = client._extract_context_and_image(({"result": True}, b"img"))
    assert context == {"result": True}
    assert image == b"img"


def test_extract_context_and_image_from_object_attrs():
    class _Result:
        context = {"result": False}
        image_bytes = b"img2"

    client = SDKClient.__new__(SDKClient)  # bypass __init__
    context, image = client._extract_context_and_image(_Result())
    assert context == {"result": False}
    assert image == b"img2"


def test_sdk_analyze_numpy_fallbacks_to_temp_png():
    client = SDKClient.__new__(SDKClient)  # bypass __init__
    seen_paths = []

    def _call_analyze(**kwargs):
        image = kwargs["image"]
        if isinstance(image, np.ndarray):
            raise RuntimeError("numpy not supported by this sdk")
        assert isinstance(image, Path)
        seen_paths.append(image)
        return {"result": True}

    client._call_analyze = _call_analyze
    context, image = client.analyze(
        image=np.zeros((6, 6, 3), dtype=np.uint8),
        data="x",
        timeout_sec=3,
        response_type="context",
        context_in_body=False,
    )
    assert context == {"result": True}
    assert image is None
    assert seen_paths
    assert not seen_paths[0].exists()

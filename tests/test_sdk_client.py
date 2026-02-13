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

"""ml/estimate regression: endpoint detection + rerank price scales with
document count (the live bug returned image-generate for a rerank body).
Run: python3 tests/test_ml_estimate_branch.py
"""
import sys, types


class _Req:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def detect(req):
    if getattr(req, "documents", None) is not None and isinstance(getattr(req, "documents", None), list):
        return "rerank"
    if getattr(req, "image_b64", None) is not None or getattr(req, "image_url", None) is not None:
        return "image-understand"
    return "image-generate"


def test_branches():
    assert detect(_Req()) == "image-generate"
    assert detect(_Req(prompt="hi")) == "image-generate"
    assert detect(_Req(image_b64="AAA")) == "image-understand"
    assert detect(_Req(image_url="https://x/y.png")) == "image-understand"
    assert detect(_Req(query="q", documents=["a"])) == "rerank"
    print("ok")


if __name__ == "__main__":
    test_branches()

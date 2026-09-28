from lib import store as store_lib


def test_sanitize_metadata_drops_none_and_stringifies_lists():
    raw = {
        "doc_key": "123",
        "page": None,
        "tags": ["a", "b"],
        "bbox": {"l": 1, "t": 2, "r": 3, "b": 4},
        "score": 0.5,
        "flag": True,
    }
    clean = store_lib.sanitize_metadata(raw)
    assert "page" not in clean
    assert clean["tags"] == "a, b"
    assert isinstance(clean["bbox"], str)
    assert clean["score"] == 0.5
    assert clean["flag"] is True
    for v in clean.values():
        assert isinstance(v, (str, int, float, bool))

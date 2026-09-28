"""Unit tests for the pure-logic helpers in lib/chunk.py (no docling/tokenizer download)."""
from lib import chunk as chunk_lib


def test_skip_heading_matches_references_and_abstract():
    assert chunk_lib._is_skipped_section("References")
    assert chunk_lib._is_skipped_section("Bibliography")
    assert chunk_lib._is_skipped_section("Abstract")
    assert chunk_lib._is_skipped_section("Introduction > Abstract")


def test_skip_heading_does_not_match_regular_sections():
    assert not chunk_lib._is_skipped_section("Introduction")
    assert not chunk_lib._is_skipped_section("Acknowledgements")
    assert not chunk_lib._is_skipped_section("Funding")
    assert not chunk_lib._is_skipped_section("")


def test_max_tokens_for_known_and_unknown_models():
    assert chunk_lib._max_tokens_for_model("BAAI/bge-small-en-v1.5") == 512
    assert chunk_lib._max_tokens_for_model("BAAI/bge-m3") == 8192
    assert chunk_lib._max_tokens_for_model("some/unknown-model") == chunk_lib.DEFAULT_MAX_TOKENS

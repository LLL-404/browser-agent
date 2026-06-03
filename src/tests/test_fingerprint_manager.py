"""Tests for shared/fingerprint_manager.py — browser fingerprint generation."""
from shared.fingerprint_manager import (
    WINDOW_PRESETS,
    FALLBACK_UA_LIST,
    generate_camoufox_opts,
    random_user_agent,
)


class TestGenerateCamoufoxOpts:
    def test_returns_dict_with_expected_keys(self):
        opts = generate_camoufox_opts()
        assert isinstance(opts, dict)
        assert "window" in opts
        assert "os" in opts
        assert "screen" in opts

    def test_window_from_presets(self):
        for _ in range(100):
            opts = generate_camoufox_opts()
            w, h = opts["window"]
            assert (w, h) in WINDOW_PRESETS

    def test_screen_dimensions_larger_than_window(self):
        for _ in range(100):
            opts = generate_camoufox_opts()
            sw = opts["screen"]["width"]
            sh = opts["screen"]["height"]
            ww, wh = opts["window"]
            assert sw >= ww
            assert sh >= wh

    def test_color_depth_is_24(self):
        opts = generate_camoufox_opts()
        assert opts["screen"]["colorDepth"] == 24
        assert opts["screen"]["pixelDepth"] == 24

    def test_os_is_list_of_one(self):
        for _ in range(50):
            opts = generate_camoufox_opts()
            assert isinstance(opts["os"], list)
            assert len(opts["os"]) == 1


class TestRandomUserAgent:
    def test_returns_string(self):
        ua = random_user_agent()
        assert isinstance(ua, str)
        assert ua.startswith("Mozilla")

    def test_returns_from_fallback_list(self):
        for _ in range(100):
            ua = random_user_agent()
            assert ua in FALLBACK_UA_LIST

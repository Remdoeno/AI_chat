import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendSamplingControlsTests(unittest.TestCase):
    def test_hidden_bunny_sampling_controls_are_present(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        for expected in (
            'id="bunnyLogoButton"',
            'id="advancedOptions"',
            'id="temperatureRange"',
            'id="topPRange"',
            'id="confirmSamplingButton"',
            'hidden',
        ):
            self.assertIn(expected, html)

    def test_chat_request_uses_sampling_controls_instead_of_constants(self):
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function getSamplingSettings()", js)
        self.assertIn("function handleBunnyLogoClick()", js)
        self.assertIn("BUNNY_CLICK_WINDOW_MS = 1000", js)
        self.assertIn("BUNNY_CLICK_TARGET = 4", js)
        self.assertIn("localStorage.setItem(SAMPLING_STORAGE_KEY", js)
        self.assertIn("...getSamplingSettings()", js)
        self.assertNotIn("temperature: 0.6", js)


if __name__ == "__main__":
    unittest.main()

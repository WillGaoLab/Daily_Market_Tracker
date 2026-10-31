from __future__ import annotations
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.history import read_history
from scripts.interactive_fingerprint import ROOT, SVG_NS, component_html, render_svg, values_for


class InteractiveFingerprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_history(ROOT / "data/history.csv")
        cls.row = next(row for row in reversed(cls.rows) if all(value != "NA" for value in row.values()))
        cls.text = render_svg(cls.row["date"])
        cls.svg = ET.fromstring(cls.text)

    def test_targets_use_original_artist_geometry_and_nine_values(self):
        self.assertEqual(self.svg.get("data-fingerprint-date"), self.row["date"])
        self.assertEqual(json.loads(self.svg.get("data-fingerprint-values")), values_for(self.row))
        line = next(item for item in self.svg.iter() if item.get("id") == "fingerprint-radar")
        markers = list(line.iter(f"{{{SVG_NS}}}use"))[:9]
        overlay = next(item for item in self.svg.iter() if item.get("id") == "fingerprint-targets")
        circles = list(overlay.iter(f"{{{SVG_NS}}}circle"))
        self.assertEqual(len(circles), 9)
        self.assertEqual(len(list(overlay.iter(f"{{{SVG_NS}}}rect"))), 9)
        for marker, circle in zip(markers, circles):
            self.assertEqual((marker.get("x"), marker.get("y")), (circle.get("cx"), circle.get("cy")))
            self.assertEqual(circle.get("tabindex"), "0")

    def test_unavailable_migrated_values_are_not_zero(self):
        row = {**self.row, "bitcoin_change_pct": "NA"}
        with self.assertRaisesRegex(ValueError, "unavailable"):
            values_for(row)

    def test_embedded_payload_cannot_close_script_tag(self):
        html = component_html({**self.row, "source": "</script><img onerror=alert(1)>"}, self.text)
        self.assertNotIn("</script><img", html)
        self.assertIn("\\u003c/script\\u003e", html)
        self.assertIn("fingerprint-radar", html)


if __name__ == "__main__":
    unittest.main()

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from history import FIELDNAMES, append_record, read_history
from sync_mirror import sync


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source, self.mirror = [Path(self.temp.name) / name for name in ("source", "mirror")]
        self.record = {field: "1.000000" for field in FIELDNAMES}
        self.record.update(date="2026-11-05", source="Yahoo Finance")
        append_record(self.source / "data/history.csv", self.record)
        (self.source / "figures").mkdir()
        for suffix, content in {"png": b"\x89PNG\r\n\x1a\ncanonical", "svg": b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'}.items():
            (self.source / "figures" / f"2026-11-05.{suffix}").write_bytes(content)

    def test_new_row_and_exact_figures_are_copied_idempotently(self):
        older = dict(self.record, date="2026-11-04")
        append_record(self.mirror / "data/history.csv", older)
        old_bytes = (self.mirror / "data/history.csv").read_bytes()
        sync(self.source, self.mirror, date(2026, 11, 5))
        after = (self.mirror / "data/history.csv").read_bytes()
        self.assertTrue(after.startswith(old_bytes))
        for suffix in ("png", "svg"):
            self.assertEqual((self.source / "figures" / f"2026-11-05.{suffix}").read_bytes(), (self.mirror / "figures" / f"2026-11-05.{suffix}").read_bytes())
        sync(self.source, self.mirror, date(2026, 11, 5))
        self.assertEqual(after, (self.mirror / "data/history.csv").read_bytes())
        self.assertEqual(len(read_history(self.mirror / "data/history.csv")), 2)

    def test_conflicting_history_and_missing_assets_make_no_changes(self):
        append_record(self.mirror / "data/history.csv", dict(self.record, bitcoin_current="2.000000"))
        old_bytes = (self.mirror / "data/history.csv").read_bytes()
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            sync(self.source, self.mirror, date(2026, 11, 5))
        self.assertEqual(old_bytes, (self.mirror / "data/history.csv").read_bytes())
        self.assertFalse((self.mirror / "figures").exists())
        (self.source / "figures/2026-11-05.svg").unlink()
        with self.assertRaises(FileNotFoundError):
            sync(self.source, self.mirror, date(2026, 11, 5))
        self.assertEqual(old_bytes, (self.mirror / "data/history.csv").read_bytes())

    def test_source_verification_is_read_only(self):
        result = sync(self.source, self.mirror, date(2026, 11, 5), verify_only=True)
        self.assertEqual(result["status"], "source_verified")
        self.assertFalse(self.mirror.exists())


if __name__ == "__main__":
    unittest.main()

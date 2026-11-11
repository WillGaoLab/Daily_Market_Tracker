import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import daily_pipeline


class ExistingRecordRepairTests(unittest.TestCase):
    def test_existing_record_repairs_png_without_fetching_or_appending(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "figures").mkdir()
            (root / "figures/2026-11-05.svg").write_text("existing svg")
            with patch.object(daily_pipeline, "PROJECT_ROOT", root), patch.object(daily_pipeline, "read_history", return_value=[{"date": "2026-11-05"}]), patch.object(daily_pipeline, "generate") as png, patch.object(daily_pipeline, "export_svg") as svg, patch.object(daily_pipeline, "fetch_record") as fetch, patch.object(daily_pipeline, "append_record") as append:
                self.assertEqual(daily_pipeline.main(date(2026, 11, 5)), 0)
                png.assert_called_once_with("2026-11-05")
                svg.assert_not_called()
                fetch.assert_not_called()
                append.assert_not_called()

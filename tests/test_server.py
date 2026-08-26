import tempfile
import unittest
from pathlib import Path

from server import TranscriptionEngine, parse_transcription_output, safe_filename


class ServerUnitTests(unittest.TestCase):
    def test_filename_removes_windows_reserved_characters(self):
        self.assertEqual(safe_filename('a/b:c*?"<>|'), "a_b_c")

    def test_transcription_parser_removes_model_tags(self):
        source = "<|zh|><|NEUTRAL|><|Speech|><|withitn|>湖北一公司。\n"
        self.assertEqual(parse_transcription_output(source), "湖北一公司。")

    def test_runtime_status_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as name:
            status = TranscriptionEngine(Path(name)).runtime_status()
            self.assertFalse(status.ready)
            self.assertIn("SenseVoice Q8 模型", status.missing)


if __name__ == "__main__":
    unittest.main()

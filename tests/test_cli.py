from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from net_speed.cli import main
from net_speed.measurement import DownloadError, Measurement, Summary


class CliTests(unittest.TestCase):
    def test_prints_results_with_units(self):
        summary = Summary(tuple(Measurement(1_000_000, 0.5) for _ in range(10)))
        output = StringIO()
        with patch("net_speed.cli.measure", return_value=summary) as measure:
            with redirect_stdout(output):
                self.assertEqual(main(["https://example.com/file"]), 0)
        measure.assert_called_once_with("https://example.com/file", 30.0)
        self.assertIn("Среднее время запроса: 0.500 с", output.getvalue())
        self.assertIn("Скачано: 10000000 байт", output.getvalue())
        self.assertIn("Скорость скачивания: 2.000 MB/s", output.getvalue())

    def test_rejects_invalid_arguments_before_network_request(self):
        for args in [
            [], ["file:///tmp/file"], ["https://"], ["http://example.com:bad"],
            ["https://example.com", "--timeout", "0"],
            ["https://example.com", "--timeout", "nan"],
            ["https://example.com", "--timeout", "inf"],
        ]:
            with self.subTest(args=args), patch("net_speed.cli.measure") as measure:
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                    main(args)
                self.assertEqual(error.exception.code, 2)
                measure.assert_not_called()

    def test_error_goes_to_stderr_without_partial_result(self):
        output, errors = StringIO(), StringIO()
        with patch("net_speed.cli.measure", side_effect=DownloadError("Запрос 3/10: timeout")):
            with redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(main(["https://example.com/file"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("Запрос 3/10", errors.getvalue())

    def test_keyboard_interrupt_returns_130(self):
        with patch("net_speed.cli.measure", side_effect=KeyboardInterrupt):
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["https://example.com/file"]), 130)


if __name__ == "__main__":
    unittest.main()

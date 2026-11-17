from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest
from unittest.mock import patch

from net_speed.measurement import (
    DownloadError, Measurement, Summary, download, measure, timed_download,
)


PAYLOAD = b"test-data" * 20_000


@contextmanager
def local_server():
    class Handler(BaseHTTPRequestHandler):
        requests = 0
        completed = 0
        overlap = False

        def do_GET(self):
            if self.requests != self.completed:
                type(self).overlap = True
            type(self).requests += 1
            if self.path == "/error":
                self.send_error(503)
                type(self).completed += 1
                return
            self.send_response(200)
            if self.path != "/no-length":
                size = len(PAYLOAD) + (1 if self.path == "/truncated" else 0)
                self.send_header("Content-Length", str(size))
            self.end_headers()
            self.wfile.write(PAYLOAD[:-1])
            # Последние байты отправляем только после регистрации завершения.
            type(self).completed += 1
            self.wfile.write(PAYLOAD[-1:])
            self.wfile.flush()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class MeasurementTests(unittest.TestCase):
    def test_decorator_times_whole_function_and_preserves_name(self):
        @timed_download
        def fetch(size: int) -> int:
            return size

        with patch("net_speed.measurement.perf_counter", side_effect=[10.0, 12.5]):
            self.assertEqual(fetch(42), Measurement(42, 2.5))
        self.assertEqual(fetch.__name__, "fetch")

    def test_summary_uses_total_bytes_divided_by_total_time(self):
        summary = Summary((Measurement(1_000_000, 1), Measurement(9_000_000, 3)))
        self.assertEqual(summary.total_bytes, 10_000_000)
        self.assertEqual(summary.average_seconds, 2)
        self.assertEqual(summary.megabytes_per_second, 2.5)

    def test_ten_sequential_requests_read_every_byte(self):
        with local_server() as (url, handler):
            result = measure(url, timeout=2)
            self.assertEqual(handler.requests, 10)
            self.assertEqual(handler.completed, 10)
            self.assertFalse(handler.overlap)
        self.assertEqual(len(result.measurements), 10)
        self.assertEqual(result.total_bytes, 10 * len(PAYLOAD))
        self.assertTrue(all(item.elapsed_seconds > 0 for item in result.measurements))

    def test_response_without_content_length(self):
        with local_server() as (url, _):
            self.assertEqual(download(url + "/no-length", 2).downloaded_bytes, len(PAYLOAD))

    def test_truncated_response_is_rejected(self):
        with local_server() as (url, handler):
            with self.assertRaisesRegex(DownloadError, "Запрос 1/10.*Неполный ответ"):
                measure(url + "/truncated", 2)
            self.assertEqual(handler.requests, 1)

    def test_http_error_stops_measurement(self):
        with local_server() as (url, handler):
            with self.assertRaisesRegex(DownloadError, "Запрос 1/10.*503"):
                measure(url + "/error", 2)
            self.assertEqual(handler.requests, 1)

    def test_timeout_is_reported_with_request_number(self):
        with patch("net_speed.measurement.download", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(DownloadError, "Запрос 1/10.*timed out"):
                measure("https://example.com/file", 2)


if __name__ == "__main__":
    unittest.main()

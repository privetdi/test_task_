"""Скачивание, измерение времени и расчёт итоговой статистики."""

from dataclasses import dataclass
from functools import wraps
from http.client import HTTPException
from time import perf_counter
from typing import Callable, ParamSpec
from urllib.error import HTTPError
from urllib.request import Request, urlopen


REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024
P = ParamSpec("P")


@dataclass(frozen=True)
class Measurement:
    downloaded_bytes: int
    elapsed_seconds: float


@dataclass(frozen=True)
class Summary:
    measurements: tuple[Measurement, ...]

    @property
    def total_bytes(self) -> int:
        return sum(item.downloaded_bytes for item in self.measurements)

    @property
    def total_seconds(self) -> float:
        return sum(item.elapsed_seconds for item in self.measurements)

    @property
    def average_seconds(self) -> float:
        return self.total_seconds / len(self.measurements)

    @property
    def megabytes_per_second(self) -> float:
        return self.total_bytes / self.total_seconds / 1_000_000


class DownloadError(Exception):
    """Ответ не удалось скачать целиком."""


def timed_download(function: Callable[P, int]) -> Callable[P, Measurement]:
    """Преобразует число скачанных байтов в результат с длительностью."""

    @wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Measurement:
        started = perf_counter()
        downloaded_bytes = function(*args, **kwargs)
        return Measurement(downloaded_bytes, perf_counter() - started)

    return wrapper


@timed_download
def download(url: str, timeout: float) -> int:
    request = Request(
        url,
        headers={
            "User-Agent": "net-speed/1.0",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
        },
    )
    downloaded_bytes = 0
    try:
        response = urlopen(request, timeout=timeout)
    except HTTPError as error:
        # HTTPError тоже содержит открытый ответ, его необходимо закрыть.
        error.close()
        raise

    with response:
        while chunk := response.read(CHUNK_SIZE):
            downloaded_bytes += len(chunk)

        # При чтении порциями urllib не всегда сообщает об оборванном ответе.
        content_length = response.headers.get("Content-Length")
        if content_length is not None and downloaded_bytes != int(content_length):
            raise DownloadError(
                f"Неполный ответ: ожидалось {content_length} байт, "
                f"получено {downloaded_bytes}."
            )

    return downloaded_bytes


def measure(url: str, timeout: float) -> Summary:
    measurements = []
    for number in range(1, REQUEST_COUNT + 1):
        try:
            measurements.append(download(url, timeout))
        except (OSError, ValueError, HTTPException, DownloadError) as error:
            raise DownloadError(f"Запрос {number}/{REQUEST_COUNT}: {error}") from error
    return Summary(tuple(measurements))

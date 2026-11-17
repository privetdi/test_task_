"""Аргументы командной строки и вывод результатов."""

import argparse
from http.client import HTTPException
import math
import sys
from urllib.parse import urlsplit

from .measurement import DownloadError, measure


def http_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        # Обращение к port также проверяет корректность номера порта.
        parsed.port
    except ValueError:
        raise argparse.ArgumentTypeError("Укажите корректный HTTP(S) URL.") from None
    return value


def positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError("Таймаут должен быть положительным числом.") from None
    return timeout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="10 последовательных скачиваний для замера скорости HTTP(S)."
    )
    parser.add_argument("url", type=http_url, help="Адрес скачиваемого файла")
    parser.add_argument(
        "--timeout", type=positive_timeout, default=30.0,
        help="Таймаут сетевой операции в секундах (по умолчанию: 30)",
    )
    args = parser.parse_args(argv)

    try:
        summary = measure(args.url, args.timeout)
    except (DownloadError, HTTPException, OSError, ValueError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nЗамер прерван пользователем.", file=sys.stderr)
        return 130

    print(f"Выполнено запросов: {len(summary.measurements)}")
    print(f"Среднее время запроса: {summary.average_seconds:.3f} с")
    print(f"Общее время запросов: {summary.total_seconds:.3f} с")
    print(f"Скачано: {summary.total_bytes} байт")
    print(f"Скорость скачивания: {summary.megabytes_per_second:.3f} MB/s")
    return 0

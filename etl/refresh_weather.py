#!/usr/bin/env python3
"""Download the S5 weather history once into data/weather_cache.json (US-2.5, decision D12).

    python etl/refresh_weather.py                  download (resumes if interrupted), then check
    python etl/refresh_weather.py --check          check the existing cache only; no network
    python etl/refresh_weather.py --print-urls     list the request links (to open in a browser)
    python etl/refresh_weather.py --import-dir D   build the cache from responses saved in folder D

What it fetches: daily maximum temperature and total rainfall for Lahore, Karachi, Islamabad and
Faisalabad, every day of the project window (2023-07-01 to 2026-06-30), from the Open-Meteo
historical archive (https://archive-api.open-meteo.com/v1/archive). Free for non-commercial use,
no key needed. Data licence: CC BY 4.0, "Weather data by Open-Meteo.com".

Only this script ever uses the network. The generator, the tests, CI and the pipeline read the
committed cache (D12), so nobody else needs internet access and every rebuild uses the same numbers.

Why it is built the way it is (the API's known failure modes):

* Rate limits. The free API allows 600 calls a minute, 5,000 an hour and 10,000 a day per IP
  address, and it counts a long date range as several calls. One request per city for three years
  can trip the per-minute limit (HTTP 429). So the window is split into 16 requests (4 cities x 4
  periods: the part-years 2023 and 2026, and the years 2024 and 2025), with a pause between them.
* HTTP 429 "Minutely ... exceeded": wait (Retry-After if given, else a minute) and retry.
  "Hourly" or "Daily ... exceeded": stop at once with a clear message. Nothing is lost: every
  request that already succeeded is kept in data/.weather_parts/, and the next run resumes there.
* Network errors, timeouts and HTTP 5xx: retry with growing waits (up to --retries attempts).
* HTTP 400 (a bad request): stop at once and show the API's reason. Retrying cannot help.
* Bad or partial answers: every response is checked before it is kept (every requested day exactly
  once and in order, the expected units and time zone, numbers in a plausible range). Missing
  values (null) are kept as null and reported: the data dictionary sends them to quarantine (DQ).
* The cache file is written only when all 16 parts are valid, in one atomic step (a temporary file
  renamed over the old one), so a failed run never leaves a half-written cache.
* A network that blocks the API (some university or office networks): run --print-urls, open each
  link in a browser, save each page with the file name shown, then run --import-dir on that folder.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.generator_config import WINDOW_END, WINDOW_START  # noqa: E402
from etl.reference_data import (  # noqa: E402
    WEATHER_CITIES,
    WEATHER_DAILY_VARIABLES,
    WEATHER_TIMEZONE,
    WEATHER_UNITS,
)

API_URL = "https://archive-api.open-meteo.com/v1/archive"
CACHE_FILE = ROOT / "data" / "weather_cache.json"
PARTS_DIR = ROOT / "data" / ".weather_parts"  # ignored by git (data/* is ignored, D12)
CACHE_FORMAT = 1
USER_AGENT = "lue-warehouse/2.5 (DL3004 student project; weather history download)"
UTC_OFFSET_SECONDS = 5 * 3600  # Asia/Karachi has no daylight saving time
# Plausible daily values for these four cities. Anything outside means a broken response.
TEMP_RANGE = (-15.0, 55.0)
RAIN_RANGE = (0.0, 600.0)


class WeatherError(Exception):
    """A failure to explain to the user without a traceback."""


class StopNow(WeatherError):
    """A failure that retrying cannot fix now (bad request, hourly or daily limit reached)."""


# --------------------------------------------------------------------------------------------------
# What to request
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Part:
    """One request: one city, one period."""

    city: str
    latitude: float
    longitude: float
    start: date
    end: date

    @property
    def file_name(self) -> str:
        return f"{self.city.lower()}_{self.start.isoformat()}_{self.end.isoformat()}.json"

    def url(self, base_url: str = API_URL) -> str:
        query = {
            "latitude": f"{self.latitude:.4f}",
            "longitude": f"{self.longitude:.4f}",
            "start_date": self.start.isoformat(),
            "end_date": self.end.isoformat(),
            "daily": ",".join(WEATHER_DAILY_VARIABLES),
            "timezone": WEATHER_TIMEZONE,
        }
        return f"{base_url}?{urllib.parse.urlencode(query)}"


def periods(start: date = WINDOW_START, end: date = WINDOW_END) -> list[tuple[date, date]]:
    """The window cut at calendar-year boundaries: 2023-07..12, 2024, 2025, 2026-01..06."""
    out, first = [], start
    while first <= end:
        last = min(date(first.year, 12, 31), end)
        out.append((first, last))
        first = last + timedelta(days=1)
    return out


def all_parts(start: date = WINDOW_START, end: date = WINDOW_END) -> list[Part]:
    return [
        Part(city, lat, lon, first, last)
        for city, lat, lon in WEATHER_CITIES
        for first, last in periods(start, end)
    ]


def days(first: date, last: date) -> list[str]:
    return [(first + timedelta(n)).isoformat() for n in range((last - first).days + 1)]


# --------------------------------------------------------------------------------------------------
# Checking a response
# --------------------------------------------------------------------------------------------------
def validate_part(part: Part, data: object) -> list[str]:
    """Every problem in one API response (an empty list means it can be kept)."""
    if not isinstance(data, dict):
        return ["the response is not a JSON object"]
    if data.get("error"):
        return [f"the API returned an error: {data.get('reason', 'no reason given')}"]
    problems = []
    if data.get("timezone") != WEATHER_TIMEZONE:
        problems.append(f"timezone is {data.get('timezone')!r}, expected {WEATHER_TIMEZONE!r}")
    if data.get("utc_offset_seconds") != UTC_OFFSET_SECONDS:
        problems.append(f"utc_offset_seconds is {data.get('utc_offset_seconds')!r}, expected 18000")
    daily, units = data.get("daily"), data.get("daily_units")
    if not isinstance(daily, dict) or not isinstance(units, dict):
        return [*problems, "the response has no 'daily' and 'daily_units' sections"]
    expected = days(part.start, part.end)
    got = daily.get("time")
    if got != expected:
        if not isinstance(got, list):
            problems.append("daily.time is missing")
        else:
            missing = sorted(set(expected) - set(got))
            extra = sorted(set(got) - set(expected))
            dupes = len(got) - len(set(got))
            detail = []
            if missing:
                detail.append(f"{len(missing)} day(s) missing, first {missing[0]}")
            if extra:
                detail.append(f"{len(extra)} unexpected day(s), first {extra[0]}")
            if dupes:
                detail.append(f"{dupes} duplicated day(s)")
            if not detail:
                detail.append("days are out of order")
            problems.append("daily.time does not cover the period: " + "; ".join(detail))
    for var in WEATHER_DAILY_VARIABLES:
        values = daily.get(var)
        if units.get(var) != WEATHER_UNITS[var]:
            problems.append(f"{var} is in {units.get(var)!r}, expected {WEATHER_UNITS[var]!r}")
        if not isinstance(values, list) or len(values) != len(expected):
            count = len(values) if isinstance(values, list) else "no"
            problems.append(f"{var} has {count} values, expected {len(expected)}")
            continue
        low, high = TEMP_RANGE if var == "temperature_2m_max" else RAIN_RANGE
        for day, v in zip(expected, values, strict=True):
            if v is None:
                continue  # a missing value: kept and reported, quarantined later (DQ)
            if isinstance(v, bool) or not isinstance(v, int | float) or math.isnan(v):
                problems.append(f"{var} on {day} is not a number: {v!r}")
                break
            if not low <= v <= high:
                problems.append(f"{var} on {day} is {v}, outside the plausible {low} to {high}")
                break
    return problems


# --------------------------------------------------------------------------------------------------
# Downloading one part, politely and with retries
# --------------------------------------------------------------------------------------------------
@dataclass
class Settings:
    base_url: str = API_URL
    pause: float = 3.0  # seconds between requests (keeps far below 600 calls a minute)
    timeout: float = 60.0
    retries: int = 6  # attempts per request
    backoff: float = 5.0  # first wait after an error; doubles each time
    max_wait: float = 120.0  # never wait longer than this between two attempts
    minute_wait: float = 65.0  # wait after "Minutely API request limit exceeded"


def _reason(body: bytes) -> str:
    try:
        return str(json.loads(body.decode("utf-8")).get("reason", "")).strip()
    except (ValueError, AttributeError, UnicodeDecodeError):
        return body[:200].decode("utf-8", "replace").strip()


def _retry_after(headers, default: float) -> float:
    """Seconds from a Retry-After header (a number of seconds), else the default."""
    value = headers.get("Retry-After") if headers is not None else None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default
    return seconds if 0 <= seconds < 86_400 else default


def fetch_part(part: Part, s: Settings, log=print, sleep=time.sleep) -> dict:
    """Download and validate one part; raise StopNow or WeatherError when it cannot be done."""
    url = part.url(s.base_url)
    wait = s.backoff
    last_problem = ""
    for attempt in range(1, s.retries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        retry_after = None
        try:
            with urllib.request.urlopen(
                request, timeout=s.timeout, context=ssl.create_default_context()
            ) as response:
                body = response.read()
            try:
                data = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                last_problem = "the answer was not valid JSON (cut off?)"
            else:
                problems = validate_part(part, data)
                if not problems:
                    return data
                last_problem = "; ".join(problems[:3])
        except urllib.error.HTTPError as exc:
            try:
                reason = _reason(exc.read() or b"")
            except OSError:
                reason = ""
            if exc.code == 400:
                raise StopNow(f"{part.file_name}: the API refused the request (HTTP 400): {reason}")
            if exc.code == 429:
                lowered = reason.lower()
                if "hourly" in lowered or "daily" in lowered or "monthly" in lowered:
                    raise StopNow(
                        f"the API's {('hourly' if 'hourly' in lowered else 'daily')} limit is used "
                        f"up ({reason}). Everything downloaded so far is kept: run this again "
                        f"{'in an hour' if 'hourly' in lowered else 'tomorrow'} and it resumes."
                    )
                retry_after = _retry_after(exc.headers, s.minute_wait)
                last_problem = f"HTTP 429 rate limit ({reason or 'too many requests'})"
            else:
                last_problem = f"HTTP {exc.code} {reason}".strip()
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            detail = getattr(exc, "reason", exc)
            if isinstance(detail, ssl.SSLCertVerificationError):
                raise StopNow(
                    f"the secure connection was refused ({detail}). Your network may be "
                    "intercepting HTTPS. Use --print-urls and a browser instead (see --help)."
                ) from None
            last_problem = f"network problem: {detail}"
        if attempt == s.retries:
            break
        delay = min(retry_after if retry_after is not None else wait, s.max_wait)
        log(f"         attempt {attempt} failed: {last_problem}; retrying in {delay:.0f}s")
        sleep(delay)
        wait = min(wait * 2, s.max_wait)
    raise WeatherError(f"{part.file_name}: gave up after {s.retries} attempts: {last_problem}")


# --------------------------------------------------------------------------------------------------
# Building, writing and checking the cache
# --------------------------------------------------------------------------------------------------
def load_part_file(part: Part, path: Path) -> dict | None:
    """A saved part, if it exists and is still valid; otherwise None."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))  # browsers may add a BOM
    except (ValueError, OSError):
        return None
    return data if not validate_part(part, data) else None


def assemble(parts: list[Part], responses: dict[Part, dict], retrieved_at: str) -> dict:
    """The cache: one record per city in Open-Meteo's own daily shape, periods joined in order."""
    cities = []
    for city, lat, lon in WEATHER_CITIES:
        mine = [p for p in parts if p.city == city]
        first = responses[mine[0]]
        daily = {"time": []} | {v: [] for v in WEATHER_DAILY_VARIABLES}
        for p in mine:
            for key in daily:
                daily[key].extend(responses[p]["daily"][key])
        cities.append(
            {
                "city": city,
                "requested_latitude": lat,
                "requested_longitude": lon,
                "latitude": first.get("latitude"),
                "longitude": first.get("longitude"),
                "elevation": first.get("elevation"),
                "timezone": first.get("timezone"),
                "utc_offset_seconds": first.get("utc_offset_seconds"),
                "daily_units": {"time": "iso8601"}
                | {v: WEATHER_UNITS[v] for v in WEATHER_DAILY_VARIABLES},
                "daily": daily,
            }
        )
    return {
        "format": CACHE_FORMAT,
        "source": {
            "system": "S5",
            "name": "Open-Meteo Historical Weather API",
            "url": API_URL,
            "licence": "CC BY 4.0",
            "attribution": "Weather data by Open-Meteo.com",
            "daily_variables": list(WEATHER_DAILY_VARIABLES),
            "timezone": WEATHER_TIMEZONE,
        },
        "window": {
            "start": min(p.start for p in parts).isoformat(),
            "end": max(p.end for p in parts).isoformat(),
        },
        "retrieved_at_utc": retrieved_at,
        "requests": [p.url() for p in parts],
        "cities": cities,
    }


def to_json(cache: dict) -> str:
    """Stable text: same data, same bytes. Each daily series is one line (not 1,096 lines)."""
    series = {}
    shallow = json.loads(json.dumps(cache))
    for i, c in enumerate(shallow["cities"]):
        for key, values in c["daily"].items():
            token = f"@@series_{i}_{key}@@"
            series[f'"{token}"'] = json.dumps(values, separators=(",", ":"))
            c["daily"][key] = token
    text = json.dumps(shallow, indent=2, ensure_ascii=False)
    for token, values in series.items():
        text = text.replace(token, values)
    return text + "\n"


def write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)  # one step: the old cache stays complete until the new one is ready


@dataclass
class CacheReport:
    ok: bool
    lines: list[str]
    null_values: int = 0


def check_cache(path: Path, start: date = WINDOW_START, end: date = WINDOW_END) -> CacheReport:
    """Does the cache cover every city and every day? Missing (null) values are counted."""
    if not path.is_file():
        return CacheReport(False, [f"{path} does not exist; run: python etl/refresh_weather.py"])
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return CacheReport(False, [f"{path} is not readable JSON: {exc}"])
    if not isinstance(cache, dict) or not isinstance(cache.get("cities"), list):
        return CacheReport(False, [f"{path} is not a weather cache (no 'cities' list)"])
    lines, ok, nulls = [], True, 0
    expected = days(start, end)
    by_city = {c.get("city"): c for c in cache.get("cities", []) if isinstance(c, dict)}
    lines.append(
        f"{'city':<12}{'days':>6}{'first':>12}{'last':>12}{'null temp':>11}{'null rain':>11}"
        f"{'max temp':>10}{'max rain':>10}"
    )
    for city, _lat, _lon in WEATHER_CITIES:
        c = by_city.get(city)
        if c is None:
            lines.append(f"{city:<12} MISSING from the cache")
            ok = False
            continue
        daily = c.get("daily", {})
        time_ = daily.get("time", [])
        temps = daily.get("temperature_2m_max", [])
        rains = daily.get("precipitation_sum", [])
        if time_ != expected or len(temps) != len(expected) or len(rains) != len(expected):
            missing = len(set(expected) - set(time_))
            lines.append(
                f"{city:<12} does NOT cover the window: {len(time_)} days, {missing} missing"
            )
            ok = False
            continue
        t = [v for v in temps if v is not None]
        r = [v for v in rains if v is not None]
        nulls += (len(temps) - len(t)) + (len(rains) - len(r))
        lines.append(
            f"{city:<12}{len(time_):>6}{time_[0]:>12}{time_[-1]:>12}{len(temps) - len(t):>11}"
            f"{len(rains) - len(r):>11}{max(t) if t else 'n/a':>10}{max(r) if r else 'n/a':>10}"
        )
    extra = sorted(set(by_city) - {c[0] for c in WEATHER_CITIES})
    if extra:
        lines.append(f"unexpected cities in the cache: {', '.join(map(str, extra))}")
        ok = False
    lines.append(
        f"window {start} to {end}: {len(expected)} days x {len(WEATHER_CITIES)} cities = "
        f"{len(expected) * len(WEATHER_CITIES)} city-days expected"
    )
    return CacheReport(ok, lines, nulls)


def load_cache(path: Path = CACHE_FILE) -> list[tuple[str, str, float | None, float | None]]:
    """(city, date, rainfall_mm, max_temp_c) rows, for the S5 ingestion (US-3.4) and tests."""
    cache = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for c in cache["cities"]:
        d = c["daily"]
        for day, temp, rain in zip(
            d["time"], d["temperature_2m_max"], d["precipitation_sum"], strict=True
        ):
            rows.append((c["city"], day, rain, temp))
    return rows


# --------------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------------
def download(
    s: Settings, cache: Path, parts_dir: Path, fresh: bool, log=print, sleep=time.sleep
) -> int:
    parts = all_parts()
    parts_dir.mkdir(parents=True, exist_ok=True)
    if fresh:
        for p in parts:
            (parts_dir / p.file_name).unlink(missing_ok=True)
    responses: dict[Part, dict] = {}
    fetched = 0
    log(f"Downloading {len(parts)} parts from {s.base_url}")
    for i, p in enumerate(parts, 1):
        saved = load_part_file(p, parts_dir / p.file_name)
        if saved is not None:
            responses[p] = saved
            log(f"  [{i:>2}/{len(parts)}] {p.file_name}: already downloaded")
            continue
        if fetched:
            sleep(s.pause)
        data = fetch_part(p, s, log=log, sleep=sleep)
        write_atomically(parts_dir / p.file_name, json.dumps(data) + "\n")
        responses[p] = data
        fetched += 1
        log(f"  [{i:>2}/{len(parts)}] {p.file_name}: OK")
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_atomically(cache, to_json(assemble(parts, responses, retrieved)))
    log(f"Wrote {cache}")
    return 0


def import_dir(folder: Path, cache: Path, log=print) -> int:
    parts = all_parts()
    responses, problems = {}, []
    for p in parts:
        path = folder / p.file_name
        if not path.is_file():
            problems.append(f"{p.file_name}: not found in {folder}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as exc:
            problems.append(f"{p.file_name}: not valid JSON ({exc})")
            continue
        bad = validate_part(p, data)
        if bad:
            problems.append(f"{p.file_name}: {'; '.join(bad[:2])}")
        else:
            responses[p] = data
    if problems:
        for line in problems:
            log(f"  [FAIL] {line}")
        raise WeatherError(
            f"{len(problems)} of {len(parts)} files are missing or invalid; cache not changed"
        )
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_atomically(cache, to_json(assemble(parts, responses, retrieved)))
    log(f"Imported {len(parts)} files from {folder}; wrote {cache}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("\n\n", 1)[1],
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="check the cache only (no network)")
    mode.add_argument("--print-urls", action="store_true", help="print the request links and exit")
    mode.add_argument("--import-dir", type=Path, help="build the cache from saved responses")
    p.add_argument("--cache", type=Path, default=CACHE_FILE, help="cache file to write or check")
    p.add_argument("--parts-dir", type=Path, default=PARTS_DIR, help="downloaded parts folder")
    p.add_argument("--fresh", action="store_true", help="ignore parts already downloaded")
    p.add_argument("--strict", action="store_true", help="also fail --check on missing values")
    p.add_argument("--pause", type=float, default=Settings.pause, help="seconds between requests")
    p.add_argument("--timeout", type=float, default=Settings.timeout, help="seconds per request")
    p.add_argument("--retries", type=int, default=Settings.retries, help="attempts per request")
    p.add_argument("--base-url", default=API_URL, help=argparse.SUPPRESS)  # for the tests
    p.add_argument("--backoff", type=float, default=Settings.backoff, help=argparse.SUPPRESS)
    p.add_argument(
        "--minute-wait", type=float, default=Settings.minute_wait, help=argparse.SUPPRESS
    )
    return p


def report(cache: Path, strict: bool) -> int:
    result = check_cache(cache)
    for line in result.lines:
        print(f"  {line}")
    if result.ok and result.null_values:
        print(f"  note: {result.null_values} missing value(s) from the API; DQ quarantines them")
    if result.ok and strict and result.null_values:
        print("RESULT: FAIL (--strict: some values are missing)")
        return 1
    print("RESULT: " + ("PASS: the cache covers every city and every day" if result.ok else "FAIL"))
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.retries < 1 or args.pause < 0 or args.timeout <= 0:
        print("refresh_weather: --retries must be at least 1, --pause and --timeout positive")
        return 2
    try:
        if args.print_urls:
            print("Open each link in a browser and save the page into one folder, named as shown.")
            print("Then run: python etl/refresh_weather.py --import-dir <that folder>\n")
            for part in all_parts():
                print(f"{part.file_name}\n  {part.url(args.base_url)}")
            return 0
        if args.check:
            return report(args.cache, args.strict)
        if args.import_dir:
            import_dir(args.import_dir, args.cache)
        else:
            settings = Settings(
                base_url=args.base_url,
                pause=args.pause,
                timeout=args.timeout,
                retries=args.retries,
                backoff=args.backoff,
                minute_wait=args.minute_wait,
            )
            download(settings, args.cache, args.parts_dir, args.fresh)
    except WeatherError as exc:
        print(f"refresh_weather: {exc}")
        print("RESULT: FAIL (the cache was not changed)")
        return 1
    return report(args.cache, args.strict)


if __name__ == "__main__":
    sys.exit(main())

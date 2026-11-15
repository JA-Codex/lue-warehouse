#!/usr/bin/env python3
"""Acceptance tests for the S5 weather download and cache (US-2.5). No internet needed.

    python scripts/test_weather.py

A local stand-in for the Open-Meteo archive API runs on 127.0.0.1 and answers exactly like the real
one (same JSON shape, same error bodies). It can be told to misbehave: rate limits (HTTP 429),
server errors, timeouts, bad requests, missing days, wrong units, cut-off answers, impossible
values and missing values. Each failure the real API can produce is tested here, so the download
cannot break in a way nobody has seen. The last section checks the committed
data/weather_cache.json itself.
"""

from __future__ import annotations

import io
import json
import math
import re
import shutil
import sys
import tempfile
import threading
import time
from contextlib import redirect_stdout
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import etl.refresh_weather as rw  # noqa: E402
from etl.generator_config import WINDOW_END, WINDOW_START  # noqa: E402
from etl.reference_data import WEATHER_CITIES  # noqa: E402

results: list[bool] = []
WINDOW_DAYS = (WINDOW_END - WINDOW_START).days + 1  # 1,096


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


# --------------------------------------------------------------------------------------------------
# The stand-in API
# --------------------------------------------------------------------------------------------------
class FakeOpenMeteo:
    """Answers like archive-api.open-meteo.com. `plan` is a list of behaviours, one per request;
    when it runs out every request succeeds. Behaviours: ok, minute429, minute429_retry_after,
    hourly429, daily429, error500, slow, bad400, missing_day, duplicate_day, wrong_units,
    truncated, impossible, nulls, wrong_timezone."""

    def __init__(self):
        self.plan: list[str] = []
        self.requests: list[dict] = []
        self.lock = threading.Lock()
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/archive"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def reset(self, plan=()):
        with self.lock:
            self.plan = list(plan)
            self.requests = []

    @staticmethod
    def values(lat: float, day: date) -> tuple[float, float]:
        """Deterministic plausible weather: hot summers, monsoon rain, cooler north."""
        doy = day.timetuple().tm_yday
        temp = 31.0 - (lat - 30) * 0.9 + 9.0 * math.sin((doy - 105) / 365 * 2 * math.pi)
        wet = 0.55 if 182 <= doy <= 258 else 0.08
        rain = ((doy * 37 + int(lat * 10)) % 100) / 100
        return round(temp, 1), (round(rain * 60, 1) if rain < wet else 0.0)

    def body(self, q: dict, behaviour: str) -> tuple[int, dict | str, dict]:
        lat, lon = float(q["latitude"][0]), float(q["longitude"][0])
        first = date.fromisoformat(q["start_date"][0])
        last = date.fromisoformat(q["end_date"][0])
        days = [first + timedelta(n) for n in range((last - first).days + 1)]
        temps = [self.values(lat, d)[0] for d in days]
        rains = [self.values(lat, d)[1] for d in days]
        units = {"time": "iso8601", "temperature_2m_max": "°C", "precipitation_sum": "mm"}
        tz = q.get("timezone", ["GMT"])[0]
        if behaviour == "minute429":
            return (
                429,
                {
                    "error": True,
                    "reason": "Minutely API request limit exceeded. Please "
                    "try again in one minute.",
                },
                {},
            )
        if behaviour == "minute429_retry_after":
            return (
                429,
                {"error": True, "reason": "Minutely API request limit exceeded."},
                {"Retry-After": "7"},
            )
        if behaviour == "hourly429":
            return (
                429,
                {
                    "error": True,
                    "reason": "Hourly API request limit exceeded. Please try "
                    "again in the next hour.",
                },
                {},
            )
        if behaviour == "daily429":
            return (
                429,
                {
                    "error": True,
                    "reason": "Daily API request limit exceeded. Please try again tomorrow.",
                },
                {},
            )
        if behaviour == "error500":
            return 502, "<html>Bad Gateway</html>", {}
        if behaviour == "bad400":
            return (
                400,
                {
                    "error": True,
                    "reason": "Parameter 'start_date' is out of allowed "
                    "range from 1940-01-01 to 2026-11-10",
                },
                {},
            )
        if behaviour == "missing_day":
            del days[len(days) // 2], temps[len(temps) // 2], rains[len(rains) // 2]
        if behaviour == "duplicate_day":  # right count, wrong dates: one day twice, one missing
            days[10] = days[9]
        if behaviour == "wrong_units":
            units["temperature_2m_max"] = "°F"
        if behaviour == "impossible":
            temps[3] = 412.0
        if behaviour == "nulls":
            temps[5] = None
            rains[6] = None
        if behaviour == "wrong_timezone":
            tz = "GMT"
        data = {
            "latitude": round(lat * 4) / 4 + 0.00418,
            "longitude": round(lon * 4) / 4 - 0.0098,
            "generationtime_ms": 1.234,
            "utc_offset_seconds": 18000 if tz == "Asia/Karachi" else 0,
            "timezone": tz,
            "timezone_abbreviation": "GMT+5" if tz == "Asia/Karachi" else "GMT",
            "elevation": 217.0,
            "daily_units": units,
            "daily": {
                "time": [d.isoformat() for d in days],
                "temperature_2m_max": temps,
                "precipitation_sum": rains,
            },
        }
        if behaviour == "truncated":
            return 200, json.dumps(data)[:500], {}
        return 200, data, {}

    def _handler(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep the test output clean
                pass

            def do_GET(self):  # noqa: N802 (the http.server API name)
                q = parse_qs(urlparse(self.path).query)
                with api.lock:
                    behaviour = api.plan.pop(0) if api.plan else "ok"
                    api.requests.append({"query": q, "behaviour": behaviour})
                if behaviour == "slow":
                    time.sleep(1.5)
                status, payload, headers = api.body(q, behaviour)
                raw = payload if isinstance(payload, str) else json.dumps(payload)
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw.encode())))
                self.end_headers()
                try:
                    self.wfile.write(raw.encode())
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the client gave up (the timeout test)

        return Handler


# --------------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------------
def settings(api: FakeOpenMeteo, **kw) -> rw.Settings:
    base = {
        "base_url": api.url,
        "pause": 0,
        "timeout": 1.0,
        "retries": 4,
        "backoff": 0.01,
        "max_wait": 0.05,
        "minute_wait": 0.02,
    }
    return rw.Settings(**(base | kw))


def run_download(api, tmp: Path, fresh=False, **kw):
    """Run a download; return (exit code or exception, log text, recorded sleeps)."""
    log, sleeps = [], []
    try:
        code = rw.download(
            settings(api, **kw),
            tmp / "cache.json",
            tmp / "parts",
            fresh,
            log=log.append,
            sleep=sleeps.append,
        )
    except rw.WeatherError as exc:
        code = exc
    return code, "\n".join(log), sleeps


def cli(*args) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = rw.main([str(a) for a in args])
    return code, out.getvalue()


def data_without_time(path: Path) -> dict:
    cache = json.loads(path.read_text(encoding="utf-8"))
    cache.pop("retrieved_at_utc")
    return cache


# --------------------------------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------------------------------
def main() -> int:
    print("=" * 70)
    print(" US-2.5 weather tests: download, failure handling and the cache")
    print("=" * 70)
    api = FakeOpenMeteo()
    tmp_root = Path(tempfile.mkdtemp(prefix="lue_weather_"))
    try:
        parts = rw.all_parts()
        print("Request plan (stays far below the free API's limits)")
        check(len(parts) == 16, f"{len(parts)} requests: 4 cities x 4 periods")
        per_city = {
            c: sum((p.end - p.start).days + 1 for p in parts if p.city == c)
            for c, *_ in WEATHER_CITIES
        }
        check(
            set(per_city.values()) == {WINDOW_DAYS} and len(per_city) == 4,
            f"each city's periods cover the window exactly ({WINDOW_DAYS} days, no overlap)",
        )
        check(
            all(p.start.year == p.end.year for p in parts),
            "no request spans more than one calendar year (a light request weight)",
        )
        url = parts[0].url()
        check(
            url.startswith(rw.API_URL)
            and "timezone=Asia%2FKarachi" in url
            and "temperature_2m_max" in url
            and "precipitation_sum" in url,
            "requests ask for max temperature and rainfall, in Pakistan time (D13)",
        )
        check(
            rw.Settings().pause >= 1 and rw.Settings().minute_wait >= 60,
            "defaults pause between requests and wait over a minute after a minute limit",
        )

        print("A clean download")
        tmp = tmp_root / "clean"
        api.reset()
        code, log, sleeps = run_download(api, tmp)
        cache = tmp / "cache.json"
        report = rw.check_cache(cache)
        check(code == 0 and len(api.requests) == 16, "16 requests, exit code 0")
        check(report.ok and report.null_values == 0, "the cache covers every city and every day")
        rows = rw.load_cache(cache)
        check(
            len(rows) == WINDOW_DAYS * 4 and len({(c, d) for c, d, *_ in rows}) == len(rows),
            f"{len(rows)} city-days, each exactly once (the S5 grain: city + date)",
        )
        doc = json.loads(cache.read_text(encoding="utf-8"))
        check(
            doc["source"]["licence"] == "CC BY 4.0"
            and "Open-Meteo" in doc["source"]["attribution"],
            "the cache records the source and its licence",
        )
        check(
            all(
                c["timezone"] == "Asia/Karachi" and c["daily_units"]["precipitation_sum"] == "mm"
                for c in doc["cities"]
            ),
            "each city keeps Open-Meteo's own fields and units",
        )
        lines = cache.read_text(encoding="utf-8").count("\n")
        check(lines < 200, f"the file stays readable: {lines} lines, one per daily series")
        check(
            cache.read_bytes().endswith(b"\n") and b"\r\n" not in cache.read_bytes(),
            "UTF-8 with \\n line ends (identical on Windows and Linux)",
        )
        check(len(list((tmp / "parts").glob("*.json"))) == 16, "all 16 parts are kept for resuming")
        check(not list(tmp.glob("*.tmp")), "no temporary file is left behind")

        print("Resume and rerun")
        before = data_without_time(cache)
        api.reset()
        code, log, _ = run_download(api, tmp)
        check(code == 0 and len(api.requests) == 0, "a rerun with all parts saved makes 0 requests")
        check(data_without_time(cache) == before, "and rebuilds the same cache content")
        api.reset()
        code, _, _ = run_download(api, tmp, fresh=True)
        check(
            code == 0 and len(api.requests) == 16 and data_without_time(cache) == before,
            "--fresh downloads all 16 again and gets the same content",
        )

        print("Rate limits (HTTP 429)")
        tmp = tmp_root / "minute"
        api.reset(["minute429", "minute429"])
        code, log, sleeps = run_download(api, tmp)
        check(
            code == 0 and rw.check_cache(tmp / "cache.json").ok,
            "two 'minutely limit' answers in a row: waits, retries, completes",
        )
        check("429" in log and "retrying" in log, "the log says what happened and that it retried")
        api.reset(["minute429_retry_after"])
        log_list, sleeps = [], []
        data = rw.fetch_part(
            parts[0], settings(api, max_wait=30), log=log_list.append, sleep=sleeps.append
        )
        check(
            sleeps == [7.0] and data["daily"]["time"][0] == "2023-07-01",
            "a Retry-After header is obeyed (waited exactly 7 s)",
        )

        tmp = tmp_root / "hourly"
        tmp.mkdir()
        (tmp / "cache.json").write_text('{"old": "cache"}\n', encoding="utf-8")
        api.reset(["ok"] * 5 + ["hourly429"])
        code, log, _ = run_download(api, tmp)
        check(
            isinstance(code, rw.StopNow) and "hourly" in str(code) and "resumes" in str(code),
            "an 'hourly limit' answer stops at once with a clear message (no pointless retries)",
        )
        check(len(api.requests) == 6, "it stopped on the 6th request, without retrying it")
        check(
            (tmp / "cache.json").read_text() == '{"old": "cache"}\n',
            "the existing cache is untouched by the failed run",
        )
        check(len(list((tmp / "parts").glob("*.json"))) == 5, "the 5 finished parts are kept")
        api.reset()
        code, _, _ = run_download(api, tmp)
        check(
            code == 0 and len(api.requests) == 11 and rw.check_cache(tmp / "cache.json").ok,
            "the next run resumes: only the 11 missing parts are requested",
        )
        api.reset(["daily429"])
        code, _, _ = run_download(api, tmp_root / "daily")
        check(
            isinstance(code, rw.StopNow) and "tomorrow" in str(code),
            "a 'daily limit' answer stops and says to try tomorrow",
        )

        print("Network and server failures")
        for plan, text in (
            (["error500", "error500"], "two server errors (HTTP 502)"),
            (["slow"], "a request that times out"),
            (["truncated"], "an answer cut off in the middle"),
        ):
            tmp = tmp_root / plan[0]
            api.reset(plan)
            code, log, _ = run_download(api, tmp)
            check(
                code == 0 and rw.check_cache(tmp / "cache.json").ok,
                f"{text}: retried, then completes",
            )
        tmp = tmp_root / "dead"
        api.reset(["error500"] * 50)
        code, log, sleeps = run_download(api, tmp, retries=3)
        check(
            isinstance(code, rw.WeatherError) and "gave up after 3 attempts" in str(code),
            "a server that keeps failing: gives up after --retries attempts with the reason",
        )
        check(sleeps == sorted(sleeps) and len(sleeps) == 2, "waits grow between attempts")
        check(not (tmp / "cache.json").exists(), "and writes no cache")
        dead = rw.Settings(
            base_url="http://127.0.0.1:9/v1/archive",
            pause=0,
            timeout=0.5,
            retries=2,
            backoff=0.01,
            max_wait=0.01,
        )
        try:
            rw.fetch_part(parts[0], dead, log=lambda *_: None, sleep=lambda *_: None)
            check(False, "no server at all: a clear network error")
        except rw.WeatherError as exc:
            check("network problem" in str(exc), "no server at all: a clear network error")

        print("Certificate problems (seen on a Windows laptop: 'certificate has expired')")
        real_open, real_contexts = rw.urllib.request.urlopen, rw.ssl_contexts
        first, second = object(), object()
        good = json.dumps(
            api.body(
                {
                    "latitude": ["31.5204"],
                    "longitude": ["74.3587"],
                    "start_date": [parts[0].start.isoformat()],
                    "end_date": [parts[0].end.isoformat()],
                    "timezone": ["Asia/Karachi"],
                },
                "ok",
            )[1]
        ).encode()

        class Answer(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_open(refuse, other_error=False):
            used = []

            def urlopen(request, timeout=None, context=None):
                used.append(context)
                if context in refuse:
                    if other_error:
                        raise rw.urllib.error.URLError(ConnectionResetError("reset"))
                    raise rw.urllib.error.URLError(
                        rw.ssl.SSLCertVerificationError("certificate has expired")
                    )
                return Answer(good)

            return urlopen, used

        try:
            rw.ssl_contexts = lambda: [("certifi", first), ("system", second)]
            rw.urllib.request.urlopen, used = fake_open({first})
            data = rw.fetch_part(
                parts[0], settings(api), log=lambda *_: None, sleep=lambda *_: None
            )
            check(
                used == [first, second] and data["daily"]["time"][0] == "2023-07-01",
                "one certificate list refuses: the other is tried and the download works",
            )
            rw.urllib.request.urlopen, used = fake_open({first, second})
            try:
                rw.fetch_part(parts[0], settings(api), log=lambda *_: None, sleep=lambda *_: None)
                check(False, "both lists refuse: stops with advice (clock, then browser route)")
            except rw.StopNow as exc:
                text = str(exc)
                check(
                    "date and time" in text
                    and "--print-urls" in text
                    and "certifi and system" in text
                    and used == [first, second],
                    "both lists refuse: stops with advice (clock, then browser route)",
                )
            rw.urllib.request.urlopen, used = fake_open({first}, other_error=True)
            try:
                rw.fetch_part(
                    parts[0], settings(api, retries=2), log=lambda *_: None, sleep=lambda *_: None
                )
            except rw.WeatherError:
                pass
            check(
                used == [first, first],
                "other network errors are retried, not hidden by the certificate fallback",
            )
        finally:
            rw.urllib.request.urlopen, rw.ssl_contexts = real_open, real_contexts
        names = [n for n, _ in rw.ssl_contexts()]
        check(
            names[-1] == "system" and set(names) <= {"certifi", "system"},
            "certifi's list is tried first when installed, then the operating system's "
            f"(here: {', '.join(names)})",
        )

        print("Bad answers are never kept")
        api.reset(["bad400"])
        tmp = tmp_root / "bad400"
        code, _, _ = run_download(api, tmp)
        check(
            isinstance(code, rw.StopNow)
            and "out of allowed range" in str(code)
            and len(api.requests) == 1,
            "HTTP 400 stops at once and shows the API's reason",
        )
        for behaviour, text in (
            ("missing_day", "a day missing from the answer"),
            ("duplicate_day", "right number of days, but one repeated and one missing"),
            ("wrong_units", "temperature in the wrong unit"),
            ("impossible", "an impossible value (412 C)"),
            ("wrong_timezone", "the wrong time zone"),
        ):
            api.reset([behaviour] * 10)
            try:
                rw.fetch_part(
                    parts[1], settings(api, retries=2), log=lambda *_: None, sleep=lambda *_: None
                )
                check(False, f"{text}: rejected")
            except rw.WeatherError as exc:
                check(
                    "gave up" in str(exc), f"{text}: rejected ({str(exc).split(': ', 2)[-1][:60]})"
                )
        problems = rw.validate_part(parts[0], {"error": True, "reason": "x"})
        check(
            problems and "x" in problems[0], "an error body with HTTP 200 is not mistaken for data"
        )

        print("Missing values (the API's own nulls)")
        tmp = tmp_root / "nulls"
        api.reset(["nulls"])
        code, _, _ = run_download(api, tmp)
        rep = rw.check_cache(tmp / "cache.json")
        check(
            code == 0 and rep.ok and rep.null_values == 2,
            "nulls are kept and counted (2), not invented: DQ quarantines them (dictionary)",
        )
        c1, out1 = cli("--check", "--cache", tmp / "cache.json")
        c2, out2 = cli("--check", "--strict", "--cache", tmp / "cache.json")
        check(
            c1 == 0 and "missing value" in out1 and c2 == 1,
            "--check passes and notes them; --check --strict fails",
        )

        print("Offline route for blocked networks (--print-urls, --import-dir)")
        code, out = cli("--print-urls")
        urls = re.findall(r"^  (https://\S+)$", out, re.M)
        names = re.findall(r"^(\w+_\d{4}-\d\d-\d\d_\d{4}-\d\d-\d\d\.json)$", out, re.M)
        check(code == 0 and len(urls) == 16 and len(names) == 16, "--print-urls lists 16 links")
        saved = tmp_root / "browser"
        shutil.copytree(tmp_root / "clean" / "parts", saved)
        first = saved / parts[0].file_name
        first.write_bytes(b"\xef\xbb\xbf" + first.read_bytes())  # a browser that adds a BOM
        target = tmp_root / "imported.json"
        code, out = cli("--import-dir", saved, "--cache", target)
        check(
            code == 0
            and data_without_time(target) == data_without_time(tmp_root / "clean" / "cache.json"),
            "--import-dir builds the same cache from saved files",
        )
        (saved / parts[3].file_name).unlink()
        target.write_text("KEEP\n", encoding="utf-8")
        code, out = cli("--import-dir", saved, "--cache", target)
        check(
            code == 1 and parts[3].file_name in out and target.read_text() == "KEEP\n",
            "a missing file is named, and the existing cache is not changed",
        )

        print("--check catches a damaged cache")
        good = json.loads((tmp_root / "clean" / "cache.json").read_text(encoding="utf-8"))
        broken = json.loads(json.dumps(good))
        broken["cities"] = broken["cities"][:3]
        (tmp_root / "b1.json").write_text(json.dumps(broken), encoding="utf-8")
        broken = json.loads(json.dumps(good))
        for key in ("time", "temperature_2m_max", "precipitation_sum"):
            del broken["cities"][2]["daily"][key][400]
        (tmp_root / "b2.json").write_text(json.dumps(broken), encoding="utf-8")
        (tmp_root / "b3.json").write_text('{"cities": ', encoding="utf-8")
        for name, text in (("b1", "a city missing"), ("b2", "a day missing"), ("b3", "not JSON")):
            ok = rw.check_cache(tmp_root / f"{name}.json").ok
            check(not ok, f"{text}: --check fails")

        print("Nothing else uses the network (D12)")
        offenders = []
        for f in sorted((ROOT / "etl").glob("*.py")) + sorted((ROOT / "scripts").glob("db_*.py")):
            if f.name == "refresh_weather.py":
                continue
            text = f.read_text(encoding="utf-8")
            if re.search(
                r"^\s*(import|from)\s+(urllib|requests|http\.client|socket)\b", text, re.M
            ):
                offenders.append(f.name)
        check(
            not offenders,
            "only etl/refresh_weather.py imports a network library"
            + (f" (also: {offenders})" if offenders else ""),
        )
    finally:
        api.close()
        shutil.rmtree(tmp_root, ignore_errors=True)

    print("The committed cache (data/weather_cache.json)")
    report = rw.check_cache(rw.CACHE_FILE)
    for line in report.lines:
        print(f"         {line}")
    check(report.ok, "the committed cache covers every city and every day of the window")
    if report.ok:
        doc = json.loads(rw.CACHE_FILE.read_text(encoding="utf-8"))
        check(
            [c["city"] for c in doc["cities"]] == [c[0] for c in WEATHER_CITIES],
            "it holds the four cities in the reference order",
        )
        check(doc["requests"][0].startswith(rw.API_URL), "it records the real API request links")

    print("=" * 70)
    print(
        f" RESULT: {sum(results)}/{len(results)} checks passed"
        + ("" if results and all(results) else " - FAILED")
    )
    print("=" * 70)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Acceptance tests for US-2.1 (generator framework, configuration and seeding).

    python scripts/test_generator.py

Needs no database. Generates into temporary folders and deletes them afterwards.
Covers the three acceptance criteria of the plan (small profile under a minute, same seed gives
identical hashes, a different seed gives different data) plus the rules later stories rely on.
"""

import dataclasses
import hashlib
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import etl.generate_data as gd  # noqa: E402
from etl import generator_config as cfg  # noqa: E402

SCRIPT = ROOT / "etl" / "generate_data.py"
results: list[bool] = []


def check(ok: bool, text: str) -> None:
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")


def cli(*args, cwd=None):
    """Run the generator as a user would; return (exit code, seconds, stdout, stderr)."""
    start = time.perf_counter()
    p = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return p.returncode, time.perf_counter() - start, p.stdout, p.stderr


def tree_bytes(out: Path) -> dict[str, bytes]:
    """Every generated file's bytes, keyed by relative path (the manifest files are separate)."""
    return {
        p.relative_to(out).as_posix(): p.read_bytes()
        for folder in gd.OWNED_DIRS
        if (out / folder).is_dir()
        for p in sorted((out / folder).rglob("*"))
        if p.is_file()
    }


def main() -> int:
    print("=" * 70)
    print(" US-2.1 acceptance tests: generator framework, configuration and seeding")
    print("=" * 70)
    with tempfile.TemporaryDirectory(prefix="lue_gen_test_") as tmp:
        tmp = Path(tmp)
        small = cfg.get_profile("small")

        print("Configuration")
        full = cfg.get_profile("full")
        check(sorted(cfg.PROFILES) == ["full", "small"], "two profiles exist: small and full")
        check(
            (small.buildings, small.months) == (2, 3),
            "small profile: 2 buildings, 3 months (plan E2)",
        )
        check(
            (full.buildings, full.units, full.months) == (40, 1800, 36),
            "full profile: 40 buildings, 1,800 units, 36 months (plan E2)",
        )
        check(
            (full.window_start, full.window_end) == (cfg.WINDOW_START, cfg.WINDOW_END)
            and str(cfg.WINDOW_START) == "2023-07-01"
            and str(cfg.WINDOW_END) == "2026-06-30",
            "full window is 2023-07-01 to 2026-06-30",
        )
        check(
            small.window_start >= cfg.WINDOW_START and small.window_end == cfg.WINDOW_END,
            "the small window lies inside the full window and ends with it",
        )
        check(
            (full.target_active_leases, full.target_invoice_lines) == (1500, 130_000)
            and (full.target_payments, full.target_tickets) == (60_000, 6000),
            "full targets: 1,500 leases, 130,000 invoice lines, 60,000 payments, 6,000 tickets",
        )
        rates = full.defect_rates.values()
        check(
            len(full.defect_rates) == 12 and all(0.01 <= r <= 0.03 for r in rates),
            "12 defect types, every rate between 1 and 3 percent (plan US-2.6)",
        )
        check(
            all(not cfg.validate(p) for p in cfg.PROFILES.values()),
            "both shipped profiles pass validation",
        )
        bad = [
            dataclasses.replace(small, window_start=cfg.WINDOW_END, window_end=cfg.WINDOW_START),
            dataclasses.replace(small, units=0),
            dataclasses.replace(small, target_active_leases=small.units + 1),
            dataclasses.replace(small, defect_rates={"exact_duplicate": 0.5}),
        ]
        check(
            all(cfg.validate(p) for p in bad),
            "validation rejects a reversed window, zero units, too many leases, a 50% defect rate",
        )
        try:
            cfg.get_profile("huge")
            raised = False
        except ValueError:
            raised = True
        check(raised, "an unknown profile name is refused")

        print("Output folders and manifest")
        out_a = tmp / "a"
        code, secs, stdout, _ = cli("--profile", "small", "--seed", 3004, "--out", out_a)
        check(code == 0, "the small profile runs and exits 0")
        check(
            all((out_a / s).is_dir() for s in ("s1", "s2", "s3", "s4", "s5", "s6")),
            "folders s1 to s6 are created",
        )
        check((out_a / "answer_key").is_dir(), "folder answer_key is created (filled by US-2.6)")
        manifest = gd.json.loads((out_a / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
        check(
            manifest["seed"] == 3004 and manifest["profile"]["name"] == "small",
            "the manifest records the seed and the profile",
        )
        check(
            manifest["files"]
            and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in manifest["files"].values()),
            "the manifest lists every generated file with a SHA-256",
        )
        recomputed = {
            k: hashlib.sha256((out_a / k).read_bytes()).hexdigest() for k in manifest["files"]
        }
        check(recomputed == manifest["files"], "every manifest hash matches the file on disk")
        check(
            manifest["content_hash"] in stdout,
            "the command prints the content hash (the single number to compare)",
        )
        check(
            "\r" not in (out_a / "_framework" / "rng_probe.csv").read_text(encoding="utf-8"),
            "files are written with \\n line ends on every operating system",
        )

        print("Seeding and determinism")
        out_b = tmp / "b"
        code_b, *_ = cli("--profile", "small", "--seed", 3004, "--out", out_b)
        manifest_b = gd.json.loads((out_b / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
        check(
            code_b == 0 and manifest_b["files"] == manifest["files"], "same seed: identical hashes"
        )
        check(tree_bytes(out_a) == tree_bytes(out_b), "same seed: files are byte-identical")
        check(
            (out_a / gd.MANIFEST_FILE).read_bytes() == (out_b / gd.MANIFEST_FILE).read_bytes(),
            "same seed: the manifest itself is byte-identical (no timestamps, no paths)",
        )
        code_r, *_ = cli("--profile", "small", "--seed", 3004, "--out", out_a)
        manifest_r = gd.json.loads((out_a / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
        check(
            code_r == 0 and manifest_r["content_hash"] == manifest["content_hash"],
            "same seed into the same folder again: same content hash",
        )
        out_c = tmp / "c"
        cli("--profile", "small", "--seed", 3005, "--out", out_c)
        manifest_c = gd.json.loads((out_c / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
        check(
            manifest_c["content_hash"] != manifest["content_hash"]
            and tree_bytes(out_c) != tree_bytes(out_a),
            "a different seed gives different data",
        )
        out_d = tmp / "d"
        cli("--profile", "full", "--seed", 3004, "--out", out_d)
        manifest_d = gd.json.loads((out_d / gd.MANIFEST_FILE).read_text(encoding="utf-8"))
        check(
            manifest_d["profile"]["name"] == "full" and manifest_d["profile"]["units"] == 1800,
            "the full profile runs and the manifest records its size",
        )

        print("Seeded generators for stages")
        ctx = gd.Context(small, 3004, tmp / "x")
        same = (ctx.rng("alpha").random(5) == ctx.rng("alpha").random(5)).all()
        other = (ctx.rng("alpha").random(5) != ctx.rng("beta").random(5)).any()
        reseed = (
            gd.Context(small, 3005, tmp / "x").rng("alpha").random(5) != ctx.rng("alpha").random(5)
        ).any()
        check(bool(same), "the same stage name and seed give the same random numbers")
        check(bool(other), "different stage names give different streams")
        check(bool(reseed), "a different seed changes a stage's stream")
        saved = dict(gd.STAGES)
        try:

            @gd.stage("zz_test_stage", "temporary stage used by the test")
            def temp_stage(c):
                c.write_text("s1/test_stage.txt", " ".join(map(str, c.rng().integers(0, 99, 8))))

            out_e, out_f = tmp / "e", tmp / "f"
            m_e = gd.run(small, 3004, out_e)
            m_f = gd.run(small, 3004, out_f)
            check(
                m_e["files"]["s1/test_stage.txt"] == m_f["files"]["s1/test_stage.txt"]
                and "zz_test_stage" in m_e["stages"],
                "a newly registered stage runs and is reproducible",
            )
            check(
                m_e["files"]["_framework/rng_probe.csv"]
                == manifest["files"]["_framework/rng_probe.csv"],
                "adding a stage does not change the data of the other stages",
            )
            try:
                gd.stage("zz_test_stage")(lambda c: None)
                dup = False
            except gd.GeneratorError:
                dup = True
            check(dup, "registering the same stage name twice is refused")
            try:
                gd.Context(small, 1, tmp / "y").write_text("../escape.txt", "x")
                escaped = True
            except gd.GeneratorError:
                escaped = False
            check(not escaped, "a stage cannot write outside the generator's folders")
        finally:
            gd.STAGES.clear()
            gd.STAGES.update(saved)

        print("Safe output handling")
        stale = tmp / "a" / "s3" / "old_run.csv"
        stale.write_text("left over from an earlier run", encoding="utf-8")
        cache = tmp / "a" / "weather_cache.json"
        cache.write_text("{}", encoding="utf-8")
        cli("--profile", "small", "--seed", 3004, "--out", out_a)
        check(not stale.exists(), "a rerun removes stale files from the folders it owns")
        check(cache.exists(), "a rerun never touches other files (weather_cache.json survives)")
        code_root, _, _, err_root = cli("--out", Path(out_a.anchor))
        check(
            code_root == 2 and "refusing" in err_root,
            "an unsafe output folder (the root) is refused",
        )
        code_neg, _, _, _ = cli("--seed", -5, "--out", tmp / "n")
        code_txt, _, _, _ = cli("--seed", "abc", "--out", tmp / "n")
        code_prof, _, _, _ = cli("--profile", "huge", "--out", tmp / "n")
        check(
            code_neg == 2 and code_txt == 2 and code_prof == 2 and not (tmp / "n").exists(),
            "a bad seed or an unknown profile is refused before anything is written",
        )
        elsewhere = tmp / "elsewhere"
        elsewhere.mkdir()
        code_cwd, *_ = cli("--out", tmp / "g", cwd=elsewhere)
        check(code_cwd == 0, "it runs from any working folder")

        print("Speed")
        code_t, secs, *_ = cli("--profile", "small", "--out", tmp / "t")
        check(
            code_t == 0 and secs < 60,
            f"the small profile completes in under a minute ({secs:.1f}s)",
        )

        print("No unseeded randomness in the generator code")
        offenders = []
        for f in sorted((ROOT / "etl").glob("*.py")):
            if f.name in ("generate_data.py", "generator_config.py") or f.name.startswith("gen_"):
                text = f.read_text(encoding="utf-8")
                if re.search(
                    r"^\s*(import random|from random\b|import uuid|from uuid\b)", text, re.M
                ):
                    offenders.append(f"{f.name}: random/uuid")
                for m in re.finditer(r"np\.random\.(\w+)", text):
                    if m.group(1) not in ("Generator", "PCG64", "SeedSequence"):
                        offenders.append(f"{f.name}: np.random.{m.group(1)}")
        check(
            not offenders,
            "no `random`, `uuid` or global `np.random` calls"
            + (f": {offenders}" if offenders else ""),
        )

        print("Defaults")
        check(
            cfg.DEFAULT_SEED == 3004 and cfg.DEFAULT_PROFILE == "small",
            "defaults are seed 3004 and the small profile (a bare run is reproducible)",
        )

    print("=" * 70)
    print(
        f" RESULT: {sum(results)}/{len(results)} checks passed"
        + ("" if results and all(results) else " - FAILED")
    )
    print("=" * 70)
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

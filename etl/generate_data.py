#!/usr/bin/env python3
"""Seeded synthetic data generator for the LUE warehouse (US-2.1: the framework).

    python etl/generate_data.py                      small profile, seed 3004, into data/
    python etl/generate_data.py --profile full --seed 7 --out /tmp/lue

What this file does (and what it deliberately does not):

* It reads a profile from `etl/generator_config.py` (portfolio size, date window, volume targets,
  defect rates), creates the output folders `s1` to `s6` and `answer_key`, runs the registered
  stages in order and writes a manifest with the SHA-256 of every file it produced.
* It generates no business data yet. Master data, leases, payments and so on arrive as stages in
  US-2.2 to US-2.6. Each of those stories adds one function with the `@stage` decorator.

Reproducibility rules for everyone who writes a stage:

1. Never use unseeded randomness: no `random`, no `np.random.<function>`, no `uuid4`, no
   `datetime.now()` in generated data, no iteration over a `set` that decides output order.
2. Get your generator from `ctx.rng()` (or `ctx.rng("name")`). It is a NumPy `Generator` derived
   from the run's one seed and the stage name, so a stage gives the same numbers whatever the
   other stages do. Adding or reordering a stage never changes another stage's data.
3. Write files only through `ctx.write_text` / `ctx.write_bytes` (UTF-8, `\\n` line ends, so the
   bytes are identical on Windows and Linux).
4. Fixed-width number formatting (`f"{x:.2f}"`), never `repr(float)`, in written files.

Source folders (plan A4, section 1): s1 LUE-PMS (PostgreSQL), s2 Excel registers, s3 bank and
wallet settlements, s4 maintenance tickets (JSON), s5 weather (the cache itself is
`data/weather_cache.json`, decision D12), s6 incentive log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from etl.generator_config import (  # noqa: E402
    DEFAULT_PROFILE,
    DEFAULT_SEED,
    PROFILES,
    Profile,
    get_profile,
)

GENERATOR_VERSION = "2.1"
SOURCES = ("s1", "s2", "s3", "s4", "s5", "s6")
# Folders and files the generator owns inside --out. Nothing else in --out is ever touched
# (in particular data/weather_cache.json, which is committed, decision D12).
OWNED_DIRS = (*SOURCES, "_framework", "answer_key")
MANIFEST_FILE = "run_manifest.json"  # deterministic: what was generated, with hashes
RUN_INFO_FILE = "run_info.json"  # not deterministic: when, how long, which library versions
OWNED_FILES = (MANIFEST_FILE, RUN_INFO_FILE)
MAX_SEED = 2**63 - 1


class GeneratorError(Exception):
    """A usage problem (bad flag, unsafe output folder, bad stage); shown without a traceback."""


# --------------------------------------------------------------------------------------------------
# Run context handed to every stage
# --------------------------------------------------------------------------------------------------
class Context:
    """What a stage may use: the profile, the seed, seeded generators and safe file writers."""

    def __init__(self, profile: Profile, seed: int, out: Path):
        self.profile = profile
        self.seed = seed
        self.out = out

    def rng(self, name: str | None = None) -> np.random.Generator:
        """A seeded NumPy generator for one stage (default: the running stage's own name).

        The stream depends only on (seed, name), so stages are independent of each other.
        """
        if name is None:
            name = _current_stage.get("name")
            if name is None:
                raise GeneratorError("ctx.rng() needs a name when called outside a stage")
        digest = hashlib.sha256(name.encode("utf-8")).digest()
        entropy = [self.seed, int.from_bytes(digest[:8], "big")]
        return np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy)))

    def source_dir(self, source: str) -> Path:
        if source not in OWNED_DIRS:
            raise GeneratorError(f"unknown output folder {source!r}; use one of {OWNED_DIRS}")
        return self.out / source

    def _target(self, relative: str) -> Path:
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise GeneratorError(f"{relative!r} is not a valid generated path")
        if rel.parts[0] not in OWNED_DIRS:
            raise GeneratorError(
                f"{relative!r} is not a valid generated path; start with one of {OWNED_DIRS}"
            )
        target = self.out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def write_bytes(self, relative: str, data: bytes) -> Path:
        target = self._target(relative)
        target.write_bytes(data)
        return target

    def write_text(self, relative: str, text: str) -> Path:
        """Write UTF-8 text with `\\n` line ends, on every operating system."""
        return self.write_bytes(relative, text.replace("\r\n", "\n").encode("utf-8"))


# --------------------------------------------------------------------------------------------------
# Stage registry: US-2.2 to US-2.6 add their functions here
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Stage:
    name: str
    description: str
    func: Callable[[Context], None]


STAGES: dict[str, Stage] = {}  # insertion order is run order (dependency order)
_current_stage: dict[str, str | None] = {"name": None}


def stage(name: str, description: str = "") -> Callable:
    """Register a generation stage. Stages run in the order they are registered."""

    def decorate(func: Callable[[Context], None]) -> Callable[[Context], None]:
        if name in STAGES:
            raise GeneratorError(f"stage {name!r} is registered twice")
        STAGES[name] = Stage(name, description or (func.__doc__ or "").strip(), func)
        return func

    return decorate


@stage("framework_probe", "Draw from a seeded stream and write it (proves seeding and writing)")
def framework_probe(ctx: Context) -> None:
    """The one stage US-2.1 ships. Its file is the determinism evidence until real data exists."""
    rng = ctx.rng()
    n = 200
    uniform = rng.random(n)
    integer = rng.integers(0, 1_000_000, n)
    normal = rng.standard_normal(n)
    lines = ["draw,uniform,integer,normal"]
    lines += [f"{i},{uniform[i]:.12f},{integer[i]},{normal[i]:.12f}" for i in range(n)]
    ctx.write_text("_framework/rng_probe.csv", "\n".join(lines) + "\n")


# --------------------------------------------------------------------------------------------------
# Running a profile
# --------------------------------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def hash_outputs(out: Path) -> dict[str, str]:
    """SHA-256 of every generated file, keyed by its path relative to `out` (sorted)."""
    files = {}
    for folder in OWNED_DIRS:
        base = out / folder
        if base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    files[p.relative_to(out).as_posix()] = sha256_file(p)
    return dict(sorted(files.items()))


def content_hash(files: dict[str, str]) -> str:
    """One hash for the whole output: equal content hashes mean byte-identical outputs."""
    text = "".join(f"{h}  {p}\n" for p, h in files.items())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare_output(out: Path) -> None:
    """Make `out`, clear the folders this generator owns, and recreate them empty."""
    resolved = out.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise GeneratorError(f"refusing to generate into {resolved}; choose a dedicated folder")
    out.mkdir(parents=True, exist_ok=True)
    for name in OWNED_DIRS:
        target = out / name
        if target.is_symlink() or target.is_file():
            raise GeneratorError(f"{target} is not a folder; remove it or use another --out")
        if target.is_dir():
            shutil.rmtree(target)
        target.mkdir()
    for name in OWNED_FILES:
        (out / name).unlink(missing_ok=True)


def run(profile: Profile, seed: int, out: Path) -> dict:
    """Generate everything for one profile and seed into `out`; return the manifest."""
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= MAX_SEED:
        raise GeneratorError(f"seed must be an integer from 0 to {MAX_SEED}")
    started = time.perf_counter()
    prepare_output(out)
    ctx = Context(profile, seed, out)
    ran = []
    try:
        for st in list(STAGES.values()):
            _current_stage["name"] = st.name
            st.func(ctx)
            ran.append(st.name)
    finally:
        _current_stage["name"] = None
    files = hash_outputs(out)
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "profile": profile.to_dict(),
        "stages": ran,
        "source_folders": list(SOURCES),
        "files": files,
        "content_hash": content_hash(files),
    }
    (out / MANIFEST_FILE).write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    info = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds": round(time.perf_counter() - started, 3),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "platform": platform.platform(),
        "note": "Not part of the determinism check. If two machines disagree on content_hash, "
        "compare the numpy versions here first.",
    }
    (out / RUN_INFO_FILE).write_bytes((json.dumps(info, indent=2) + "\n").encode("utf-8"))
    return manifest


# --------------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------------
def seed_arg(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not an integer") from None
    if not 0 <= value <= MAX_SEED:
        raise argparse.ArgumentTypeError(f"seed must be from 0 to {MAX_SEED}")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate the seeded synthetic source data for the LUE warehouse (US-2.1).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--profile", choices=sorted(PROFILES), default=DEFAULT_PROFILE)
    p.add_argument("--seed", type=seed_arg, default=DEFAULT_SEED, help="random seed (non-negative)")
    p.add_argument("--out", type=Path, default=ROOT / "data", help="output folder")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = get_profile(args.profile)
        manifest = run(profile, args.seed, args.out)
    except (GeneratorError, ValueError) as exc:
        print(f"generate_data: {exc}", file=sys.stderr)
        return 2
    print(
        f"profile       {profile.name} ({profile.buildings} buildings, {profile.units} units, "
        f"{profile.months} months)"
    )
    print(f"seed          {manifest['seed']}")
    print(f"output        {args.out}  (folders: {', '.join(SOURCES)}, answer_key)")
    print(f"stages        {', '.join(manifest['stages'])}")
    print(f"files         {len(manifest['files'])}")
    print(f"content hash  {manifest['content_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

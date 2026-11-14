# Evidence for US-2.1: generator framework, configuration and seeding

| File | What it shows |
|---|---|
| `01_hash_comparison.txt` | The plan's evidence: same seed twice gives the same content hash and identical file hashes; a different seed gives different ones |
| `02_acceptance_tests.txt` | `python scripts/test_generator.py`: 39 PASS lines (configuration, folders, manifest, determinism, seeded streams, safe output, speed, no unseeded randomness) |
| `03_tests_catch_broken_seeding.txt` | Two deliberately broken copies of the generator fail the tests, so a green run means something |

Produced on Linux with Python 3.13 and NumPy 2.5.3. The content hash for `--profile small --seed 3004` is
`67c361e826115383461b85b9160a9f0630c365625b3175bfc8d1c47d60fd1f68`. Each teammate should run the same command on their
own machine and compare; a different value points at a different NumPy version (see `data/run_info.json`).

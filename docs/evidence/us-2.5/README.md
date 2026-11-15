# Evidence for US-2.5: tickets, incentives and weather

| File | What it shows |
|---|---|
| `01_hash_comparison.txt` | Same seed, same content hash; another seed, another hash; the US-2.2 files unchanged |
| `02_ticket_tests.txt` | `python scripts/test_tickets.py`: 67/67 (small and full profile) |
| `03_weather_tests.txt` | `python scripts/test_weather.py`: 54/54, including the committed cache |
| `04_weather_cache_check.txt` | `python etl/refresh_weather.py --check`: every city and every day, with null counts |
| `05_samples.txt` | A verified ticket, an open ticket, the offers, the first incentive log rows |
| `06_tests_catch_broken_code.txt` | 14 deliberate code changes: 13 bugs, each caught (one only after a test was added), and 1 harmless change |
| `07_merge_rehearsal.txt` | Merging with the US-2.3/2.4 branch: the 4 conflict spots and all six suites passing after |

`03_` and `04_` come from the machine that downloaded the real cache (see the README, "Weather data").

# Contributing

This repo is generated. A private cockpit exports it through FOURTHWALL, so the public history is a series of releases, not a mirror of day-to-day commits.

- **Issues** are welcome: bugs in the scripts, unclear skill specs, ideas for new domains.
- **Pull requests:** keep them small and include a test in `tests/test_suite.py` (synthetic data only, never real records). Accepted changes are ported into the private source and come back in the next release, so the merge may land as part of a release commit.
- **Data:** never put real personal data in an issue, a PR or a fixture. Use the fictional persona in `examples/persona/`.
- **Style:** match the surrounding code. Scripts do exact work (math, dates, hashes, checks); skills describe the judgment calls.

Run the tests before opening a PR:

```bash
python tests/test_suite.py
```

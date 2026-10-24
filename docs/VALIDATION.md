# Validation for 0.1.0

Executed on 2026-10-24 with Windows and CPython 3.13.16:

- `python -m unittest discover -s tests -v`: 16 tests passed.
- Same 16 tests passed in a separate new virtual environment after installing
  the built wheel with `--no-index --no-deps`.
- Ruff 0.17.2 lint and formatting checks, compileall and pip check passed.
- Source distribution and pure-Python wheel built successfully; wheel metadata
  declares MIT and zero runtime dependencies. Examples/docs are included in sdist.
- Both documented examples ran through the installed executable: valid shards
  returned 0 with three cases; broken input returned 1 with actual findings.
- An actual pytest 9.1.1 JUnit report from two plain tests passed the integrity
  and success gates with two observed cases.
- A separate pytest run of the unittest suite passed 16 tests and 10 subtests.
  Its XML declared 26 tests but emitted 16 testcase elements. The guard correctly
  reported that discrepancy. This is recorded as a producer compatibility limit,
  not silently adjusted or presented as a clean report.
- Byte hashes verified read-only behavior; failure messages, trace bodies and
  system logs were absent from captured CLI output. DTD rejection tested with
  UTF-8 and UTF-16 input. Case/byte/depth limits and missing input were exercised.
- Separately installed development toolchain checked with pip-audit 2.10.1:
  no known vulnerabilities reported at the time of the check. This is not a
  guarantee about unknown vulnerabilities or future advisories.

The CI workflow additionally runs tests on Linux (Python 3.10/3.13), Windows
(3.13) and macOS (3.13), and builds/checks formatting on Linux. See the repository
Actions tab for actual run status; this document does not substitute for it.

Review found and fixed a closure binding flagged by Ruff and missing ancillary
files in the original source-distribution manifest. No external code is vendored.

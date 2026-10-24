# junit-report-guard

Catch duplicate test identities, stale counters and malformed JUnit XML before
publishing CI results. Local, read-only, with no runtime dependencies.

```text
FAIL: 2 test cases; 2 integrity findings
duplicate-test: Repeated classname/name identity can hide a test in CI ...
count-mismatch: Declared count differs from observed test cases ...
```

JUnit upload success does not mean a report is complete. [GitLab documents that
duplicate names can be ignored](https://docs.gitlab.com/ci/testing/unit_test_reports/).
[junitparser](https://github.com/weiwei/junitparser) is a capable parser and merger;
its merge operation deliberately leaves duplicate handling to the caller. This
tool adds a small integrity gate across explicit report files. It never merges,
repairs or rewrites reports.

## Install

Requires Python 3.10+ and Git. No service, credentials or Java installation.
This initial version is distributed on GitHub, **not on PyPI**.

```sh
git clone https://github.com/KanadeK/junit-report-guard.git
cd junit-report-guard
python -m venv .venv
```

Activate the environment:

- Linux/macOS: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

If PowerShell activation is restricted, use `.venv\Scripts\python.exe` instead
of `python` and `.venv\Scripts\junit-report-guard.exe` instead of the command.
No policy changes are needed.

```sh
python -m pip install .
junit-report-guard --version
```

The build step may download setuptools. Once installed, all checks run offline.
To uninstall: `python -m pip uninstall junit-report-guard`. The tool creates no
cache or configuration. Deactivate the environment and remove the clone/venv
when no longer needed; delete any reports you redirected to disk yourself.

## Try it

From the cloned repository:

```sh
junit-report-guard examples/shard-a.xml examples/shard-b.xml --require-files 2
# OK: 3 test cases; 0 integrity findings (exit 0)

junit-report-guard examples/broken.xml --json
# duplicate-test and count-mismatch (exit 1)
```

For your CI artifacts:

```sh
junit-report-guard results/unit.xml results/integration.xml --require-files 2 --json
```

Pass explicit filenames; the program does not expand globs or scan directories.
`--require-files` verifies the supplied path count, not the existence of unnamed
shards. A missing supplied file is always an error. Use your CI's artifact
manifest if you need to check exact shard names.

## Checks and semantics

| Check | Behavior |
| --- | --- |
| Identity | Exact `(classname, name)` pair, globally across all input files and suites |
| Missing classname | Treated as an empty string; a nonblank name is required |
| Duplicate occurrence | Reported with first and repeated file/suite/case locations |
| Counters | Present `tests`, `failures`, `errors`, `skipped` attributes compared to descendant testcase totals |
| Multiple failures | Several `<failure>` elements in one testcase count as one failing testcase |
| Conflicting outcomes | Different kinds among `failure`, `error`, `skipped` are an integrity error |
| Time | Present `time` attributes must parse as finite, nonnegative decimal numbers |
| Empty input/report | An error, even when declared `tests="0"` |
| XML | `testsuite` or `testsuites` root; nested suites and namespaces supported |
| Hidden testcase | An error when testcase is nested under unsupported extension elements |

Totals count occurrences, including duplicates; they are not deduplicated. A
conflicting outcome uses error → failure → skipped precedence for totals while
still making the report fail. Missing count/time attributes are permitted.
Failure messages, properties, error bodies and system logs are never included
in output. Metadata such as test identities, suite names and filenames may
still be sensitive. Terminal output escapes these values.

By default, a correctly formed report containing failing tests can pass the
integrity gate. Add `--require-success` to also fail on test failures or errors.
Skipped tests alone do not fail that gate.

Exit codes: **0** all requested checks pass, **1** integrity/input finding or
required test success failed, **2** invalid command usage. JSON includes
`schema_version`, `ok`, `totals`, per-file counts, `finding_count`,
`findings_truncated` and bounded `findings`.

```python
from junit_report_guard import audit

report = audit(["unit.xml", "integration.xml"], require_files=2)
assert report["ok"], report["findings"]
```

## Limits in 0.1.0

This checks a documented common subset, not every JUnit dialect or an official
universal schema. Repeated platform runs or retry attempts with identical
identities must be checked separately or given distinct identities by the
producer. Rerun-specific extension semantics are not interpreted. Aggregate
timings are validated but are not recomputed because producers differ.
Some producers count subtests in suite totals without emitting corresponding
testcase elements. These reports will receive a count-mismatch finding; this
tool deliberately checks emitted testcase counts, not hidden subtest events.

Defaults: 30 MB per file, 120 MB total, 1,000 paths, 200,000 test cases total,
64 levels of XML nesting, 1,000,000 elements per file and 1,000 stored findings.
`--max-bytes` changes the per-file byte limit; `--max-findings` changes stored
findings. The total finding count and failure exit code remain accurate when
output is truncated. DTDs/entities are rejected, including UTF-16 documents.
Files are read independently; this is not an atomic snapshot of live reports.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md),
[validation notes](docs/VALIDATION.md) and [MIT license](LICENSE).

## 中文说明

本工具用于在上传 CI 测试结果前检查 JUnit XML 的完整性：发现跨文件的重复测试、
错误汇总计数、空报告、非法耗时和冲突结果。全程本地只读，不上传数据，不输出
失败正文或日志。Python 3.10 及以上即可使用，无第三方运行时依赖。

按照上方步骤克隆、创建虚拟环境并执行 `python -m pip install .`。
运行 `junit-report-guard examples/shard-a.xml examples/shard-b.xml --require-files 2`
可验证正常流程；`examples/broken.xml` 应返回退出码 1。
默认仅检查报告完整性，添加 `--require-success` 可同时要求测试结果成功。
同一测试在不同平台或重试中重复运行时，请分开检查，避免身份碰撞。

# Scope and acceptance criteria

Target: maintainers who collect explicit JUnit artifacts before CI ingestion.
The complete workflow is install → audit reports → inspect findings → fix the
producer/collection step → rerun the audit. The tool never changes results.

Acceptance: count distinct outcome kinds correctly; find duplicates across files;
reject empty/malformed/missing input and unsafe XML; preserve input byte hashes;
hide failure/log content; expose deterministic structured output and useful
nonzero exit codes; install from a wheel in a clean environment; pass CI on the
supported OS/Python matrix.

Architecture: a bounded XML TreeBuilder rejects DTD and excessive nesting before
semantic traversal. A global identity map links duplicate occurrences; each
suite computes counts recursively without double counting. Findings are capped
independently from their total count. argparse is a thin interface over audit().
Complexity is linear in input XML size plus identity storage. No third-party
parser, network client or mutation API is required.

Review focus: XML entity bypasses, hidden testcases, conflicting status, nested
counter correctness, malicious metadata escaping and duplicate report paths.

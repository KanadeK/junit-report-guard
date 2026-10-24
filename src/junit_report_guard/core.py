"""A conservative JUnit subset, with no modification or log-body output."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

COUNTS = ("tests", "failures", "errors", "skipped", "passed")
CONTAINERS = {"testsuite", "testsuites"}
OUTCOMES = {"failure", "error", "skipped"}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class ReportInputError(ValueError):
    """Input rejected before semantic validation."""


class LimitedTree(ET.TreeBuilder):
    """Reject DTDs and cap nesting, case count and total element count."""

    def __init__(self, max_cases: int, max_depth: int):
        super().__init__()
        self.depth = 0
        self.elements = 0
        self.cases = 0
        self.max_cases = max_cases
        self.max_depth = max_depth

    def start(self, tag: str, attrs: dict[str, str]) -> ET.Element:
        self.depth += 1
        self.elements += 1
        if self.depth > self.max_depth or self.elements > 1_000_000:
            raise ReportInputError("XML nesting or element limit exceeded")
        if local(tag) == "testcase":
            self.cases += 1
            if self.cases > self.max_cases:
                raise ReportInputError("Test case limit exceeded")
        return super().start(tag, attrs)

    def end(self, tag: str) -> ET.Element:
        self.depth -= 1
        return super().end(tag)

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise ReportInputError("DTD and entity declarations are not accepted")


def audit(
    paths: list[str | Path],
    *,
    require_files: int | None = None,
    require_success: bool = False,
    max_bytes: int = 30_000_000,
    max_cases: int = 200_000,
    max_depth: int = 64,
    max_findings: int = 1000,
) -> dict[str, Any]:
    """Audit explicit files. Counts are per testcase, including duplicate occurrences.

    Identity is the exact (classname, name) pair across all inputs. Nested suite
    names do not disambiguate identities. Missing classname is the empty string.
    Inputs are parsed separately; malformed files contribute zero to totals and
    always produce an error. No failure/error/system-out text is returned.
    """
    for limit in (max_bytes, max_cases, max_depth, max_findings):
        if type(limit) is not int or limit < 1:
            raise ValueError("All resource limits must be positive integers")
    if require_files is not None and (type(require_files) is not int or require_files < 1):
        raise ValueError("require_files must be a positive integer")
    totals: Counter[str] = Counter(dict.fromkeys(COUNTS, 0))
    findings: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    seen_cases: dict[tuple[str, str], dict[str, Any]] = {}
    finding_count = 0
    total_bytes = 0

    def add(code: str, message: str, **where: Any) -> None:
        nonlocal finding_count
        finding_count += 1
        if len(findings) < max_findings:
            findings.append({"code": code, "message": message, **where})

    if not paths:
        add("no-input", "At least one report is required")
    if len(paths) > 1000:
        add("input-limit", "At most 1000 report paths are accepted")
        paths = []
    if require_files is not None and len(paths) != require_files:
        add("file-count", "Report path count differs from required count", expected=require_files)

    for path in paths:
        source = Path(path)
        display = str(source)
        try:
            resolved = source.resolve(strict=True)
            if resolved in seen_paths:
                add("duplicate-input", "The same file was supplied more than once", file=display)
                continue
            seen_paths.add(resolved)
            if not resolved.is_file():
                raise ReportInputError("Report must be a regular file")
            with source.open("rb") as stream:
                raw = stream.read(max_bytes + 1)
            total_bytes += len(raw)
            if len(raw) > max_bytes or total_bytes > 120_000_000:
                raise ReportInputError("Report byte limit exceeded")
            builder = LimitedTree(max_cases, max_depth)
            root = ET.fromstring(raw, parser=ET.XMLParser(target=builder))
        except (OSError, ValueError, ET.ParseError) as exc:
            message = (
                str(exc) if isinstance(exc, ReportInputError) else "Unreadable or malformed XML"
            )
            add("input-error", message, file=display)
            files.append({"file": display, "parsed": False})
            continue

        if local(root.tag) not in CONTAINERS:
            add("root-element", "Root must be testsuite or testsuites", file=display)
            files.append({"file": display, "parsed": False})
            continue
        case_number = 0

        def timing(node: ET.Element, context: dict[str, Any]) -> None:
            if "time" not in node.attrib:
                return
            try:
                value = Decimal(node.attrib["time"])
                if not value.is_finite() or value < 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                add("invalid-time", "Time must be finite and nonnegative", **context)

        def visit(
            node: ET.Element, parent: tuple[str, ...], source_name: str = display
        ) -> Counter[str]:
            nonlocal case_number
            tag = local(node.tag)
            suite = (*parent, node.attrib.get("name", "")) if tag == "testsuite" else parent
            context: dict[str, Any] = {"file": source_name, "suite": list(suite)}
            result: Counter[str] = Counter(dict.fromkeys(COUNTS, 0))
            timing(node, context)
            for child in node:
                child_tag = local(child.tag)
                if child_tag in CONTAINERS:
                    result.update(visit(child, suite))
                    continue
                if child_tag != "testcase":
                    continue
                case_number += 1
                location = {**context, "case": case_number}
                name = child.attrib.get("name", "")
                classname = child.attrib.get("classname", "")
                if not name.strip():
                    add("missing-name", "Test case must have a nonblank name", **location)
                else:
                    identity = (classname, name)
                    if identity in seen_cases:
                        add(
                            "duplicate-test",
                            "Repeated classname/name identity can hide a test in CI",
                            **location,
                            identity=list(identity),
                            first=seen_cases[identity],
                        )
                    else:
                        seen_cases[identity] = location
                timing(child, location)
                states = {local(element.tag) for element in child} & OUTCOMES
                if len(states) > 1:
                    add("conflicting-outcomes", "Test has more than one outcome kind", **location)
                # Multiple <failure> elements still represent one failing test.
                outcome = (
                    "errors"
                    if "error" in states
                    else "failures"
                    if "failure" in states
                    else "skipped"
                    if "skipped" in states
                    else "passed"
                )
                result["tests"] += 1
                result[outcome] += 1
            for attribute in COUNTS[:-1]:
                if attribute not in node.attrib:
                    continue
                declared = node.attrib[attribute]
                if not re.fullmatch(r"[0-9]+", declared) or len(declared) > 12:
                    add(
                        "invalid-count",
                        "Count must be a nonnegative integer",
                        **context,
                        attribute=attribute,
                    )
                elif int(declared) != result[attribute]:
                    add(
                        "count-mismatch",
                        "Declared count differs from observed test cases",
                        **context,
                        attribute=attribute,
                        declared=int(declared),
                        observed=result[attribute],
                    )
            return result

        observed = visit(root, ())
        if case_number != builder.cases:
            add(
                "hidden-testcase",
                "Testcase appears outside the supported suite hierarchy",
                file=display,
            )
        if not observed["tests"]:
            add("empty-report", "Report contains no test cases", file=display)
        if totals["tests"] + observed["tests"] > max_cases:
            add("total-case-limit", "Combined report case limit exceeded", file=display)
            break
        totals.update(observed)
        files.append({"file": display, "parsed": True, "counts": dict(observed)})

    if require_success and (totals["failures"] or totals["errors"]):
        add("test-failures", "Observed test failures or errors; success was required")
    return {
        "schema_version": 1,
        "ok": finding_count == 0,
        "totals": dict(totals),
        "files": files,
        "finding_count": finding_count,
        "findings_truncated": finding_count > len(findings),
        "findings": findings,
    }

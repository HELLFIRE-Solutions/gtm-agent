"""Gate verdict from JUnit XML reports (stdlib only).

``--base`` is the JUnit report of the test run on the base commit; it defines
which test ids exist on base and how each of them ended there.  ``--gate`` is
the JUnit report of the run in the assembled tree.

The gate passes only if

* every test id that exists on base appears in the gate report with outcome
  ``passed``; the only exception is an id that has the same non-run outcome
  (``skipped`` or ``xfailed``) on base;
* no test that is new in the gate run, including a collection error, failed;
* at least one test ran.
"""
from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import safe, write_json  # noqa: E402

# Ordered from best to worst; a test id seen twice keeps the worst outcome.
OUTCOMES = ("passed", "skipped", "xfailed", "failed", "error")
NON_RUN = frozenset({"skipped", "xfailed"})
FAILING = frozenset({"failed", "error"})
LIST_LIMIT = 50


def _worse(a: str | None, b: str) -> str:
    if a is None:
        return b
    return a if OUTCOMES.index(a) >= OUTCOMES.index(b) else b


def _outcome(case: ET.Element) -> str:
    result = "passed"
    for child in case:
        if child.tag == "error":
            result = _worse(result, "error")
        elif child.tag == "failure":
            result = _worse(result, "failed")
        elif child.tag == "skipped":
            kind = "xfailed" if child.get("type") == "pytest.xfail" else "skipped"
            result = _worse(result, kind)
    return result


def parse_junit(path: str) -> dict[str, str]:
    """Map test id (``classname::name``) -> outcome."""
    outcomes: dict[str, str] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        classname = case.get("classname") or ""
        name = case.get("name") or ""
        test_id = "%s::%s" % (classname, name) if classname else name
        outcomes[test_id] = _worse(outcomes.get(test_id), _outcome(case))
    return outcomes


def evaluate(base: dict[str, str], gate: dict[str, str]) -> dict:
    """Compare base outcomes with gate outcomes."""
    missing: list[str] = []
    not_passed: dict[str, str] = {}
    passed_in_gate = 0
    for test_id in sorted(base):
        got = gate.get(test_id)
        if got == "passed":
            passed_in_gate += 1
        elif got is None:
            missing.append(test_id)
        elif got in NON_RUN and got == base[test_id]:
            continue  # same id is skipped/xfailed on base too
        else:
            not_passed[test_id] = got
    new_ids = sorted(t for t in gate if t not in base)
    new_failed = {t: gate[t] for t in new_ids if gate[t] in FAILING}
    empty = len(gate) == 0
    return {
        "passed": not (missing or not_passed or new_failed or empty),
        "base_total": len(base),
        "gate_total": len(gate),
        "base_passed_in_gate": passed_in_gate,
        "base_same_nonrun": len(base) - passed_in_gate - len(missing) - len(not_passed),
        "new_total": len(new_ids),
        "missing": missing,
        "not_passed": not_passed,
        "new_failed": new_failed,
        "empty": empty,
        "error": None,
    }


def _print_list(title: str, items: list[str]) -> None:
    print("%s (%d):" % (title, len(items)))
    for item in items[:LIST_LIMIT]:
        print("  - " + safe(item))
    if len(items) > LIST_LIMIT:
        print("  ... and %d more" % (len(items) - LIST_LIMIT))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="JUnit XML of the run on base")
    ap.add_argument("--gate", required=True, help="JUnit XML of the gate run")
    ap.add_argument("--out", required=True, help="path of the JSON verdict to write")
    args = ap.parse_args(argv)

    try:
        base = parse_junit(args.base)
        gate = parse_junit(args.gate)
    except (OSError, ET.ParseError) as exc:
        write_json(args.out, {"passed": False, "error": "cannot read test report: %s" % safe(exc)})
        print("GATE FAILED: cannot read test report: " + safe(exc))
        return 1

    verdict = evaluate(base, gate)
    write_json(args.out, verdict)
    print("base tests: %d, gate tests: %d (new: %d)" % (
        verdict["base_total"], verdict["gate_total"], verdict["new_total"]))
    if verdict["passed"]:
        print("GATE PASSED: every base test passed (or is skipped on base too)")
        return 0
    print("GATE FAILED")
    if verdict["empty"]:
        print("  no tests ran in the gate run")
    _print_list("base tests missing from the gate run", verdict["missing"])
    _print_list(
        "base tests that did not pass",
        ["%s [%s]" % (t, o) for t, o in sorted(verdict["not_passed"].items())],
    )
    _print_list(
        "new tests that failed",
        ["%s [%s]" % (t, o) for t, o in sorted(verdict["new_failed"].items())],
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

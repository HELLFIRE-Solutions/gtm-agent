import json

import pytest

from verdict import evaluate, main, parse_junit


def junit(path, cases):
    """cases: list of (classname, name, outcome) with outcome in passed/failed/error/skipped/xfailed."""
    rows = []
    for cls, name, outcome in cases:
        inner = {
            "passed": "",
            "failed": '<failure message="boom">x</failure>',
            "error": '<error message="boom">x</error>',
            "skipped": '<skipped type="pytest.skip" message="s">x</skipped>',
            "xfailed": '<skipped type="pytest.xfail" message="x"/>',
        }[outcome]
        rows.append('<testcase classname="%s" name="%s" time="0.01">%s</testcase>' % (cls, name, inner))
    path.write_text('<?xml version="1.0"?><testsuites><testsuite name="pytest">%s</testsuite></testsuites>' % "".join(rows))
    return str(path)


BASE_CASES = [("tests.test_a", "test_one", "passed"), ("tests.test_a", "test_two[x]", "passed"), ("tests.test_b", "test_s", "skipped")]


def test_parse_junit_outcomes(tmp_path):
    p = junit(
        tmp_path / "r.xml",
        [("t", "a", "passed"), ("t", "b", "failed"), ("t", "c", "error"), ("t", "d", "skipped"), ("t", "e", "xfailed")],
    )
    assert parse_junit(p) == {
        "t::a": "passed",
        "t::b": "failed",
        "t::c": "error",
        "t::d": "skipped",
        "t::e": "xfailed",
    }


def test_duplicate_ids_keep_worst_outcome(tmp_path):
    p = junit(tmp_path / "r.xml", [("t", "a", "passed"), ("t", "a", "error")])
    assert parse_junit(p) == {"t::a": "error"}


def test_all_base_tests_pass():
    base = {c[0] + "::" + c[1]: c[2] for c in BASE_CASES}
    gate = dict(base) | {"tests.test_new::test_n": "passed"}
    v = evaluate(base, gate)
    assert v["passed"] and v["new_total"] == 1 and v["base_same_nonrun"] == 1


def test_base_test_that_becomes_skipped_fails_and_is_named():
    base = {"t::a": "passed", "t::b": "passed"}
    v = evaluate(base, {"t::a": "passed", "t::b": "skipped"})
    assert not v["passed"] and v["not_passed"] == {"t::b": "skipped"}


def test_base_test_that_becomes_xfailed_fails():
    v = evaluate({"t::a": "passed"}, {"t::a": "xfailed"})
    assert not v["passed"] and v["not_passed"] == {"t::a": "xfailed"}


def test_base_test_missing_from_report_fails_and_is_named():
    v = evaluate({"t::a": "passed", "t::b": "passed"}, {"t::a": "passed", "t::z": "passed"})
    assert not v["passed"] and v["missing"] == ["t::b"]


def test_test_skipped_on_base_too_is_allowed():
    v = evaluate({"t::a": "skipped"}, {"t::a": "skipped", "t::b": "passed"})
    assert v["passed"]


def test_test_skipped_on_base_but_missing_in_gate_fails():
    assert not evaluate({"t::a": "skipped"}, {"t::b": "passed"})["passed"]


def test_test_failing_on_base_must_pass_in_gate():
    assert not evaluate({"t::a": "failed"}, {"t::a": "failed"})["passed"]
    assert evaluate({"t::a": "failed"}, {"t::a": "passed"})["passed"]


def test_new_failing_test_or_collection_error_fails():
    v = evaluate({"t::a": "passed"}, {"t::a": "passed", "tests.test_new": "error"})
    assert not v["passed"] and v["new_failed"] == {"tests.test_new": "error"}


def test_new_skipped_test_is_fine():
    assert evaluate({"t::a": "passed"}, {"t::a": "passed", "t::n": "skipped"})["passed"]


def test_empty_gate_run_fails():
    v = evaluate({}, {})
    assert not v["passed"] and v["empty"]


def test_main_exit_codes_and_names(tmp_path, capsys):
    base = junit(tmp_path / "base.xml", BASE_CASES)
    gate_ok = junit(tmp_path / "ok.xml", BASE_CASES)
    gate_bad = junit(tmp_path / "bad.xml", [BASE_CASES[0], ("tests.test_a", "test_two[x]", "skipped"), BASE_CASES[2]])
    out = tmp_path / "v.json"
    assert main(["--base", base, "--gate", gate_ok, "--out", str(out)]) == 0
    assert json.loads(out.read_text())["passed"] is True
    capsys.readouterr()
    assert main(["--base", base, "--gate", gate_bad, "--out", str(out)]) == 1
    printed = capsys.readouterr().out
    assert "tests.test_a::test_two[x] [skipped]" in printed
    assert json.loads(out.read_text())["not_passed"] == {"tests.test_a::test_two[x]": "skipped"}


@pytest.mark.parametrize("content", [None, "not xml"])
def test_main_fails_on_missing_or_broken_report(tmp_path, content):
    base = junit(tmp_path / "base.xml", BASE_CASES)
    gate = tmp_path / "gate.xml"
    if content is not None:
        gate.write_text(content)
    out = tmp_path / "v.json"
    assert main(["--base", base, "--gate", str(gate), "--out", str(out)]) == 1
    assert json.loads(out.read_text())["passed"] is False


def test_printed_ids_cannot_start_a_workflow_command(tmp_path, capsys):
    base = junit(tmp_path / "base.xml", [("t", "a", "passed")])
    gate = junit(tmp_path / "gate.xml", [("t", "b\n::error::x", "passed")])
    assert main(["--base", base, "--gate", gate, "--out", str(tmp_path / "v.json")]) == 1
    assert not any(line.startswith("::") for line in capsys.readouterr().out.splitlines())

import json

from summary import main, render

REPORT = {
    "changes": {
        "tests/test_a.py": "modified",
        "tests/test_new.py": "added",
        "tests/test_gone.py": "deleted",
        "conftest.py": "added",
        "src/x.py": "modified",
    },
    "classification": {
        "protected_modified": ["tests/test_a.py", "conftest.py"],
        "protected_deleted": ["tests/test_gone.py"],
        "protected_added": ["conftest.py"],
        "tests_added": ["tests/test_new.py"],
        "tests_modified": ["tests/test_a.py"],
        "tests_deleted": ["tests/test_gone.py"],
        "other": ["src/x.py"],
        "reasons": {"conftest.py": "gate-relevant file (conftest.py)"},
    },
    "pyproject_diff": ["--- base/pyproject.toml", "+++ pr/pyproject.toml", "+  'dep'"],
    "new_src_toplevel": ["extra"],
    "errors": [],
}
VERDICT = {
    "passed": False,
    "base_total": 10,
    "base_passed_in_gate": 8,
    "base_same_nonrun": 0,
    "gate_total": 9,
    "new_total": 1,
    "missing": ["t::gone"],
    "not_passed": {"t::skipped_now": "skipped"},
    "new_failed": {},
    "empty": False,
    "error": None,
}
SHA = "a" * 40


def test_summary_contents():
    md = render(REPORT, VERDICT, SHA, "b" * 40)
    assert SHA in md and "b" * 40 in md
    assert "Tests: FAIL" in md
    assert "PROTECTED PATHS TOUCHED: 3" in md
    assert "`conftest.py`" in md and "`tests/test_gone.py`" in md
    assert "added: 1" in md and "existing tests modified (base version used): 1" in md
    assert "tests on base: 10" in md and "`t::gone`" in md and "t::skipped_now [skipped]" in md
    assert "pyproject.toml differs from base" in md and "```diff" in md
    assert "`extra`" in md
    assert "owner-approval" in md


def test_summary_pass():
    v = dict(VERDICT, passed=True, missing=[], not_passed={})
    assert "Tests: PASS" in render(dict(REPORT), v, SHA, "")


def test_summary_without_inputs():
    md = render(None, None, SHA, "")
    assert "no verdict was produced" in md and SHA in md


def test_summary_shows_assemble_errors():
    md = render(dict(REPORT, errors=["symlink points outside the tree: src/l -> /x"]), None, SHA, "")
    assert "Rejected by the assemble step" in md and "symlink points outside" in md


def test_pr_controlled_strings_cannot_break_markdown():
    report = dict(REPORT)
    report["classification"] = dict(REPORT["classification"], protected_modified=["a`<img src=x>\n# h"])
    md = render(report, VERDICT, SHA, "")
    assert "\n# h" not in md
    assert "`a'<img src=x>\\x0a# h`" in md


def test_main_reads_json_files(tmp_path, capsys):
    (tmp_path / "r.json").write_text(json.dumps(REPORT))
    (tmp_path / "v.json").write_text(json.dumps(VERDICT))
    assert main(["--assemble", str(tmp_path / "r.json"), "--verdict", str(tmp_path / "v.json"), "--head-sha", SHA]) == 0
    assert "Gate summary" in capsys.readouterr().out
    assert main(["--assemble", str(tmp_path / "missing.json"), "--head-sha", SHA]) == 0

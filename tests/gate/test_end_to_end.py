"""Assemble a tree, run pytest in it and evaluate the verdict (offline, no install)."""
import subprocess
import sys

from assemble import assemble
from conftest import BASE_FILES
from verdict import evaluate, parse_junit

PYTEST_INI = "[pytest]\npythonpath = src\n"


def run_pytest(cwd, junit):
    subprocess.run(
        [sys.executable, "-m", "pytest", "-c", "pytest.ini", "-p", "no:cacheprovider", "--junitxml", str(junit), "tests"],
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    return parse_junit(str(junit))


def gate(trees, tmp_path, pr_changes=None, pr_delete=()):
    base_files = dict(BASE_FILES, **{"pytest.ini": PYTEST_INI})
    base, pr, out = trees(pr_changes, pr_delete, base_files=base_files)
    assemble(str(base), str(pr), str(out))
    base_ids = run_pytest(base, tmp_path / "base.xml")
    gate_ids = run_pytest(out, tmp_path / "gate.xml")
    return evaluate(base_ids, gate_ids)


def test_untouched_pr_passes(trees, tmp_path):
    verdict = gate(trees, tmp_path)
    assert verdict["passed"] and verdict["base_total"] == 2


def test_broken_source_fails_even_if_the_pr_rewrote_the_tests(trees, tmp_path):
    verdict = gate(
        trees,
        tmp_path,
        pr_changes={
            "src/demo/__init__.py": "def add(a, b):\n    return 0\n",
            "tests/test_add.py": "def test_add():\n    assert True\n",
        },
    )
    assert not verdict["passed"]
    assert list(verdict["not_passed"]) == ["tests.test_add::test_add"]


def test_deleting_the_failing_test_does_not_help(trees, tmp_path):
    verdict = gate(
        trees,
        tmp_path,
        pr_changes={"src/demo/__init__.py": "def add(a, b):\n    return 0\n"},
        pr_delete=["tests/test_add.py"],
    )
    assert not verdict["passed"]
    assert "tests.test_add::test_add" in verdict["not_passed"]


def test_new_passing_test_is_counted(trees, tmp_path):
    verdict = gate(trees, tmp_path, pr_changes={"tests/test_new.py": "def test_new():\n    assert True\n"})
    assert verdict["passed"] and verdict["new_total"] == 1


def test_new_failing_test_fails_the_gate(trees, tmp_path):
    verdict = gate(trees, tmp_path, pr_changes={"tests/test_new.py": "def test_new():\n    assert False\n"})
    assert not verdict["passed"]
    assert list(verdict["new_failed"]) == ["tests.test_new::test_new"]

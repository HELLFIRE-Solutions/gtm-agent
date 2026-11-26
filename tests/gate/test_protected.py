import pytest

from protected import classify, new_src_toplevel, protected_reason

BASE = {"tests/test_a.py", "tests/data/x.json", "src/pkg/mod.py", "pyproject.toml"}


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/gate.yml",
        ".github/gate/verdict.py",
        ".claude/settings.json",
        "pkg/.claude/x",
        "pyproject.toml",
        "conftest.py",
        "tests/conftest.py",
        "src/pkg/conftest.py",
        "CLAUDE.md",
        "tests/new/pytest.ini",
        "tox.ini",
        "setup.cfg",
        "setup.py",
        "sitecustomize.py",
        "evil.pth",
        "tests/test_a.py",
        "tests/data/x.json",
    ],
)
def test_protected(path):
    assert protected_reason(path, BASE) is not None


@pytest.mark.parametrize(
    "path",
    ["src/pkg/mod.py", "tests/test_new.py", "docs/guide.md", "README.md", "src/pkg/setup.py", "scripts/run.py"],
)
def test_not_protected(path):
    assert protected_reason(path, BASE) is None


def test_classify_all_categories():
    changes = {
        "tests/test_a.py": "modified",
        "tests/data/x.json": "deleted",
        "tests/test_new.py": "added",
        "tests/conftest.py": "added",
        "conftest.py": "added",
        ".github/workflows/gate.yml": "modified",
        "pyproject.toml": "modified",
        "src/pkg/mod.py": "modified",
        "docs/a.md": "added",
    }
    c = classify(changes, BASE)
    assert set(c.protected_modified) == {
        "tests/test_a.py",
        "tests/conftest.py",
        "conftest.py",
        ".github/workflows/gate.yml",
        "pyproject.toml",
    }
    assert c.protected_deleted == ["tests/data/x.json"]
    assert c.tests_added == ["tests/test_new.py"]
    assert sorted(c.other) == ["docs/a.md", "src/pkg/mod.py"]
    assert c.tests_modified == ["tests/test_a.py"]
    assert c.tests_deleted == ["tests/data/x.json"]
    assert set(c.protected_added) == {"tests/conftest.py", "conftest.py"}


def test_classify_empty_pr():
    c = classify({}, BASE)
    assert not (c.protected_modified or c.protected_deleted or c.tests_added or c.other)


def test_classify_rejects_unknown_status():
    with pytest.raises(ValueError):
        classify({"a.py": "renamed"}, BASE)


def test_new_src_toplevel():
    pr = BASE | {"src/pytest_extra/__init__.py", "src/pkg/new.py"}
    assert new_src_toplevel(BASE, pr) == ["pytest_extra"]

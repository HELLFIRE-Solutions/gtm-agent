import json
import os

import pytest

import assemble as asm
from assemble import AssembleError, assemble, main


def read(path):
    return path.read_text(encoding="utf-8")


def test_pr_deletes_existing_test_it_is_restored(trees):
    base, pr, out = trees(pr_delete=["tests/test_zero.py"])
    report = assemble(str(base), str(pr), str(out))
    assert (out / "tests/test_zero.py").is_file()
    assert report["classification"]["tests_deleted"] == ["tests/test_zero.py"]
    assert "tests/test_zero.py" in report["classification"]["protected_deleted"]


def test_pr_edits_existing_test_base_version_wins_and_is_reported(trees):
    weakened = "def test_add():\n    assert True\n"
    base, pr, out = trees({"tests/test_add.py": weakened})
    report = assemble(str(base), str(pr), str(out))
    assert read(out / "tests/test_add.py") == read(base / "tests/test_add.py")
    assert report["classification"]["tests_modified"] == ["tests/test_add.py"]


def test_pr_adds_test_it_is_included(trees):
    base, pr, out = trees({"tests/test_new.py": "def test_new():\n    pass\n"})
    report = assemble(str(base), str(pr), str(out))
    assert read(out / "tests/test_new.py") == "def test_new():\n    pass\n"
    assert report["classification"]["tests_added"] == ["tests/test_new.py"]


def test_source_comes_from_pr(trees):
    base, pr, out = trees({"src/demo/__init__.py": "def add(a, b):\n    return 42\n"})
    assemble(str(base), str(pr), str(out))
    assert "42" in read(out / "src/demo/__init__.py")


@pytest.mark.parametrize("path", ["conftest.py", "tests/conftest.py", "tests/sub/conftest.py", "src/demo/conftest.py"])
def test_added_conftest_is_reported_and_dropped(trees, path):
    base, pr, out = trees({path: "import pytest\n"})
    report = assemble(str(base), str(pr), str(out))
    assert path in report["classification"]["protected_modified"]
    assert path in report["classification"]["protected_added"]
    assert not (out / path).exists()


def test_github_and_pyproject_changes_reported_base_version_used(trees):
    base, pr, out = trees(
        {
            ".github/workflows/gate.yml": "name: weakened\n",
            ".github/workflows/extra.yml": "name: extra\n",
            "pyproject.toml": '[project]\nname = "demo"\ndependencies = ["evil"]\n',
        }
    )
    report = assemble(str(base), str(pr), str(out))
    cls = report["classification"]
    assert {".github/workflows/gate.yml", ".github/workflows/extra.yml", "pyproject.toml"} <= set(
        cls["protected_modified"]
    )
    assert read(out / ".github/workflows/gate.yml") == "name: gate\n"
    assert not (out / ".github/workflows/extra.yml").exists()
    assert read(out / "pyproject.toml") == read(base / "pyproject.toml")
    assert any("evil" in line for line in report["pyproject_diff"])


def test_pr_deleting_protected_file_is_restored(trees):
    base, pr, out = trees(pr_delete=[".github/workflows/gate.yml", "pyproject.toml"])
    report = assemble(str(base), str(pr), str(out))
    assert (out / ".github/workflows/gate.yml").is_file()
    assert (out / "pyproject.toml").is_file()
    assert set(report["classification"]["protected_deleted"]) == {".github/workflows/gate.yml", "pyproject.toml"}


def test_pytest_config_comes_from_base(trees):
    cfg = "[pytest]\naddopts = -q\n"
    base_files = {"pytest.ini": cfg, "tests/test_a.py": "def test_a():\n    pass\n", "src/demo/__init__.py": ""}
    base, pr, out = trees(
        {"pytest.ini": "[pytest]\naddopts = -k nothing\n", "tests/pytest.ini": "[pytest]\n", "tox.ini": "[pytest]\n"},
        base_files=base_files,
    )
    report = assemble(str(base), str(pr), str(out))
    assert report["pytest_config"] == "pytest.ini"
    assert read(out / "pytest.ini") == cfg
    assert not (out / "tests/pytest.ini").exists()
    assert not (out / "tox.ini").exists()


def test_empty_pytest_config_is_synthesised_when_base_has_none(trees):
    base, pr, out = trees()
    report = assemble(str(base), str(pr), str(out))
    assert report["pytest_config"] == "pytest.ini"
    assert (out / "pytest.ini").is_file() and (base / "pytest.ini").is_file()


def test_pyproject_pytest_section_is_found(trees):
    base_files = {"pyproject.toml": "[tool.pytest.ini_options]\naddopts = '-q'\n", "tests/test_a.py": ""}
    base, pr, out = trees(base_files=base_files)
    assert assemble(str(base), str(pr), str(out))["pytest_config"] == "pyproject.toml"


def test_root_module_added_by_pr_is_dropped(trees):
    base, pr, out = trees({"sitecustomize.py": "print('x')\n", "requests.py": ""})
    report = assemble(str(base), str(pr), str(out))
    assert not (out / "sitecustomize.py").exists() and not (out / "requests.py").exists()
    assert "sitecustomize.py" in report["classification"]["protected_added"]


def test_new_top_level_src_package_is_reported(trees):
    base, pr, out = trees({"src/_pytest/__init__.py": ""})
    report = assemble(str(base), str(pr), str(out))
    assert report["new_src_toplevel"] == ["_pytest"]


def test_empty_pr(trees):
    base, pr, out = trees()
    report = assemble(str(base), str(pr), str(out))
    assert report["changes"] == {}
    cls = report["classification"]
    assert not (cls["protected_modified"] or cls["protected_deleted"] or cls["tests_added"] or cls["other"])
    assert (out / "tests/test_add.py").is_file() and (out / "src/demo/__init__.py").is_file()


def test_git_directories_are_ignored(trees):
    base, pr, out = trees({".git/config": "evil\n"})
    report = assemble(str(base), str(pr), str(out))
    assert report["changes"] == {}
    assert not (out / ".git").exists()


def test_pr_replacing_tests_dir_with_file_still_gets_base_tests(trees):
    base, pr, out = trees({"tests": "not a directory\n"}, pr_delete=["tests/test_add.py", "tests/test_zero.py"])
    assemble(str(base), str(pr), str(out))
    assert (out / "tests/test_add.py").is_file()


# ----------------------------------------------------------------------- symlinks


def test_symlink_escaping_the_tree_is_rejected(trees):
    base, pr, out = trees({"src/demo/link": ("link", "../../../outside")})
    with pytest.raises(AssembleError) as exc:
        assemble(str(base), str(pr), str(out))
    assert any("outside the tree" in e and "src/demo/link" in e for e in exc.value.errors)
    assert exc.value.report["errors"]
    assert not out.exists()


def test_symlink_with_absolute_target_is_rejected(trees):
    base, pr, out = trees({"src/demo/abs": ("link", "/etc/passwd")})
    with pytest.raises(AssembleError) as exc:
        assemble(str(base), str(pr), str(out))
    assert any("absolute target" in e for e in exc.value.errors)


def test_symlink_in_protected_path_is_rejected(trees):
    base, pr, out = trees({"conftest.py": ("link", "src/demo/__init__.py"), ".github/x": ("link", "../README.md")})
    with pytest.raises(AssembleError) as exc:
        assemble(str(base), str(pr), str(out))
    joined = "\n".join(exc.value.errors)
    assert "protected path: conftest.py" in joined and "protected path: .github/x" in joined


def test_new_symlink_under_tests_is_rejected(trees):
    base, pr, out = trees({"tests/test_link.py": ("link", "../src/demo/__init__.py")})
    with pytest.raises(AssembleError) as exc:
        assemble(str(base), str(pr), str(out))
    assert any("under tests/" in e for e in exc.value.errors)


def test_symlink_inside_the_tree_is_allowed_and_not_followed(trees):
    base, pr, out = trees({"docs_link": ("link", "src/demo")})
    report = assemble(str(base), str(pr), str(out))
    assert os.path.islink(out / "docs_link")
    assert report["classification"]["other"] == ["docs_link"]


def test_place_does_not_write_through_a_symlinked_parent(tmp_path):
    out = tmp_path / "out"
    victim = tmp_path / "victim"
    victim.mkdir()
    out.mkdir()
    os.symlink(str(victim), out / "tests")
    src = tmp_path / "src"
    (src / "tests").mkdir(parents=True)
    (src / "tests/test_a.py").write_text("base\n")
    asm._place(str(out), "tests/test_a.py", str(src), ("file", "x"))
    assert not os.path.islink(out / "tests")
    assert (out / "tests/test_a.py").read_text() == "base\n"
    assert list(victim.iterdir()) == []


# ---------------------------------------------------------------------------- main


def test_main_writes_report_and_config_file(trees, tmp_path, capsys):
    base, pr, out = trees({"tests/test_new.py": ""})
    report_path = tmp_path / "o" / "assemble.json"
    rc = main(["--base", str(base), "--pr", str(pr), "--out", str(out), "--report", str(report_path)])
    assert rc == 0
    assert json.loads(report_path.read_text())["classification"]["tests_added"] == ["tests/test_new.py"]
    assert (tmp_path / "o" / "pytest-config.txt").read_text().strip() == "pytest.ini"
    assert "new tests: 1" in capsys.readouterr().out


def test_main_reports_symlink_error_with_exit_code_1(trees, tmp_path, capsys):
    base, pr, out = trees({"src/demo/link": ("link", "../../../../x")})
    report_path = tmp_path / "o" / "assemble.json"
    rc = main(["--base", str(base), "--pr", str(pr), "--out", str(out), "--report", str(report_path)])
    assert rc == 1
    assert json.loads(report_path.read_text())["errors"]
    assert "ASSEMBLE FAILED" in capsys.readouterr().out


def test_nonempty_output_directory_is_refused(trees):
    base, pr, out = trees()
    out.mkdir()
    (out / "stale").write_text("x")
    with pytest.raises(AssembleError):
        assemble(str(base), str(pr), str(out))


def test_scan_records_links_without_following(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d/f.txt").write_text("a")
    os.symlink("d", tmp_path / "dl")
    entries = asm.scan(str(tmp_path))
    assert entries["dl"] == ("link", "d")
    assert "dl/f.txt" not in entries and "d/f.txt" in entries

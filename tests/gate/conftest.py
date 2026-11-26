"""Make the gate scripts in .github/gate importable and provide tree helpers."""
import os
import sys
from pathlib import Path

import pytest

GATE_DIR = Path(__file__).resolve().parents[2] / ".github" / "gate"
if str(GATE_DIR) not in sys.path:
    sys.path.insert(0, str(GATE_DIR))


def build_tree(root: Path, files: dict) -> Path:
    """Create ``files`` under ``root``.

    A value is the file text, or ``("link", target)`` for a symlink.
    """
    root.mkdir(parents=True, exist_ok=True)
    for rel, value in files.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, tuple):
            os.symlink(value[1], dest)
        else:
            dest.write_text(value, encoding="utf-8")
    return root


BASE_FILES = {
    "pyproject.toml": '[project]\nname = "demo"\ndependencies = []\n',
    "src/demo/__init__.py": "def add(a, b):\n    return a + b\n",
    "tests/test_add.py": "from demo import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    "tests/test_zero.py": "from demo import add\n\n\ndef test_zero():\n    assert add(0, 0) == 0\n",
    ".github/workflows/gate.yml": "name: gate\n",
    "README.md": "demo\n",
}


@pytest.fixture
def trees(tmp_path):
    """Return a function (pr_files) -> (base, pr, out) paths; PR starts as a copy of base."""

    def make(pr_changes=None, pr_delete=(), base_files=None):
        base_files = dict(BASE_FILES if base_files is None else base_files)
        base = build_tree(tmp_path / "base", base_files)
        pr_files = dict(base_files)
        for rel in pr_delete:
            pr_files.pop(rel)
        pr_files.update(pr_changes or {})
        pr = build_tree(tmp_path / "pr", pr_files)
        return base, pr, tmp_path / "out"

    return make

from pathlib import Path
from types import SimpleNamespace

import pytest

from llm_fuzz_ci.pytest_plugin import _target_from_marker


def test_budget_marker_infers_target_from_pytest_item(tmp_path):
    def test_checkout_security():
        """Checkout totals must not trust user-controlled discount values."""

    item = SimpleNamespace(
        nodeid="tests/test_checkout.py::test_checkout_security",
        path=tmp_path / "tests" / "test_checkout.py",
        obj=test_checkout_security,
    )
    marker = SimpleNamespace(args=(), kwargs={"budget_usd": 0.25})

    target = _target_from_marker(item, marker)

    assert target.id == "tests/test_checkout.py::test_checkout_security"
    assert target.target == "pytest::tests/test_checkout.py::test_checkout_security"
    assert target.budget_usd == 0.25
    assert target.description == "Checkout totals must not trust user-controlled discount values."
    assert target.source_file == str(Path(tmp_path / "tests" / "test_checkout.py"))


def test_marker_rejects_positional_arguments(tmp_path):
    item = SimpleNamespace(
        nodeid="tests/test_app.py::test_policy",
        path=tmp_path / "tests" / "test_app.py",
        obj=lambda: None,
    )
    marker = SimpleNamespace(args=(0.5,), kwargs={})

    with pytest.raises(pytest.UsageError, match="does not accept positional arguments"):
        _target_from_marker(item, marker)


def test_marker_requires_budget(tmp_path):
    item = SimpleNamespace(
        nodeid="tests/test_app.py::test_policy",
        path=tmp_path / "tests" / "test_app.py",
        obj=lambda: None,
    )
    marker = SimpleNamespace(args=(), kwargs={})

    with pytest.raises(pytest.UsageError, match="requires budget_usd"):
        _target_from_marker(item, marker)


def test_marker_rejects_extra_keyword_arguments(tmp_path):
    item = SimpleNamespace(
        nodeid="tests/test_app.py::test_policy",
        path=tmp_path / "tests" / "test_app.py",
        obj=lambda: None,
    )
    marker = SimpleNamespace(args=(), kwargs={"budget_usd": 0.5, "params": ["x"]})

    with pytest.raises(pytest.UsageError, match="params"):
        _target_from_marker(item, marker)


def test_marker_rejects_invalid_budget(tmp_path):
    item = SimpleNamespace(
        nodeid="tests/test_app.py::test_policy",
        path=tmp_path / "tests" / "test_app.py",
        obj=lambda: None,
    )
    marker = SimpleNamespace(args=(), kwargs={"budget_usd": 0})

    with pytest.raises(pytest.UsageError, match="greater than 0"):
        _target_from_marker(item, marker)

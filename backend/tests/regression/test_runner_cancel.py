"""
Regression tests for the cancel/kill functions in runner.py.

These test the in-process Python functions directly, not via HTTP.
Covers:
  cancel_run()
  cancel_run_file()
  get_active_files()
"""

from unittest.mock import MagicMock

import pytest

from app.services.runner import _active_runs, cancel_run, cancel_run_file, get_active_files


def _make_mock_proc(poll_return=None):
    """Create a mock Popen with configurable poll() return."""
    proc = MagicMock()
    proc.poll.return_value = poll_return
    return proc


@pytest.fixture(autouse=True)
def clean_active_runs():
    """Ensure _active_runs is clean before and after each test."""
    _active_runs.clear()
    yield
    _active_runs.clear()


class TestCancelRun:
    def test_cancel_kills_running_processes(self):
        p1 = _make_mock_proc(poll_return=None)  # still running
        p2 = _make_mock_proc(poll_return=None)
        _active_runs[1] = {"file_a": p1, "file_b": p2}

        killed = cancel_run(1)

        assert killed == 2
        p1.kill.assert_called_once()
        p2.kill.assert_called_once()
        assert 1 not in _active_runs

    def test_cancel_skips_finished_processes(self):
        p1 = _make_mock_proc(poll_return=0)  # already finished
        p2 = _make_mock_proc(poll_return=None)  # still running
        _active_runs[1] = {"file_a": p1, "file_b": p2}

        killed = cancel_run(1)

        assert killed == 1
        p1.kill.assert_not_called()
        p2.kill.assert_called_once()

    def test_cancel_nonexistent_run(self):
        killed = cancel_run(999)
        assert killed == 0

    def test_cancel_empty_run(self):
        _active_runs[1] = {}
        killed = cancel_run(1)
        assert killed == 0


class TestCancelRunFile:
    def test_kill_running_file(self):
        proc = _make_mock_proc(poll_return=None)
        _active_runs[1] = {"tests/test_foo.py": proc}

        result = cancel_run_file(1, "tests/test_foo.py")

        assert result == "killed"
        proc.kill.assert_called_once()

    def test_already_finished_file(self):
        proc = _make_mock_proc(poll_return=0)
        _active_runs[1] = {"tests/test_foo.py": proc}

        result = cancel_run_file(1, "tests/test_foo.py")

        assert result == "already_finished"
        proc.kill.assert_not_called()

    def test_not_found_file(self):
        _active_runs[1] = {"tests/test_foo.py": _make_mock_proc()}

        result = cancel_run_file(1, "tests/test_bar.py")

        assert result == "not_found"

    def test_not_found_run(self):
        result = cancel_run_file(999, "tests/test_foo.py")
        assert result == "not_found"


class TestGetActiveFiles:
    def test_returns_running_files(self):
        _active_runs[1] = {
            "tests/test_a.py": _make_mock_proc(poll_return=None),  # running
            "tests/test_b.py": _make_mock_proc(poll_return=0),  # finished
            "tests/test_c.py": _make_mock_proc(poll_return=None),  # running
        }

        active = get_active_files(1)

        assert sorted(active) == ["tests/test_a.py", "tests/test_c.py"]

    def test_empty_when_all_finished(self):
        _active_runs[1] = {
            "tests/test_a.py": _make_mock_proc(poll_return=0),
        }
        assert get_active_files(1) == []

    def test_empty_for_unknown_run(self):
        assert get_active_files(999) == []

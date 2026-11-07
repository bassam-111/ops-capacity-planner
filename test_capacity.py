"""Tests for capacity.py — run with: python3 test_capacity.py"""

import os
import tempfile

import pandas as pd

from capacity import build_report, load_tasks, plan_capacity, working_days

TASKS = pd.DataFrame(
    [
        {"task_id": "A", "title": "Small task", "owner": "Bassam",
         "effort_hours": 4, "due_date": pd.Timestamp("2026-11-10"),
         "status": "open"},
        {"task_id": "B", "title": "Done task", "owner": "Bassam",
         "effort_hours": 9, "due_date": pd.Timestamp("2026-11-09"),
         "status": "done"},
        {"task_id": "C", "title": "Overdue task", "owner": "Ayesha",
         "effort_hours": 3, "due_date": pd.Timestamp("2026-11-05"),
         "status": "open"},
        {"task_id": "D", "title": "Too big to fit", "owner": "Omar",
         "effort_hours": 20, "due_date": pd.Timestamp("2026-11-10"),
         "status": "open"},
    ]
)
START = pd.Timestamp("2026-11-06")  # a Friday


def test_working_days_skip_weekends():
    days = working_days(pd.Timestamp("2026-11-06"), pd.Timestamp("2026-11-10"))
    assert list(days.day_name()) == ["Friday", "Monday", "Tuesday"], days
    assert len(working_days(pd.Timestamp("2026-11-10"),
                            pd.Timestamp("2026-11-09"))) == 0


def test_done_tasks_excluded_and_hours_spread():
    day_load, flags = plan_capacity(TASKS, START, 6.0)
    bassam = day_load[day_load["owner"] == "Bassam"]
    # Task A: 4 hrs over Fri/Mon/Tue = 1.33 hrs/day; done task B ignored.
    assert len(bassam) == 3, bassam
    assert abs(bassam["hours"].sum() - 4.0) < 0.01, bassam
    assert not day_load[day_load["owner"] == "Bassam"]["overloaded"].any()


def test_overdue_and_at_risk_flags():
    _, flags = plan_capacity(TASKS, START, 6.0)
    assert any("OVERDUE" in f and "C" in f for f in flags), flags
    assert any("AT RISK" in f and "D" in f for f in flags), flags


def test_overloaded_day_flagged():
    busy = TASKS.copy()
    busy.loc[busy["task_id"] == "A", "effort_hours"] = 30  # 10 hrs/day > 6 cap
    day_load, flags = plan_capacity(busy, START, 6.0)
    assert day_load["overloaded"].any()
    assert any("OVERLOADED" in f and "Bassam" in f for f in flags), flags


def test_sample_csv_loads_and_plans():
    df = load_tasks("data/tasks.csv")
    assert len(df) == 12
    day_load, flags = plan_capacity(df, pd.Timestamp("2026-11-06"), 6.0)
    assert not day_load.empty
    report = build_report(df, day_load, flags, pd.Timestamp("2026-11-06"), 6.0)
    assert "OPS CAPACITY PLAN" in report
    assert "OVERDUE" in report  # T-112 is due 2026-11-05


def test_empty_tasks_csv():
    path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as handle:
            handle.write("task_id,title,owner,effort_hours,due_date,status\n")
            path = handle.name
        df = load_tasks(path)
        day_load, flags = plan_capacity(df, START, 6.0)
        report = build_report(df, day_load, flags, START, 6.0)
        assert df.empty
        assert day_load.empty
        assert flags == []
        assert "Tasks: 0 total, 0 open, 0 done, 0.0 open hours" in report
        assert "(no open work scheduled)" in report
    finally:
        if path is not None:
            os.unlink(path)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed.")

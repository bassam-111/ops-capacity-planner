"""Ops Capacity Planner.

Reads a CSV of operations tasks (owner, effort in hours, due date, status)
and spreads each task's remaining effort evenly across the working days
left before its deadline. It then compares each person's daily load
against their daily capacity and flags:

  * overloaded days  - planned hours above daily capacity
  * at-risk tasks    - not enough working days left to fit the effort
  * overdue tasks    - due before the planning start date

Usage:
    python3 capacity.py                  # plan from today, data/tasks.csv
    python3 capacity.py --start 2026-11-09 --capacity 6
    python3 capacity.py --tasks my-tasks.csv --out output/

Only the standard library and pandas are used.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

DEFAULT_DAILY_CAPACITY_HOURS = 6.0


def load_tasks(path):
    """Read the tasks CSV and normalise the columns we need."""
    df = pd.read_csv(path, parse_dates=["due_date"])
    required = {"task_id", "title", "owner", "effort_hours", "due_date", "status"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"tasks file is missing columns: {sorted(missing)}")
    df["effort_hours"] = pd.to_numeric(df["effort_hours"], errors="coerce").fillna(0)
    df["status"] = df["status"].str.strip().str.lower()
    return df


def working_days(start, end):
    """Business days (Mon-Fri) from start to end, inclusive."""
    if end < start:
        return pd.DatetimeIndex([])
    return pd.bdate_range(start=start, end=end)


def plan_capacity(df, start, daily_capacity):
    """Build the per-person, per-day load plan and collect flags.

    Returns (day_load, flags) where day_load is a DataFrame with one row
    per owner per working day, and flags is a list of human-readable
    warning strings.
    """
    start = pd.Timestamp(start).normalize()
    flags = []
    load_rows = []

    active = df[df["status"] != "done"].copy()
    for _, task in active.iterrows():
        due = pd.Timestamp(task["due_date"]).normalize()
        days = working_days(start, due)
        if len(days) == 0:
            flags.append(
                f"OVERDUE: {task['task_id']} '{task['title']}' "
                f"({task['owner']}) was due {due.date()}."
            )
            continue
        per_day = task["effort_hours"] / len(days)
        if per_day > daily_capacity:
            flags.append(
                f"AT RISK: {task['task_id']} '{task['title']}' "
                f"({task['owner']}) needs {per_day:.1f} hrs/day over "
                f"{len(days)} working day(s) before {due.date()} "
                f"(capacity {daily_capacity:.1f} hrs/day)."
            )
        for day in days:
            load_rows.append(
                {
                    "date": day.date(),
                    "owner": task["owner"],
                    "task_id": task["task_id"],
                    "hours": round(per_day, 2),
                }
            )

    if load_rows:
        day_load = pd.DataFrame(load_rows)
        day_load = (
            day_load.groupby(["date", "owner"], as_index=False)["hours"]
            .sum()
            .sort_values(["date", "owner"])
        )
    else:
        day_load = pd.DataFrame(columns=["date", "owner", "hours"])

    day_load["capacity"] = daily_capacity
    day_load["overloaded"] = day_load["hours"] > daily_capacity
    for _, row in day_load[day_load["overloaded"]].iterrows():
        flags.append(
            f"OVERLOADED: {row['owner']} on {row['date']} "
            f"has {row['hours']:.1f} hrs planned "
            f"(capacity {daily_capacity:.1f} hrs)."
        )
    return day_load, flags


def build_report(df, day_load, flags, start, daily_capacity):
    """Render the plain-text summary report."""
    lines = [
        "OPS CAPACITY PLAN",
        f"Planning from {pd.Timestamp(start).date()}, "
        f"daily capacity {daily_capacity:.1f} hrs/person",
        "",
    ]
    active = df[df["status"] != "done"]
    done = df[df["status"] == "done"]
    lines.append(
        f"Tasks: {len(df)} total, {len(active)} open, {len(done)} done, "
        f"{active['effort_hours'].sum():.1f} open hours"
    )
    lines.append("")
    lines.append("Load by person:")
    if not day_load.empty:
        summary = day_load.groupby("owner")["hours"].agg(["sum", "max", "count"])
        for owner, row in summary.iterrows():
            lines.append(
                f"  {owner}: {row['sum']:.1f} hrs planned over "
                f"{int(row['count'])} working day(s), "
                f"busiest day {row['max']:.1f} hrs"
            )
    else:
        lines.append("  (no open work scheduled)")
    lines.append("")
    if flags:
        lines.append(f"Flags ({len(flags)}):")
        for flag in flags:
            lines.append(f"  - {flag}")
    else:
        lines.append("No flags: everything fits within capacity.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan ops team capacity.")
    parser.add_argument("--tasks", default="data/tasks.csv",
                        help="tasks CSV file (default: data/tasks.csv)")
    parser.add_argument("--start", default=None,
                        help="planning start date YYYY-MM-DD (default: today)")
    parser.add_argument("--capacity", type=float,
                        default=DEFAULT_DAILY_CAPACITY_HOURS,
                        help="billable hours per person per day (default: 6)")
    parser.add_argument("--out", default="output",
                        help="output directory (default: output)")
    args = parser.parse_args(argv)

    start = pd.Timestamp(args.start) if args.start else pd.Timestamp.today().normalize()
    df = load_tasks(args.tasks)
    day_load, flags = plan_capacity(df, start, args.capacity)
    report = build_report(df, day_load, flags, start, args.capacity)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    day_load.to_csv(out_dir / "plan.csv", index=False)
    (out_dir / "report.md").write_text("# Ops Capacity Plan\n\n```\n" + report + "```\n")
    print(report)
    print(f"Wrote {out_dir / 'plan.csv'} and {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

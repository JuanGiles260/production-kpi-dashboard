"""Generates data/production_log.csv with realistic example data (fixed seed)."""
import csv
import random
from datetime import date, timedelta

random.seed(42)
LINES = {"Line 1": 2.4, "Line 2": 3.0, "Line 3": 1.8}  # ideal cycle time (seconds per unit)
REASONS = ["Changeover", "Material shortage", "Mechanical failure", "Quality check", "Cleaning", "Operator absence"]
WEIGHTS = [30, 20, 18, 12, 12, 8]

rows = []
start = date(2026, 9, 1)
for d in range(14):
    day = start + timedelta(days=d)
    if day.weekday() == 6:  # no production on Sundays
        continue
    for line, cycle in LINES.items():
        for shift in ("Morning", "Afternoon"):
            planned = 480
            downtime = random.choice([0, 10, 15, 20, 30, 45, 60, 90]) if random.random() > 0.15 else 0
            reason = random.choices(REASONS, WEIGHTS)[0] if downtime else ""
            run_min = planned - downtime
            speed = random.uniform(0.78, 0.97)
            total = int(run_min * 60 / cycle * speed)
            good = int(total * random.uniform(0.95, 0.995))
            rows.append([day.isoformat(), line, shift, planned, downtime, reason, cycle, total, good])

with open("data/production_log.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "line", "shift", "planned_time_min", "downtime_min", "downtime_reason",
                "ideal_cycle_time_s", "total_count", "good_count"])
    w.writerows(rows)
print(f"{len(rows)} rows written")

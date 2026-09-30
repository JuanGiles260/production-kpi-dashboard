"""Production KPI dashboard: OEE, availability, performance, quality and downtime Pareto.

Reads a production log (CSV) and writes a self-contained HTML dashboard.
Standard library only, so it runs anywhere Python 3.9+ is installed.

    python oee.py data/production_log.csv -o docs/index.html
"""

from __future__ import annotations

import argparse
import csv
import html
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

REQUIRED = [
    "date", "line", "shift", "planned_time_min", "downtime_min", "downtime_reason",
    "ideal_cycle_time_s", "total_count", "good_count",
]


@dataclass
class Totals:
    """Sums needed to compute OEE for any group of shifts."""

    planned: float = 0.0
    downtime: float = 0.0
    ideal_time_s: float = 0.0  # ideal cycle time x units produced
    total: int = 0
    good: int = 0

    def add(self, row: dict) -> None:
        self.planned += float(row["planned_time_min"])
        self.downtime += float(row["downtime_min"])
        self.ideal_time_s += float(row["ideal_cycle_time_s"]) * int(row["total_count"])
        self.total += int(row["total_count"])
        self.good += int(row["good_count"])

    @property
    def run_time(self) -> float:
        return self.planned - self.downtime

    @property
    def availability(self) -> float:
        return self.run_time / self.planned if self.planned else 0.0

    @property
    def performance(self) -> float:
        return self.ideal_time_s / (self.run_time * 60) if self.run_time else 0.0

    @property
    def quality(self) -> float:
        return self.good / self.total if self.total else 0.0

    @property
    def oee(self) -> float:
        return self.availability * self.performance * self.quality


def load(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    missing = [c for c in REQUIRED if rows and c not in rows[0]]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")
    return rows


def summarize(rows: list[dict]) -> dict:
    overall = Totals()
    by_line: dict[str, Totals] = defaultdict(Totals)
    by_day_line: dict[tuple[str, str], Totals] = defaultdict(Totals)
    downtime: dict[str, float] = defaultdict(float)
    for r in rows:
        overall.add(r)
        by_line[r["line"]].add(r)
        by_day_line[(r["date"], r["line"])].add(r)
        if float(r["downtime_min"]) > 0:
            downtime[r["downtime_reason"] or "Unspecified"] += float(r["downtime_min"])
    days = sorted({r["date"] for r in rows})
    lines = sorted(by_line)
    return {
        "overall": overall,
        "by_line": {k: by_line[k] for k in lines},
        "trend": {ln: [by_day_line[(d, ln)].oee if (d, ln) in by_day_line else None for d in days] for ln in lines},
        "days": days,
        "pareto": sorted(downtime.items(), key=lambda kv: kv[1], reverse=True),
    }


# ---------- HTML rendering (inline SVG, no external libraries) ----------

SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"]


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def bar_chart(items: list[tuple[str, float]], fmt, max_value: float | None = None, label_w: int = 150) -> str:
    """Horizontal bars, single hue, value label at the end of each bar."""
    w, row_h, gap = 520, 26, 10
    h = len(items) * (row_h + gap)
    top = max_value or max(v for _, v in items) or 1
    plot_w = w - label_w - 150
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    for i, (name, v) in enumerate(items):
        y = i * (row_h + gap)
        bw = max(plot_w * v / top, 2)
        parts.append(
            f'<g class="mark"><title>{html.escape(name)}: {fmt(v)}</title>'
            f'<text x="{label_w - 10}" y="{y + row_h / 2}" class="lbl" text-anchor="end" dominant-baseline="middle">{html.escape(name)}</text>'
            f'<rect x="{label_w}" y="{y}" width="{bw:.1f}" height="{row_h}" rx="4" fill="var(--s1)"/>'
            f'<text x="{label_w + bw + 8:.1f}" y="{y + row_h / 2}" class="val" dominant-baseline="middle">{fmt(v)}</text></g>'
        )
    parts.append("</svg>")
    return "".join(parts)


def line_chart(days: list[str], series: dict[str, list[float | None]]) -> str:
    """Daily OEE per line on one y-axis (50-100%), direct labels at the line ends."""
    w, h, left, right, top, bottom = 960, 300, 48, 80, 12, 28
    lo = 0.5
    pw, ph = w - left - right, h - top - bottom
    n = max(len(days) - 1, 1)
    x = lambda i: left + pw * i / n
    y = lambda v: top + ph * (1 - (max(v, lo) - lo) / (1 - lo))
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    for t in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        parts.append(f'<line x1="{left}" x2="{w - right}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="grid"/>'
                     f'<text x="{left - 6}" y="{y(t):.1f}" class="axis" text-anchor="end" dominant-baseline="middle">{int(t * 100)}%</text>')
    for i, d in enumerate(days):
        if i % 3 == 0 or i == len(days) - 1:
            parts.append(f'<text x="{x(i):.1f}" y="{h - 8}" class="axis" text-anchor="middle">{d[5:]}</text>')
    ends = []
    for k, (name, vals) in enumerate(series.items()):
        color = SERIES[k % len(SERIES)]
        pts = [(x(i), y(v), v, days[i]) for i, v in enumerate(vals) if v is not None]
        path = " ".join(f"{'M' if j == 0 else 'L'}{px:.1f},{py:.1f}" for j, (px, py, _, _) in enumerate(pts))
        parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
        for px, py, v, d in pts:
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{color}" stroke="var(--surface)" stroke-width="2">'
                         f'<title>{html.escape(name)} · {d}: {pct(v)}</title></circle>')
        ends.append([pts[-1][1], pts[-1][0], name])
    # Direct labels at the line ends, nudged apart so they never overlap.
    ends.sort()
    for j in range(1, len(ends)):
        ends[j][0] = max(ends[j][0], ends[j - 1][0] + 16)
    for ly, lx, name in ends:
        parts.append(f'<text x="{lx + 10:.1f}" y="{ly + 4:.1f}" class="lbl">{html.escape(name)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render(s: dict, title: str) -> str:
    o = s["overall"]
    tiles = "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{pct(v)}</div><div class="n">{n}</div></div>'
        for k, v, n in [
            ("OEE", o.oee, "Availability × Performance × Quality"),
            ("Availability", o.availability, f"{o.run_time:,.0f} of {o.planned:,.0f} planned min"),
            ("Performance", o.performance, "Actual vs ideal speed"),
            ("Quality", o.quality, f"{o.good:,} good of {o.total:,} units"),
        ]
    )
    legend = "".join(f'<span><i style="background:{SERIES[i]}"></i>{html.escape(n)}</span>' for i, n in enumerate(s["trend"]))
    rows = "".join(
        f"<tr><td>{html.escape(n)}</td><td>{pct(t.availability)}</td><td>{pct(t.performance)}</td>"
        f"<td>{pct(t.quality)}</td><td><b>{pct(t.oee)}</b></td><td>{t.good:,}</td></tr>"
        for n, t in s["by_line"].items()
    )
    total_dt = sum(v for _, v in s["pareto"]) or 1
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#f6f7f5;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--ink3:#8a8984;--line:#e4e4df;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111110;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--ink3:#8f8e86;--line:#2e2e2b;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;color-scheme:dark}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:24px 16px}}
main{{max-width:1040px;margin:0 auto;display:grid;gap:20px}}
h1{{font-size:26px;margin:0}}h2{{font-size:16px;margin:0 0 12px}}.sub{{color:var(--ink2);margin:4px 0 0}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}
.tile,.card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}}
.k{{color:var(--ink2);font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}}
.v{{font-size:34px;font-weight:700;font-variant-numeric:tabular-nums}}.n{{color:var(--ink3);font-size:13px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}@media (max-width:760px){{.grid2{{grid-template-columns:1fr}}}}
.chart{{width:100%;height:auto;display:block}}.lbl{{fill:var(--ink2);font-size:14px}}.val{{fill:var(--ink);font-size:14px;font-weight:600}}
.axis{{fill:var(--ink3);font-size:12px}}.grid{{stroke:var(--line);stroke-width:1}}.mark:hover rect{{opacity:.85}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;color:var(--ink2);font-size:13px;margin-bottom:8px}}
.legend i{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}th,td{{text-align:right;padding:8px;border-bottom:1px solid var(--line)}}
th,td{{white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}.wide{{overflow-x:auto}}.wide .chart{{min-width:620px}}th{{color:var(--ink2);font-size:13px}}.wrap{{overflow-x:auto}}
footer{{color:var(--ink3);font-size:13px}}
</style></head><body><main>
<header><h1>{html.escape(title)}</h1>
<p class="sub">{s["days"][0]} to {s["days"][-1]} · {len(s["by_line"])} lines · generated by <code>oee.py</code> from a production log</p></header>
<section class="tiles">{tiles}</section>
<section class="grid2">
<div class="card"><h2>OEE by line</h2>{bar_chart([(n, t.oee) for n, t in s["by_line"].items()], pct, 1.0, 90)}</div>
<div class="card"><h2>Downtime by reason (Pareto, minutes)</h2>{bar_chart([(r, v) for r, v in s["pareto"]], lambda v: f"{v:,.0f} min · {v / total_dt:.0%}")}</div>
</section>
<section class="card"><h2>Daily OEE by line</h2><div class="legend">{legend}</div><div class="wide">{line_chart(s["days"], s["trend"])}</div></section>
<section class="card"><h2>Summary by line</h2><div class="wrap"><table>
<tr><th>Line</th><th>Availability</th><th>Performance</th><th>Quality</th><th>OEE</th><th>Good units</th></tr>{rows}</table></div></section>
<footer>Example data. OEE = Availability × Performance × Quality. Availability = run time / planned time;
Performance = (ideal cycle time × units) / run time; Quality = good units / total units.</footer>
</main></body></html>"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Build an OEE dashboard (HTML) from a production log CSV.")
    p.add_argument("csv", type=Path, help="Production log with columns: " + ", ".join(REQUIRED))
    p.add_argument("-o", "--output", type=Path, default=Path("dashboard.html"))
    p.add_argument("--title", default="Production KPI Dashboard")
    a = p.parse_args(argv)
    s = summarize(load(a.csv))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(render(s, a.title), encoding="utf-8")
    o = s["overall"]
    print(f"OEE {pct(o.oee)} | Availability {pct(o.availability)} | Performance {pct(o.performance)} | Quality {pct(o.quality)}")
    print(f"Saved to {a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

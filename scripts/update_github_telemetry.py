#!/usr/bin/env python3
"""Generate self-hosted GitHub telemetry SVGs for the profile README.

The activity chart is built from GitHub's own contribution-calendar endpoint.
If GitHub is temporarily unavailable, an existing last-known-good chart is kept
instead of replacing it with an error response or a broken image.
"""

from __future__ import annotations

import argparse
import html.parser
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

USERNAME = "zureealLV"
ROOT = Path(__file__).resolve().parents[1]
TELEMETRY_DIR = ROOT / "assets" / "telemetry"
ACTIVITY_PATH = TELEMETRY_DIR / "activity-graph.svg"
SIGNAL_PATH = TELEMETRY_DIR / "profile-signal.svg"
UTC_PLUS_8 = timezone(timedelta(hours=8))


class ContributionCalendarParser(html.parser.HTMLParser):
    """Read contribution cells without depending on HTML attribute order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: dict[str, date] = {}
        self.tooltips: dict[str, str] = {}
        self._tooltip_id: str | None = None
        self._tooltip_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "td" and attributes.get("data-date") and attributes.get("id"):
            try:
                day = datetime.strptime(attributes["data-date"] or "", "%Y-%m-%d").date()
            except ValueError:
                return
            self.cells[attributes["id"] or ""] = day
        elif tag == "tool-tip" and attributes.get("for"):
            self._tooltip_id = attributes["for"]
            self._tooltip_text = []

    def handle_data(self, data: str) -> None:
        if self._tooltip_id is not None:
            self._tooltip_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "tool-tip" and self._tooltip_id is not None:
            self.tooltips[self._tooltip_id] = "".join(self._tooltip_text).strip()
            self._tooltip_id = None
            self._tooltip_text = []


def fetch_text(url: str, attempts: int = 3) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "zureealLV-profile-readme/2.0",
        },
    )
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"GitHub returned HTTP {response.status}")
                return response.read().decode("utf-8")
        except Exception as error:  # Network errors differ between Python versions.
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"Could not fetch {url}: {last_error}")


def contribution_days(year: int) -> dict[date, int]:
    url = (
        f"https://github.com/users/{USERNAME}/contributions"
        f"?from={year}-01-01&to={year}-12-31"
    )
    page = fetch_text(url)
    calendar = ContributionCalendarParser()
    calendar.feed(page)
    if len(calendar.cells) < 300:
        raise RuntimeError(f"Expected a full contribution calendar, found {len(calendar.cells)} days")

    result: dict[date, int] = {}
    for cell_id, day in calendar.cells.items():
        label = calendar.tooltips.get(cell_id, "")
        count_match = re.search(r"([\d,]+) contributions?\b", label)
        result[day] = int(count_match.group(1).replace(",", "")) if count_match else 0
    return result


def sunday_of(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def render_activity_graph(days: dict[date, int], year: int) -> str:
    today = datetime.now(UTC_PLUS_8).date()
    visible_through = min(today, date(year, 12, 31))
    first_sunday = sunday_of(date(year, 1, 1))
    last_sunday = sunday_of(date(year, 12, 31))
    week_count = (last_sunday - first_sunday).days // 7 + 1
    weekly = defaultdict(int)
    for day, count in days.items():
        if day.year == year and day <= visible_through:
            weekly[sunday_of(day)] += count

    visible_week_count = max(1, min(week_count, (sunday_of(visible_through) - first_sunday).days // 7 + 1))
    values = [weekly[first_sunday + timedelta(days=7 * index)] for index in range(visible_week_count)]
    total = sum(count for day, count in days.items() if day.year == year and day <= visible_through)
    peak = max(values, default=1) or 1

    left, right, top, bottom = 44.0, 856.0, 72.0, 224.0
    step = (right - left) / max(1, week_count - 1)
    points: list[tuple[float, float, int]] = []
    for index, value in enumerate(values):
        x = left + index * step
        y = bottom - (value / peak) * (bottom - top)
        points.append((x, y, value))
    if len(points) == 1:
        points.append((points[0][0] + 0.1, points[0][1], points[0][2]))

    point_string = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
    area_string = f"{left:.1f},{bottom:.1f} {point_string} {points[-1][0]:.1f},{bottom:.1f}"
    grid = "".join(
        f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#25304a" stroke-width="1" opacity=".72"/>'
        for y in (top, top + 38, top + 76, bottom)
    )

    month_labels: list[str] = []
    for month in range(1, 13):
        month_week = (sunday_of(date(year, month, 1)) - first_sunday).days // 7
        x = left + max(0, month_week) * step
        month_labels.append(
            f'<text x="{x:.1f}" y="250" fill="#7d89a6" font-size="9" '
            f'text-anchor="middle" style="font-family:\'Cascadia Mono\',\'Consolas\',monospace">'
            f'{date(year, month, 1).strftime("%b").upper()}</text>'
        )

    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{3.2 if value else 1.7}" '
        f'fill="{"#ff66aa" if value == peak else "#00d4aa"}" opacity="{"1" if value else ".35"}"/>'
        for x, y, value in points
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="280" viewBox="0 0 900 280" role="img" aria-label="NEURAL ACTIVITY LOG — {total} contributions in {year}">
<defs><linearGradient id="edge" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#00d4aa"/><stop offset=".52" stop-color="#ff66aa"/><stop offset="1" stop-color="#6d5dfc"/></linearGradient><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#00d4aa" stop-opacity=".34"/><stop offset="1" stop-color="#5b21b6" stop-opacity=".04"/></linearGradient><filter id="glow"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
<rect width="900" height="280" rx="16" fill="#0d1117"/><rect x=".75" y=".75" width="898.5" height="278.5" rx="15.25" fill="none" stroke="#2d3652" stroke-width="1.5"/><rect width="900" height="4" rx="2" fill="url(#edge)"/>
<text x="28" y="38" fill="#c9d1d9" font-size="18" font-weight="700" style="font-family:'Segoe UI','Noto Sans',Arial,sans-serif">NEURAL ACTIVITY LOG</text>
<text x="872" y="37" fill="#7d89a6" font-size="10" text-anchor="end" letter-spacing="1.1" style="font-family:'Cascadia Mono','Consolas',monospace">SELF-HOSTED · {total} CONTRIBUTIONS · {year}</text>
{grid}<polygon points="{area_string}" fill="url(#area)"/><polyline points="{point_string}" fill="none" stroke="#00d4aa" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)"/>{dots}
{''.join(month_labels)}
<text x="872" y="269" fill="#58647f" font-size="9" text-anchor="end" style="font-family:'Cascadia Mono','Consolas',monospace">GITHUB NATIVE DATA · LAST-KNOWN-GOOD FALLBACK</text>
</svg>
'''


def render_profile_signal() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="260" height="32" viewBox="0 0 260 32" role="img" aria-label="PROFILE SIGNAL: ONLINE">
<defs><linearGradient id="edge" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#00d4aa"/><stop offset=".52" stop-color="#ff66aa"/><stop offset="1" stop-color="#6d5dfc"/></linearGradient><filter id="glow"><feGaussianBlur stdDeviation="1.8" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
<rect x=".75" y=".75" width="258.5" height="30.5" rx="7" fill="#0d1117" stroke="#2d3652" stroke-width="1.5"/><rect x="1" y="1" width="4" height="30" rx="2" fill="url(#edge)"/><circle cx="20" cy="16" r="4" fill="#00d4aa" filter="url(#glow)"/><text x="32" y="20" fill="#c9d1d9" font-size="12" font-weight="700" letter-spacing="1" style="font-family:'Cascadia Mono','Consolas',monospace">PROFILE SIGNAL</text><text x="244" y="20" fill="#ff66aa" font-size="11" font-weight="700" text-anchor="end" letter-spacing=".8" style="font-family:'Cascadia Mono','Consolas',monospace">ONLINE</text>
</svg>
'''


def write_valid_svg(path: Path, content: str) -> None:
    ET.fromstring(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="fail instead of retaining the previous chart")
    args = parser.parse_args()

    write_valid_svg(SIGNAL_PATH, render_profile_signal())
    year = datetime.now(UTC_PLUS_8).year
    try:
        days = contribution_days(year)
        write_valid_svg(ACTIVITY_PATH, render_activity_graph(days, year))
        print(f"GitHub telemetry updated: {sum(days.values())} contributions parsed")
    except Exception as error:
        if args.strict or not ACTIVITY_PATH.exists():
            raise
        print(f"warning: {error}; retained {ACTIVITY_PATH.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

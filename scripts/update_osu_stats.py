#!/usr/bin/env python3
"""Refresh the osu! statistics block in the profile README."""

from __future__ import annotations

import html.parser
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

OSU_USER_ID = 37641269
PROFILE_URL = f"https://osu.ppy.sh/users/{OSU_USER_ID}/osu"
README_PATH = Path(__file__).resolve().parents[1] / "README.md"
START_MARKER = "<!-- OSU_STATS_START -->"
END_MARKER = "<!-- OSU_STATS_END -->"


class ProfilePageParser(html.parser.HTMLParser):
    """Extract the JSON payload attached to osu!'s profile React root."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.initial_data: str | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if attributes.get("data-react") == "profile-page":
            self.initial_data = attributes.get("data-initial-data")


def fetch_profile() -> dict[str, Any]:
    request = urllib.request.Request(
        PROFILE_URL,
        headers={
            "Accept": "text/html",
            "User-Agent": "zureealLV-profile-readme/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        page = response.read().decode("utf-8")

    parser = ProfilePageParser()
    parser.feed(page)
    if parser.initial_data is None:
        raise RuntimeError("Could not find osu! profile data in the page")

    payload = json.loads(parser.initial_data)
    user = payload.get("user")
    if not isinstance(user, dict) or user.get("id") != OSU_USER_ID:
        raise RuntimeError("osu! returned an unexpected user payload")
    return user


def compact_number(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:,}"


def render_stats(user: dict[str, Any]) -> str:
    stats = user["statistics"]
    level = stats["level"]
    grades = stats["grade_counts"]
    country_code = user["country"]["code"]

    pp = f"{stats['pp']:,.2f}"
    global_rank = f"#{stats['global_rank']:,}"
    country_rank = f"#{stats['country_rank']:,}"
    accuracy = f"{stats['hit_accuracy']:.4f}%"
    play_count = f"{stats['play_count']:,}"
    current_level = f"{level['current']}.{level['progress']:02d}"
    max_combo = f"{stats['maximum_combo']:,}×"
    grade_line = f"{grades['ss'] + grades['ssh']:,} / {grades['s'] + grades['sh']:,} / {grades['a']:,}"
    total_score = compact_number(stats["total_score"])
    play_hours = stats["play_time"] // 3600
    total_hits = compact_number(stats["total_hits"])
    synced = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d UTC+8")

    return f"""
<div align="center">

<table>
<tr>
<td align="center" width="150">⚡ <b>PP</b><br/>{pp}</td>
<td align="center" width="150">🌐 <b>Global</b><br/>{global_rank}</td>
<td align="center" width="150">🇸🇬 <b>Country</b><br/>{country_rank}</td>
<td align="center" width="150">🎯 <b>Accuracy</b><br/>{accuracy}</td>
</tr>
<tr>
<td align="center" width="150">🎮 <b>Play Count</b><br/>{play_count}</td>
<td align="center" width="150">⭐ <b>Level</b><br/>{current_level}</td>
<td align="center" width="150">🔥 <b>Max Combo</b><br/>{max_combo}</td>
<td align="center" width="150">🏅 <b>SS / S / A</b><br/>{grade_line}</td>
</tr>
</table>

<sub>Total score: <b>{total_score}</b> · Play time: <b>{play_hours:,}h</b> · Total hits: <b>{total_hits}</b> · Synced: <b>{synced}</b></sub>

</div>
""".strip()


def update_readme(block: str) -> bool:
    readme = README_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"({re.escape(START_MARKER)})(.*?)({re.escape(END_MARKER)})",
        re.DOTALL,
    )
    replacement = rf"\1\n{block}\n\3"
    updated, count = pattern.subn(replacement, readme)
    if count != 1:
        raise RuntimeError(f"Expected one osu! stats block, found {count}")
    if updated == readme:
        return False
    README_PATH.write_text(updated, encoding="utf-8", newline="\n")
    return True


def main() -> None:
    user = fetch_profile()
    changed = update_readme(render_stats(user))
    print("README updated" if changed else "README already current")


if __name__ == "__main__":
    main()

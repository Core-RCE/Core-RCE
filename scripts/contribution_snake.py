"""Build a contribution snake from GitHub's public, dated calendar cells."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


_HANDLE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}\Z")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_COUNT = re.compile(r"\b(No|\d{1,3}(?:,\d{3})+|\d+)\s+contributions?\b", re.I)
_MAX_HTML_BYTES = 4 * 1024 * 1024
_DURATION_SECONDS = 28
_WIDTH, _HEIGHT = 940, 210
_PALETTES = {
    "light": {
        "dots": ("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"),
        "body": "#24292f", "head": "#096b30", "text": "#57606a",
    },
    "dark": {
        "dots": ("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"),
        "body": "#f0f6fc", "head": "#39d353", "text": "#8b949e",
    },
}


def _validate_username(username):
    if not isinstance(username, str) or not _HANDLE.fullmatch(username):
        raise ValueError("Invalid GitHub username: expected a valid 1–39 character handle.")


def _source(username):
    _validate_username(username)
    return f"https://github.com/users/{quote(username, safe='')}/contributions"


def _parse_date(value):
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise ValueError("Contribution dates must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Invalid contribution date: {value}.") from None


def _validate_days(days):
    if not isinstance(days, list) or not 300 <= len(days) <= 380:
        raise ValueError("Expected 300–380 dated contribution cells, not a partial calendar.")
    seen = set()
    normalized = []
    for item in days:
        if not isinstance(item, dict):
            raise ValueError("Contribution day must be an object.")
        day = _parse_date(item.get("date"))
        if day in seen:
            raise ValueError(f"Duplicate contribution date: {day}.")
        seen.add(day)
        level, count = item.get("level"), item.get("count")
        if type(level) is not int or not 0 <= level <= 4:
            raise ValueError(f"Invalid contribution level for {day}: expected 0–4.")
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError(f"Invalid contribution count for {day}.")
        normalized.append({"date": day.isoformat(), "level": level, "count": count})
    normalized.sort(key=lambda item: item["date"])
    first, last = _parse_date(normalized[0]["date"]), _parse_date(normalized[-1]["date"])
    if (last - first).days + 1 != len(normalized):
        raise ValueError("Contribution calendar has missing dates.")
    return normalized


class _CalendarParser(HTMLParser):
    """Read data attributes and tooltip text, without interpreting markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = []
        self.ids = {}
        self.counts = {}
        self.tooltip_target = None
        self.tooltip_text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in ("td", "rect") and "data-date" in attributes:
            day = _parse_date(attributes["data-date"]).isoformat()
            raw_level = attributes.get("data-level", "")
            if not isinstance(raw_level, str) or not re.fullmatch(r"[0-4]", raw_level):
                raise ValueError(f"Invalid contribution level for {day}.")
            item = {"date": day, "level": int(raw_level), "count": None}
            if "data-count" in attributes:
                raw_count = attributes["data-count"]
                if not isinstance(raw_count, str) or not re.fullmatch(r"\d+", raw_count):
                    raise ValueError(f"Invalid contribution count for {day}.")
                item["count"] = int(raw_count)
            identifier = attributes.get("id")
            if identifier:
                if identifier in self.ids:
                    raise ValueError("Duplicate contribution cell identifier.")
                self.ids[identifier] = item
            self.cells.append(item)
        if tag == "tool-tip":
            self.tooltip_target = attributes.get("for")
            self.tooltip_text = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self.tooltip_target:
            self.tooltip_text.append(data)

    def handle_endtag(self, tag):
        if tag != "tool-tip" or not self.tooltip_target:
            return
        match = _COUNT.search(" ".join(self.tooltip_text))
        if match:
            value = match[1]
            count = 0 if value.lower() == "no" else int(value.replace(",", ""))
            previous = self.counts.get(self.tooltip_target)
            if previous is not None and previous != count:
                raise ValueError("Conflicting contribution tooltip counts.")
            self.counts[self.tooltip_target] = count
        self.tooltip_target = None
        self.tooltip_text = []

    def days(self):
        for identifier, item in self.ids.items():
            if identifier in self.counts:
                count = self.counts[identifier]
                if item["count"] is not None and item["count"] != count:
                    raise ValueError("Conflicting contribution cell and tooltip counts.")
                item["count"] = count
        return _validate_days(self.cells)


def _parse_html(content):
    parser = _CalendarParser()
    parser.feed(content)
    parser.close()
    return parser.days()


def fetch_contributions(username):
    """Fetch only the public GitHub HTML calendar; no authentication is used."""
    source = _source(username)
    headers = {
        "User-Agent": "corerce-public-contribution-calendar",
        "Accept": "text/html",
        "Accept-Language": "en-US",
    }
    for attempt in range(3):
        try:
            with urlopen(Request(source, headers=headers), timeout=15) as response:
                body = response.read(_MAX_HTML_BYTES + 1)
        except HTTPError as error:
            status = error.code
            error.close()
            if (status == 429 or 500 <= status <= 599) and attempt < 2:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"GitHub contribution request failed: HTTP {status}.") from None
        except (URLError, TimeoutError, OSError):
            if attempt < 2:
                time.sleep(2**attempt)
                continue
            raise RuntimeError("GitHub contribution request failed: network or timeout error.") from None
        if len(body) > _MAX_HTML_BYTES:
            raise RuntimeError("GitHub contribution response is unexpectedly large.")
        try:
            days = _parse_html(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise RuntimeError(f"Invalid public GitHub contribution calendar: {error}") from None
        return {
            "username": username,
            "source": source,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "days": days,
        }
    raise RuntimeError("GitHub contribution request failed.")


def _validate_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("Contribution snapshot must be an object.")
    username = snapshot.get("username")
    source = _source(username)
    if snapshot.get("source") != source:
        raise ValueError("Contribution snapshot source does not match its GitHub account.")
    updated = snapshot.get("updated_at")
    if not isinstance(updated, str) or not updated.endswith("Z"):
        raise ValueError("Contribution snapshot timestamp must be UTC with a Z suffix.")
    try:
        datetime.fromisoformat(updated.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Contribution snapshot timestamp is invalid.") from None
    return {"username": username, "source": source, "updated_at": updated,
            "days": _validate_days(snapshot.get("days"))}


def load_contributions(path, username):
    """Load an account's cache, returning None only when absent or mismatched."""
    _validate_username(username)
    path = Path(path)
    if not path.exists():
        return None
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError(f"Contribution snapshot is not valid UTF-8 JSON: {path}") from None
    if not isinstance(snapshot, dict):
        raise ValueError("Contribution snapshot must be an object.")
    _validate_username(snapshot.get("username"))
    if snapshot["username"].casefold() != username.casefold():
        return None
    return _validate_snapshot(snapshot)


def _calendar_cells(days):
    first = _parse_date(days[0]["date"])
    sunday = first - timedelta(days=(first.weekday() + 1) % 7)
    cells = []
    for item in days:
        offset = (_parse_date(item["date"]) - sunday).days
        cells.append((offset // 7, offset % 7, item))
    return cells, max(cell[0] for cell in cells) + 1


def _route(columns):
    """A simple closed lattice route: scan seven rows and return outside."""
    if type(columns) is not int or columns < 2:
        raise ValueError("Snake route needs at least two calendar columns.")
    points = []
    for y in range(7):
        xs = range(columns) if y % 2 == 0 else range(columns - 1, -1, -1)
        points.extend((x, y) for x in xs)
    points.extend([(columns - 1, 7), (columns - 1, 8)])
    points.extend((x, 8) for x in range(columns - 2, -3, -1))
    points.extend((-2, y) for y in range(7, -3, -1))
    points.extend([(-1, -2), (0, -2), (0, -1)])
    points.append(points[0])
    return points


def render_snake(snapshot, theme="light"):
    """Return a standalone SVG with truthful cells and a six-segment snake."""
    snapshot = _validate_snapshot(snapshot)
    if theme not in _PALETTES:
        raise ValueError("Snake theme must be light or dark.")
    colors = _PALETTES[theme]
    days = snapshot["days"]
    cells, columns = _calendar_cells(days)
    route = _route(columns)
    steps = len(route) - 1
    arrival = {point: index for index, point in enumerate(route[:-1])}
    cell_size = min(16, 860 / columns)
    dot_size, snake_size = cell_size * 0.6875, cell_size / 2
    left, top = (_WIDTH - columns * cell_size) / 2, 46

    def position(point, size):
        x, y = point
        inset = (cell_size - size) / 2
        return left + x * cell_size + inset, top + y * cell_size + inset

    motion = []
    for index, point in enumerate(route):
        x, y = position(point, snake_size)
        motion.append(f"{index / steps * 100:.6f}%{{transform:translate({x:.3f}px,{y:.3f}px)}}")
    css = [
        f".snake{{animation:travel {_DURATION_SECONDS}s linear infinite;fill:{colors['body']}}}",
        f".head{{fill:{colors['head']}}}",
        "@keyframes travel{" + "".join(motion) + "}",
    ]
    rectangles = []
    for x, y, item in cells:
        level = item["level"]
        color = colors["dots"][level]
        attributes = ""
        if level:
            tick = arrival[(x, y)]
            percentage = tick / steps * 100
            name = f"eat-{tick}"
            css.append(
                f"@keyframes {name}{{0%,{percentage:.6f}%{{fill:{color}}}"
                f"{percentage + .001:.6f}%,98.9%{{fill:{colors['dots'][0]}}}"
                f"99%,100%{{fill:{color}}}}}"
            )
            attributes = f' style="animation:{name} {_DURATION_SECONDS}s linear infinite"'
        px, py = position((x, y), dot_size)
        count = item["count"]
        description = f"{item['date']}：{count} 次贡献" if count is not None else f"{item['date']}：贡献等级 {level}，次数未提供"
        rectangles.append(
            f'<rect class="day" x="{px:.3f}" y="{py:.3f}" width="{dot_size:.3f}" '
            f'height="{dot_size:.3f}" rx="2" fill="{color}" data-date="{item["date"]}" '
            f'data-level="{level}"{attributes}><title>{escape(description)}</title></rect>'
        )
    segments = []
    for index in range(5, -1, -1):
        x, y = position(route[-1 - index], snake_size)
        delay = -_DURATION_SECONDS + index * _DURATION_SECONDS / steps
        segments.append(
            f'<rect class="snake{" head" if index == 0 else ""}" width="{snake_size:.3f}" '
            f'height="{snake_size:.3f}" rx="2" transform="translate({x:.3f},{y:.3f})" '
            f'style="animation-delay:{delay:.6f}s"/>'
        )
    css.append("@media(prefers-reduced-motion:reduce){*{animation:none!important}.snake{display:none}}")
    username = snapshot["username"]
    first, last = days[0]["date"], days[-1]["date"]
    description = (
        f"{username} 的 GitHub 公开贡献贪吃蛇，日期范围 {first} 至 {last}。"
        f"来源：{snapshot['source']}；数据获取时间：{snapshot['updated_at']}。"
        "格子颜色使用公开贡献等级，未提供的贡献次数保持未知。"
    )
    footer = f"{username} · {first} — {last} · 来源：GitHub 公开贡献图"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{_HEIGHT}" '
        f'viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img" aria-labelledby="snake-title snake-description">'
        f'<title id="snake-title">{escape(username)} 的 GitHub 贡献贪吃蛇</title>'
        f'<desc id="snake-description">{escape(description)}</desc>'
        '<style>' + "".join(css) + '</style>' + "".join(rectangles) + "".join(segments)
        + f'<text x="470" y="204" text-anchor="middle" fill="{colors["text"]}" '
          'font-family="ui-monospace,Consolas,monospace" font-size="11">'
        + escape(footer) + '</text></svg>\n'
    )

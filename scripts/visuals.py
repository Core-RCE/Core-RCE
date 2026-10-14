"""Generate the profile's self-contained, monochrome SVG illustrations.

All text is escaped before it reaches XML. Every illustration is visible in
its base state so viewers that disable animation still receive its content.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from html import escape
import math
from pathlib import Path
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
WIDTH = 940
FAMILY = "ProfileMono,ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
TEXT_FAMILY = "ProfileMono,'Microsoft YaHei','PingFang SC','Noto Sans CJK SC',ui-monospace,SFMono-Regular,Menlo,Consolas,sans-serif"


def _safe(value):
    return escape(str(value), quote=True)


def _display_width(value):
    """Use terminal-style columns to budget mixed Latin and CJK text."""
    return sum(0 if unicodedata.combining(char) else
               2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
               for char in str(value))


def _prefix(value, width):
    result, used = [], 0
    for char in value:
        char_width = _display_width(char)
        if used + char_width > width:
            break
        result.append(char)
        used += char_width
    return "".join(result)


def _short(value, length):
    value = " ".join(str(value).split())
    return value if _display_width(value) <= length else _prefix(value, max(0, length - 1)) + "…"


def _wrap(value, width, maximum=3):
    width = max(2, width)
    remaining = " ".join(str(value).split())
    lines = []
    while _display_width(remaining) > width:
        line = _prefix(remaining, width)
        # Prefer word boundaries for English while allowing Chinese to wrap
        # without spaces. Long identifiers are split at the column budget.
        space = line.rfind(" ")
        if space > 0:
            line = line[:space]
        lines.append(line.rstrip())
        remaining = remaining[len(line):].lstrip()
    lines.append(remaining)
    if len(lines) > maximum:
        lines = lines[:maximum]
        lines[-1] = _short(lines[-1] + "…", width)
    return lines


@lru_cache(maxsize=1)
def _font_css():
    faces = []
    for weight, filename in ((400, "JetBrainsMono-Regular.woff2"),
                             (600, "JetBrainsMono-SemiBold.woff2")):
        path = ROOT / "assets" / "fonts" / filename
        if not path.is_file():
            raise FileNotFoundError(f"缺少个人主页所需字体：{path}")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        faces.append(f"@font-face{{font-family:ProfileMono;font-style:normal;"
                     f"font-weight:{weight};font-display:block;"
                     f"src:url(data:font/woff2;base64,{encoded}) format('woff2')}}")
    return "".join(faces)


CSS = """
.ink{fill:#24292f}.muted{fill:#57606a}.data{fill:#6e7681}
.rule{stroke:#d0d7de;fill:none}.surface{fill:#fff}
.scan{animation:scan .55s ease-out both;animation-delay:var(--delay,0s)}
.fade{animation:appear .65s ease-out both;animation-delay:var(--delay,0s)}
.draw{animation:draw 1.15s ease-out both;animation-delay:var(--delay,0s)}
.pulse{animation:pulse 2.8s ease-out infinite;transform-box:fill-box;transform-origin:center}
.cursor{opacity:0;animation:cursor .55s linear both;animation-delay:var(--delay,0s)}
@keyframes scan{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
@keyframes appear{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:translateY(0)}}
@keyframes draw{from{stroke-dasharray:var(--length,1000);stroke-dashoffset:var(--length,1000)}to{stroke-dasharray:var(--length,1000);stroke-dashoffset:0}}
@keyframes pulse{0%{opacity:.8;transform:scale(1)}100%{opacity:0;transform:scale(2.8)}}
@keyframes cursor{0%{opacity:.5;transform:translateX(0)}99%{opacity:.5}100%{opacity:0;transform:translateX(var(--travel,0px))}}
@media(prefers-color-scheme:dark){.ink{fill:#f0f6fc}.muted,.data{fill:#8b949e}.rule{stroke:#30363d}.surface{fill:#0d1117}}
@media(prefers-reduced-motion:reduce){.scan,.fade,.draw,.pulse,.cursor{animation:none!important}.pulse,.cursor{opacity:0}}
"""


def _svg(width, height, description, parts):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" fill="none" '
            f'font-family="{FAMILY}" role="img" aria-label="{_safe(description)}">'
            f'<title>{_safe(description)}</title><style>{_font_css()}{CSS}</style>'
            + "".join(parts) + "</svg>")


def _text(x, y, value, size=12, tone="ink", weight=400, anchor="start", spacing=0):
    return (f'<text x="{x:.2f}" y="{y:.2f}" class="{tone}" font-size="{size}" '
            f'font-family="{TEXT_FAMILY}" '
            f'font-weight="{weight}" text-anchor="{anchor}" '
            f'letter-spacing="{spacing}">{_safe(value)}</text>')


def _line(x1, y1, x2, y2, delay=None):
    anim = ""
    if delay is not None:
        length = math.hypot(x2 - x1, y2 - y1) + 1
        anim = f' draw" style="--delay:{delay:.2f}s;--length:{length:.1f}'
    return (f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'class="rule{anim}" stroke-width="1"/>')


def _rect_edge(cx, cy, width, height, toward_x, toward_y):
    """Meet a rectangle's edge along the line toward another center."""
    dx, dy = toward_x - cx, toward_y - cy
    scale = 1 / max(abs(dx) / (width / 2), abs(dy) / (height / 2))
    return cx + dx * scale, cy + dy * scale


def _group(parts, delay=0, animation="fade"):
    return f'<g class="{animation}" style="--delay:{delay:.2f}s">' + "".join(parts) + "</g>"


def _frame(label, figure, width, height):
    return [_text(30, 28, label, 10.5, "muted", spacing=1.6),
            _text(width - 30, 28, figure, 10.5, "muted", anchor="end", spacing=1.6),
            _line(30, 40, width - 30, 40),
            _line(30, height - 24, width - 30, height - 24)]


def heading(label):
    label = {"portrait": "头像", "system info": "系统信息", "ecosystem": "技术生态",
             "timeline": "时间线", "projects": "项目", "snake": "贡献贪吃蛇"}.get(str(label), label)
    title = _short(label, 50)
    start = min(WIDTH - 30, _display_width(title) * 9.6 + 18)
    return _svg(WIDTH, 30, f"章节：{title}",
                [_text(0, 20, title, 16, weight=600), _line(start, 15, WIDTH, 15)])


# A compact 5 x 7 alphabet authored for this profile's block-text greeting.
GLYPHS = {
    "A": [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "B": ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    "C": [" ####", "#    ", "#    ", "#    ", "#    ", "#    ", " ####"],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "F": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    "G": [" ####", "#    ", "#    ", "# ###", "#   #", "#   #", " ####"],
    "H": ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "I": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"],
    "J": ["#####", "    #", "    #", "    #", "#   #", "#   #", " ### "],
    "K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"],
    "N": ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "P": ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    "Q": [" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"],
    "R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    "S": [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "V": ["#   #", "#   #", "#   #", "#   #", " # # ", " # # ", "  #  "],
    "W": ["#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"],
    "X": ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    "Y": ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    "Z": ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    " ": ["     "] * 7,
}


def hero(config):
    name = str(config.get("display_name") or config.get("username") or "corerce")
    letters = "".join(c for c in name.upper() if c in GLYPHS).strip()[:14] or "CORERCE"
    phrase = "HI IM " + letters
    rows = [" ".join(GLYPHS[c][r] for c in phrase) for r in range(7)]
    columns = max(map(len, rows))
    font_size = min(16, 864 / (columns * .6))
    char_w = font_size * .6
    x = (WIDTH - columns * char_w) / 2
    line_h = 19
    parts = [_text(WIDTH / 2, 25, "PERSONAL SYSTEM / INITIALIZED", 10, "muted", anchor="middle", spacing=2)]
    for i, row in enumerate(rows):
        text = (f'<text xml:space="preserve" x="{x:.2f}" y="{52 + i * line_h}" '
                f'class="ink" font-size="{font_size:.2f}" font-weight="600">{_safe(row)}</text>')
        parts.append(_group([text], i * .09, "scan"))
    parts.append(_group([_text(WIDTH / 2, 202, _short(config.get("tagline", "profile initialized"), 95),
                              13, "muted", anchor="middle")], .7))
    parts.append(_group([_text(WIDTH / 2, 226,
                              "github.com/" + _short(config.get("username", "corerce"), 39),
                              11, "muted", anchor="middle", spacing=.4)], .85))
    return _svg(WIDTH, 244, f"你好，我是 {name}", parts)


def _core_lines(columns=64, rows=37):
    """An original diamond lattice with a bright, circular core."""
    ramp = " .:-=+*#%@"
    result = []
    for row in range(rows):
        chars = []
        y = (row - (rows - 1) / 2) * 1.8
        for col in range(columns):
            x = col - (columns - 1) / 2
            diamond = abs(x) + abs(y)
            ring = max(0, 1 - abs(diamond - 25) / 1.5) * .7
            inner = max(0, 1 - abs(diamond - 17) / 1.3) * .45
            circle = math.hypot(x, y)
            core = max(0, 1 - abs(circle - 8) / 2) * .95
            dot = max(0, 1 - circle / 3)
            rays = .2 if (abs(x) < .7 or abs(y) < .7) and 10 < circle < 27 else 0
            level = max(ring, inner, core, dot, rays)
            chars.append(ramp[min(len(ramp) - 1, int(level * (len(ramp) - 1)))])
        result.append("".join(chars).rstrip())
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()
    return result


def _photo_lines(path, root, columns=64):
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("转换配置的头像需要 Pillow：pip install Pillow") from exc
    root = Path(root).resolve()
    path = (root / path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("portrait 必须指向个人主页仓库内的图片")
    if not path.is_file():
        raise FileNotFoundError(f"配置的头像图片不存在：{path}")
    with Image.open(path) as source:
        source = ImageOps.exif_transpose(source).convert("RGBA")
        white = Image.new("RGBA", source.size, "white")
        white.alpha_composite(source)
        gray = ImageOps.autocontrast(white.convert("L"))
        rows = max(1, min(90, round(columns * gray.height / gray.width * .48)))
        gray = gray.resize((columns, rows), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())
    ramp = " .,:;+=*#%@"
    return ["".join(ramp[min(len(ramp) - 1, int((255 - pixels[y * columns + x]) / 255 * (len(ramp) - 1)))]
                    for x in range(columns)).rstrip() for y in range(rows)]


def portrait(config, root=ROOT):
    photo = config.get("portrait")
    if isinstance(photo, dict):
        photo = photo.get("path")
    rows = _photo_lines(photo, root) if photo else _core_lines()
    columns = 64
    font_size, line_h = 12.5, 14.3
    width = 600
    x = (width - columns * font_size * .6) / 2
    height = round(len(rows) * line_h + 62)
    parts = []
    for i, row in enumerate(rows):
        parts.append(_group([f'<text xml:space="preserve" x="{x:.2f}" y="{24 + i * line_h:.2f}" '
                             f'class="data" font-size="{font_size}">{_safe(row)}</text>'], i * .025, "scan"))
    parts.append(_text(width / 2, height - 14, "ASCII / 头像" if photo else "ASCII / 原创核心符号", 9,
                       "muted", anchor="middle", spacing=1.8))
    return _svg(width, height, f"{config.get('display_name', 'corerce')} 的 ASCII 头像" if photo
                else "原创 ASCII 菱形网格与圆形核心", parts)


def _snapshot_number(snapshot, key):
    value = snapshot.get("profile", {}).get(key) if snapshot.get("available") else None
    return f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else "未同步"


def system_info(config, snapshot):
    info = list(config.get("info", []))
    info += [{"label": "公开仓库", "value": _snapshot_number(snapshot, "public_repos")},
             {"label": "关注者", "value": _snapshot_number(snapshot, "followers")},
             {"label": "正在关注", "value": _snapshot_number(snapshot, "following")}]
    rows = []
    for item in info:
        wrapped = _wrap(item.get("value", "待补充"), 58, 3)
        rows.append((_short(item.get("label", "信息"), 18), wrapped))
    height = max(324, 102 + sum(max(1, len(values)) * 20 + 8 for _, values in rows))
    parts = []
    mascot = _core_lines(30, 22)
    for i, row in enumerate(mascot):
        parts.append(_group([f'<text xml:space="preserve" x="24" y="{62 + i * 11.5:.2f}" '
                             f'class="data" font-size="10.2">{_safe(row)}</text>'], .02 * i, "scan"))
    username = _short(config.get("username", "corerce"), 39)
    parts += [_text(286, 36, username + "@github", 14, weight=600), _line(286, 49, WIDTH - 24, 49)]
    y = 75
    for index, (label, values) in enumerate(rows):
        row = [_text(286, y, label, 11.5, weight=600)]
        for j, line in enumerate(values):
            row.append(_text(444, y + j * 20, line, 11.5, "data"))
        parts.append(_group(row, .08 + index * .05))
        y += len(values) * 20 + 8
    sync = snapshot.get("updated_at") if snapshot.get("available") else "未同步"
    parts.append(_text(286, height - 20, "数据更新  " + _short(sync or "未同步", 58), 9, "muted", spacing=.6))
    return _svg(WIDTH, height, f"{username} 的系统信息", parts)


def ecosystem(config):
    nodes = list(config.get("ecosystem", []))[:8]
    height = 584
    parts = _frame("技术生态 / 以核心连接各个方向", "图 01", WIDTH, height)
    if len(nodes) == 6:
        positions = [(230, 124), (710, 124), (150, 290),
                     (790, 290), (230, 458), (710, 458)]
    else:
        positions = [(190, 124), (470, 124), (750, 124),
                     (170, 290), (770, 290),
                     (190, 458), (470, 458), (750, 458)][:len(nodes)]
    hub_x, hub_y = 470, 290
    node_w, node_h = 230, 90
    for index, (x, y) in enumerate(positions):
        start_x, start_y = _rect_edge(hub_x, hub_y, 240, 76, x, y)
        end_x, end_y = _rect_edge(x, y, node_w, node_h, hub_x, hub_y)
        parts.append(_line(start_x, start_y, end_x, end_y, .1 + index * .06))
    parts.append(f'<rect x="350" y="252" width="240" height="76" rx="3" class="rule"/>')
    parts.append(_group([_text(hub_x, 283, _short(config.get("username", "corerce").upper(), 22) + ".SYS",
                              14, weight=600, anchor="middle", spacing=1),
                         _text(hub_x, 306, "个人技术生态", 9.5, "muted", anchor="middle")], .08))
    for index, ((x, y), node) in enumerate(zip(positions, nodes)):
        lines = _wrap(" · ".join(str(item) for item in node.get("items", ["待补充"])), 34, 3)
        body = [f'<rect x="{x - node_w / 2}" y="{y - node_h / 2}" width="{node_w}" height="{node_h}" '
                f'rx="3" class="rule"/>',
                _text(x, y - 19, _short(node.get("label", "待补充"), 24), 12.5, weight=600,
                      anchor="middle", spacing=.4)]
        for j, line in enumerate(lines):
            body.append(_text(x, y + 1 + j * 13, line, 9, "muted", anchor="middle"))
        parts.append(_group(body, .55 + index * .07))
    return _svg(WIDTH, height, "围绕个人核心展开的技术生态", parts)


def timeline(config):
    milestones = list(config.get("timeline", []))[:7]
    if not milestones:
        milestones = [{"date": "NEXT", "title": "你的里程碑", "detail": "待补充"}]
    height, axis = 300, 149
    parts = _frame("成长轨迹", "图 03", WIDTH, height)
    parts.append(_line(68, axis, WIDTH - 68, axis, .1))
    count = len(milestones)
    step = (WIDTH - 136) / max(1, count - 1)
    text_width = min(31, max(19, int(step / 6.5)))
    for i, item in enumerate(milestones):
        x = WIDTH / 2 if count == 1 else 68 + i * step
        # Start/end captions point into the canvas to avoid edge clipping.
        anchor = "start" if i == 0 and count > 1 else "end" if i == count - 1 and count > 1 else "middle"
        tx = x
        up = i % 2 == 0
        tick_end = axis - 25 if up else axis + 25
        date_y = axis - 72 if up else axis + 45
        title_y = date_y + 20
        details = _wrap(item.get("detail", "待补充"), text_width, 2)
        date = str(item.get("date", "NEXT"))
        display_date = {"NOW": "现在", "NEXT": "下一站", "TODAY": "今天"}.get(date.upper(), date)
        body = [_line(x, axis, x, tick_end),
                f'<circle cx="{x:.2f}" cy="{axis}" r="4" class="ink"/>',
                _text(tx, date_y, _short(display_date, 17), 10, "muted", weight=600,
                      anchor=anchor, spacing=.8),
                _text(tx, title_y, _short(item.get("title", "你的里程碑"), text_width),
                      10.5, weight=600, anchor=anchor)]
        for j, line in enumerate(details):
            body.append(_text(tx, title_y + 17 + j * 14, line, 9, "muted", anchor=anchor))
        if date.upper() in {"NOW", "NEXT", "TODAY", "现在", "下一站", "今天"}:
            body.append(f'<circle cx="{x:.2f}" cy="{axis}" r="4" class="rule pulse"/>')
        parts.append(_group(body, .35 + i * .16))
    return _svg(WIDTH, height, "沿水平时间线展开的个人成长里程碑", parts)


def language_stats(snapshot):
    totals = snapshot.get("languages", {}) if snapshot.get("available") else {}
    languages = sorted(((str(name), value) for name, value in totals.items()
                        if isinstance(value, int) and not isinstance(value, bool) and value > 0),
                       key=lambda item: (-item[1], item[0]))
    height = 160 if not languages else 142 + min(7, len(languages)) * 34
    parts = _frame("语言分布 / 公开仓库代码字节数", "图 02", WIDTH, height)
    if not languages:
        parts += [_text(WIDTH / 2, 86, "暂无语言数据", 13, "muted", anchor="middle"),
                  _text(WIDTH / 2, 109, "未同步" if not snapshot.get("available") else "未返回可统计的代码字节数",
                        10, "muted", anchor="middle", spacing=.7)]
    else:
        total = sum(value for _, value in languages)
        for i, (name, value) in enumerate(languages[:7]):
            y, percentage = 73 + i * 34, value / total * 100
            bar_x, bar_w = 216, 442
            row = [_text(30, y + 8, _short(name, 24), 12, weight=600),
                   f'<rect x="{bar_x}" y="{y - 4}" width="{bar_w}" height="13" rx="2" class="rule"/>',
                   _group([f'<rect x="{bar_x + 1}" y="{y - 3}" width="{max(1, (bar_w - 2) * percentage / 100):.2f}" '
                           f'height="11" rx="1" class="data"/>'], .15 + i * .07, "scan"),
                   _text(WIDTH - 28, y + 8, f"{percentage:.1f}%", 12, weight=600, anchor="end"),
                   _text(WIDTH - 107, y + 8, f"{value:,}", 9, "muted", anchor="end")]
            parts.append(_group(row, .15 + i * .07))
        parts.append(_text(30, height - 56, "最多显示 7 种语言；按代码字节数计算，占比不代表熟练度。", 9, "muted"))
        scope = snapshot.get("scope") or "public non-fork non-archived repositories, excluding profile repo"
        if str(scope).casefold() in {"public non-fork non-archived repositories, excluding profile repo",
                                    "public original non-archived repositories, excluding profile repo"}:
            scope = "统计范围：公开、非 Fork、未归档仓库，不含个人主页仓库。"
        parts.append(_text(30, height - 39, _short(scope, 135), 9, "muted"))
    return _svg(WIDTH, height, "公开仓库的编程语言分布，按代码字节数计算", parts)

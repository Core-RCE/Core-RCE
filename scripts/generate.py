"""Generate the profile from explicit content and optional public GitHub data."""

import argparse
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import visuals
from github_data import fetch_snapshot
from contribution_snake import fetch_contributions, load_contributions, render_snake


ROOT = Path(__file__).resolve().parents[1]
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
EMPTY_SNAPSHOT = {
    "available": False,
    "profile": {},
    "repos": [],
    "languages": {},
    "updated_at": None,
}


def plain(value, field, max_length=160):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{field} must be a non-empty string of at most {max_length} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{field} contains a control character")
    return value.strip()


def safe_url(value, field):
    value = plain(value, field, 500)
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "mailto"):
        raise ValueError(f"{field} must use https or mailto")
    if parsed.scheme == "https" and (not parsed.hostname or parsed.username or parsed.password):
        raise ValueError(f"{field} must be an absolute URL without credentials")
    if parsed.scheme == "mailto" and not parsed.path:
        raise ValueError(f"{field} must contain an email address")
    return value


def load_config():
    config = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("profile.json must contain an object")
    username = plain(config.get("username"), "username", 39)
    if not USERNAME_PATTERN.fullmatch(username) or "--" in username:
        raise ValueError("username must be a valid GitHub handle")
    config["username"] = username
    plain(config.get("display_name"), "display_name", 32)
    plain(config.get("tagline"), "tagline", 90)
    for field, limit in (("bio", 3), ("info", 12), ("ecosystem", 8), ("timeline", 7), ("projects", 8), ("links", 5)):
        if not isinstance(config.get(field), list) or len(config[field]) > limit:
            raise ValueError(f"{field} must be a list with at most {limit} entries")
        if field != "bio" and any(not isinstance(entry, dict) for entry in config[field]):
            raise ValueError(f"{field} entries must be objects")
    for index, value in enumerate(config["bio"]):
        plain(value, f"bio[{index}]", 180)
    for index, entry in enumerate(config["info"]):
        plain(entry.get("label"), f"info[{index}].label", 18)
        plain(entry.get("value"), f"info[{index}].value", 90)
    for index, entry in enumerate(config["ecosystem"]):
        plain(entry.get("label"), f"ecosystem[{index}].label", 22)
        if not isinstance(entry.get("items"), list) or not 1 <= len(entry["items"]) <= 6:
            raise ValueError(f"ecosystem[{index}].items must have 1–6 entries")
        for item in entry["items"]:
            plain(item, f"ecosystem[{index}].items", 40)
    for index, entry in enumerate(config["timeline"]):
        for field in ("date", "title", "detail"):
            plain(entry.get(field), f"timeline[{index}].{field}", 48)
    for field in ("projects", "links"):
        for index, entry in enumerate(config[field]):
            plain(entry.get("name" if field == "projects" else "label"), f"{field}[{index}].label", 80)
            safe_url(entry.get("url"), f"{field}[{index}].url")
            if field == "projects":
                plain(entry.get("description"), f"{field}[{index}].description", 240)
                if entry.get("language") is not None:
                    plain(entry["language"], f"{field}[{index}].language", 40)
    if config.get("portrait") is not None:
        plain(config["portrait"], "portrait", 200)
    return config


def load_snapshot(config):
    path = ROOT / "data" / "github.json"
    if not path.exists():
        return dict(EMPTY_SNAPSHOT)
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        raise ValueError("data/github.json must contain an object")
    if snapshot.get("username", "").lower() != config["username"].lower():
        print("Stored GitHub data belongs to another account; using NOT SYNCED state.")
        return dict(EMPTY_SNAPSHOT)
    return snapshot


def write_text(path, text):
    """Replace only a fully produced file, preserving existing output on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def escape(value):
    return html.escape(str(value), quote=True)


def projects_markup(config, snapshot):
    projects = config["projects"]
    if not projects and snapshot.get("available"):
        projects = [
            {"name": repo["name"], "url": repo["html_url"], "description": repo.get("description") or "暂无项目说明。", "language": repo.get("language")}
            for repo in snapshot.get("repos", [])[:6]
        ]
    if not projects:
        return '<p><code>$ ls ~/projects</code><br/>代表项目待填写。</p>'
    rows = ['<table>']
    for index in range(0, len(projects), 2):
        rows.append('<tr>')
        for project in projects[index:index + 2]:
            url = safe_url(project["url"], "project url")
            language = f'<p><code>{escape(project["language"])}</code></p>' if project.get("language") else ''
            rows.append(f'<td width="50%" valign="top"><h3><a href="{escape(url)}">{escape(project["name"])}</a></h3><p>{escape(project["description"])}</p>{language}</td>')
        if len(projects[index:index + 2]) == 1:
            rows.append('<td width="50%"></td>')
        rows.append('</tr>')
    rows.append('</table>')
    return '\n'.join(rows)


def readme_markup(config, snapshot):
    links = ' &nbsp;·&nbsp; '.join(
        f'<a href="{escape(safe_url(link["url"], "link url"))}"><code>{escape(link["label"])}</code></a>'
        for link in config["links"]
    )
    bio = '\n'.join('> ' + escape(line) + '<br/>' for line in config["bio"])
    if not bio:
        bio = '> 个人简介与研究方向待填写。'
    return f'''<!-- Generated by scripts/generate.py. Edit profile.json, then regenerate. -->
<div align="center">
  <img src="./hello.svg" width="600" alt="{escape(config['display_name'])} 终端欢迎图"/>
  <br/>
  {links}
</div>

<img src="./hd-portrait.svg" width="940" alt="头像"/>
<div align="center">
  <img src="./ascii.svg" width="400" alt="{escape(config['display_name'])} ASCII 头像"/>
</div>

{bio}

<img src="./hd-system-info.svg" width="940" alt="系统信息"/>
<img src="./neofetch.svg" width="940" alt="{escape(config['username'])} 的系统信息"/>

<img src="./hd-ecosystem.svg" width="940" alt="技术生态"/>
<img src="./system-map.svg" width="940" alt="个人技术生态，未提供的信息标记为待补充"/>

<img src="./hd-timeline.svg" width="940" alt="时间线"/>
<img src="./timeline.svg" width="940" alt="GitHub 账号与公开仓库的时间线"/>

<img src="./hd-projects.svg" width="940" alt="项目"/>
<img src="./lang-stats.svg" width="940" alt="公开仓库的代码语言分布，按代码字节数统计"/>

{projects_markup(config, snapshot)}

<img src="./hd-snake.svg" width="940" alt="贡献贪吃蛇"/>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./snake-dark.svg"/>
  <source media="(prefers-color-scheme: light)" srcset="./snake.svg"/>
  <img src="./snake.svg" width="940" alt="{escape(config['username'])} 的 GitHub 贡献贪吃蛇动画"/>
</picture>

<details>
<summary>设计来源</summary>

终端视觉与章节结构参考 <a href="https://github.com/moiz-codez/moiz-codez">moiz-codez/moiz-codez</a>，SVG 和生成脚本独立实现。字体为 <a href="https://github.com/JetBrains/JetBrainsMono">JetBrains Mono</a>，按 SIL OFL 1.1 使用。

</details>
'''


def make_preview(readme):
    # README content is controlled HTML; SVGs retain their own image context.
    readme = re.sub(r'^> (.*)$', r'<blockquote>\1</blockquote>', readme, flags=re.MULTILINE)
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CoreRCE · 个人主页预览</title>
<style>
:root{color-scheme:light dark;--bg:light-dark(#fff,#0d1117);--ink:light-dark(#24292f,#f0f6fc);--muted:light-dark(#57606a,#8b949e);--line:light-dark(#d0d7de,#30363d)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:980px;margin:48px auto;padding:0 24px}img{max-width:100%;height:auto;display:block;margin:20px 0}[align=center] img{margin:20px auto}
a{color:inherit;text-underline-offset:4px}code{font-family:Consolas,monospace}blockquote{margin:24px 0;padding-left:16px;border-left:3px solid var(--line);color:var(--muted)}
table{border-collapse:collapse;width:100%;table-layout:fixed}td{border:1px solid var(--line);padding:20px;overflow-wrap:anywhere}h3{font-size:16px;margin:0 0 8px}p{margin:12px 0}details{margin-top:40px;color:var(--muted)}summary{cursor:pointer}
@media(max-width:600px){main{margin:24px auto;padding:0 16px}td{padding:12px}h3{font-size:14px}}
</style></head><body><main>''' + readme + '</main></body></html>\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="fetch this account's public GitHub data")
    parser.add_argument("--preview", action="store_true", help="write ignored preview.html for local review")
    args = parser.parse_args()
    config = load_config()
    snapshot = dict(EMPTY_SNAPSHOT) if args.sync else load_snapshot(config)
    if args.sync:
        snapshot = fetch_snapshot(config["username"], token=os.environ.get("GITHUB_TOKEN"))
        snapshot["username"] = config["username"]
        contributions = fetch_contributions(config["username"])
    else:
        contributions = load_contributions(ROOT / "data" / "contributions.json", config["username"])
    if contributions is None:
        raise RuntimeError("贡献图尚未同步，请使用 --sync 获取当前账号的公开贡献日历。")
    assets = {
        "hello.svg": visuals.hero(config),
        "ascii.svg": visuals.portrait(config, ROOT),
        "neofetch.svg": visuals.system_info(config, snapshot),
        "system-map.svg": visuals.ecosystem(config),
        "timeline.svg": visuals.timeline(config),
        "lang-stats.svg": visuals.language_stats(snapshot),
        "snake.svg": render_snake(contributions, theme="light"),
        "snake-dark.svg": render_snake(contributions, theme="dark"),
    }
    for section in ("portrait", "system info", "ecosystem", "timeline", "projects", "snake"):
        assets['hd-' + section.replace(' ', '-') + '.svg'] = visuals.heading(section)
    for filename, content in assets.items():
        ET.fromstring(content)
    readme = readme_markup(config, snapshot)
    # Every output is produced and validated before any existing output is replaced.
    for filename, content in assets.items():
        write_text(ROOT / filename, content)
    write_text(ROOT / "README.md", readme)
    if args.sync:
        write_text(ROOT / "data" / "github.json", json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
        write_text(ROOT / "data" / "contributions.json", json.dumps(contributions, ensure_ascii=False, indent=2) + '\n')
    if args.preview:
        write_text(ROOT / "preview.html", make_preview(readme))
    print(f"Generated {len(assets)} SVGs and README.md for {config['username']}.")
    if not snapshot.get("available"):
        print("GitHub data: NOT SYNCED. Run with --sync to fetch public statistics.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, ET.ParseError) as error:
        print(f"Generation failed: {error}", file=sys.stderr)
        sys.exit(1)

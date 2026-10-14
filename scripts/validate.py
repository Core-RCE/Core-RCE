"""Validate generated SVGs, README references, and identity isolation."""

from pathlib import Path
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SVG = '{http://www.w3.org/2000/svg}'
EXPECTED = {
    'hello.svg', 'ascii.svg', 'neofetch.svg', 'system-map.svg', 'timeline.svg',
    'lang-stats.svg', 'hd-portrait.svg', 'hd-system-info.svg',
    'hd-ecosystem.svg', 'hd-timeline.svg', 'hd-projects.svg',
    'hd-snake.svg', 'snake.svg', 'snake-dark.svg',
}


def main():
    found = {path.name for path in ROOT.glob('*.svg')}
    if found != EXPECTED:
        raise ValueError(f'SVG manifest mismatch: missing={EXPECTED-found}, unexpected={found-EXPECTED}')
    for filename in sorted(EXPECTED):
        content = (ROOT / filename).read_text(encoding='utf-8')
        root = ET.fromstring(content)
        if root.tag != SVG + 'svg' or not root.get('viewBox'):
            raise ValueError(f'{filename}: invalid SVG root or viewBox')
        for node in root.iter():
            if node.tag in (SVG + 'script', SVG + 'foreignObject'):
                raise ValueError(f'{filename}: prohibited executable or HTML SVG content')
            for key, value in node.attrib.items():
                if key.lower().startswith('on'):
                    raise ValueError(f'{filename}: event handler found')
                if key.endswith('href') and not (value.startswith('#') or value.startswith('data:')):
                    raise ValueError(f'{filename}: external SVG resource found')
        if re.search(r'url\(\s*[\"\']?https?://', content):
            raise ValueError(f'{filename}: external stylesheet resource')
        if 'moiz.codez@gmail.com' in content or 'Muhammad Moiz' in content or 'Mehran University' in content:
            raise ValueError(f'{filename}: original identity remains')
        if 'prefers-reduced-motion' not in content:
            raise ValueError(f'{filename}: reduced motion support missing')

    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    referenced = set()
    for attribute, value in re.findall(r'\b(src|srcset|href)="([^"]+)"', readme):
        if value.startswith('./'):
            target = (ROOT / value).resolve()
            if not target.is_relative_to(ROOT.resolve()) or not target.is_file():
                raise ValueError(f'Missing or escaping README resource: {value}')
            if attribute in ('src', 'srcset'):
                referenced.add(target.name)
        elif urlsplit(value).scheme not in ('https', 'mailto'):
            raise ValueError(f'Unsafe README link: {value}')
    if referenced != EXPECTED:
        raise ValueError(f'README omits generated assets: {EXPECTED-referenced}')
    print(f'Validated {len(EXPECTED)} SVGs, local README references, and identity replacement.')


if __name__ == '__main__':
    main()

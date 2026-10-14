"""Network-free contribution parsing, cache, route, and SVG checks."""

from datetime import date, timedelta
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

from scripts import contribution_snake as snake


def days_fixture():
    start = date(2025, 10, 12)
    return [{"date": (start + timedelta(days=index)).isoformat(),
             "level": index % 5, "count": index % 5 if index % 3 else None}
            for index in range(368)]


def snapshot_fixture():
    return {"username": "CoreRCE", "source": "https://github.com/users/CoreRCE/contributions",
            "updated_at": "2026-10-14T08:00:00Z", "days": days_fixture()}


def html_fixture():
    # The public page uses data-date/level on td and separate linked tooltips.
    entries = []
    for index, item in enumerate(reversed(days_fixture())):
        tag = "rect" if index == 4 else "td"
        entries.append(f'<{tag} id="day-{index}" data-level="{item["level"]}" data-date="{item["date"]}"></{tag}>')
        if index == 0:
            text = 'No contributions on October 14th.'
        elif index == 1:
            text = '<span>1,234 contributions</span> on October 13th.'
        elif index == 2:
            continue
        else:
            text = f'{item["level"]} contributions on a day.'
        entries.append(f'<tool-tip for="day-{index}">{text}</tool-tip>')
    return '<table><tbody>' + ''.join(entries) + '</tbody></table><script>ignored()</script>'


class ContributionSnakeTests(unittest.TestCase):
    def test_public_markup_extracts_sorted_real_dates_levels_and_optional_counts(self):
        days = snake._parse_html(html_fixture())
        self.assertEqual(len(days), 368)
        self.assertEqual(days[0]["date"], "2025-10-12")
        self.assertEqual(days[-1]["date"], "2026-10-14")
        self.assertEqual(days[-1]["count"], 0)
        self.assertEqual(days[-2]["count"], 1234)
        self.assertIsNone(days[-3]["count"])
        self.assertEqual(days[-1]["level"], days_fixture()[-1]["level"])

    def test_parser_rejects_partial_duplicate_dates_and_bad_attributes(self):
        valid = html_fixture()
        examples = [
            '<td data-date="2026-10-14" data-level="1"></td>',
            valid + '<td data-date="2025-10-12" data-level="1"></td>',
            valid.replace('data-level="2"', 'data-level="5"', 1),
            valid.replace('2026-10-14', '2026-02-30', 1),
            valid.replace('data-level="2"', 'data-level="-1"', 1),
        ]
        for content in examples:
            with self.subTest(content=content[-90:]), self.assertRaises(ValueError):
                snake._parse_html(content)

    def test_fetch_uses_fixed_public_url_and_no_authentication(self):
        with patch.object(snake, 'urlopen', return_value=io.BytesIO(html_fixture().encode())) as open_mock:
            snapshot = snake.fetch_contributions('CoreRCE')
        request = open_mock.call_args.args[0]
        self.assertEqual(request.full_url, 'https://github.com/users/CoreRCE/contributions')
        self.assertEqual(request.get_header('Accept-language'), 'en-US')
        self.assertIsNone(request.get_header('Authorization'))
        self.assertEqual(open_mock.call_args.kwargs['timeout'], 15)
        self.assertEqual(snapshot['source'], request.full_url)
        self.assertTrue(snapshot['updated_at'].endswith('Z'))
        with patch.object(snake, 'urlopen') as open_mock:
            for username in ('../other', 'https://example.com', '-bad', 'a--b', 'a' * 40):
                with self.subTest(username=username), self.assertRaises(ValueError):
                    snake.fetch_contributions(username)
            open_mock.assert_not_called()

    def test_network_and_http_retries_are_bounded(self):
        for status in (429, 503):
            failures = [HTTPError('https://github.com', status, 'temporary', {}, io.BytesIO()) for _ in range(2)]
            with self.subTest(status=status), patch.object(snake, 'urlopen', side_effect=failures + [io.BytesIO(html_fixture().encode())]) as opened:
                with patch.object(snake.time, 'sleep') as sleeping:
                    self.assertEqual(len(snake.fetch_contributions('CoreRCE')['days']), 368)
                self.assertEqual(opened.call_count, 3)
                self.assertEqual([call.args[0] for call in sleeping.call_args_list], [1, 2])
        for failure in (URLError('offline'), TimeoutError('timeout')):
            with self.subTest(error=type(failure).__name__), patch.object(snake, 'urlopen', side_effect=failure) as opened:
                with patch.object(snake.time, 'sleep'), self.assertRaises(RuntimeError):
                    snake.fetch_contributions('CoreRCE')
                self.assertEqual(opened.call_count, 3)
        failure = HTTPError('https://github.com', 404, 'missing', {}, io.BytesIO())
        with patch.object(snake, 'urlopen', side_effect=failure) as opened, self.assertRaisesRegex(RuntimeError, 'HTTP 404'):
            snake.fetch_contributions('CoreRCE')
        self.assertEqual(opened.call_count, 1)

    def test_invalid_network_calendar_is_not_reported_as_empty_success(self):
        for body in (b'<h1>Sign in</h1>', b'\xff'):
            with patch.object(snake, 'urlopen', return_value=io.BytesIO(body)), self.assertRaisesRegex(RuntimeError, 'Invalid public GitHub'):
                snake.fetch_contributions('CoreRCE')

    def test_cache_absence_mismatch_corruption_and_validation(self):
        path = Path('contributions.json')
        with patch.object(Path, 'exists', return_value=False):
            self.assertIsNone(snake.load_contributions(path, 'CoreRCE'))
        with patch.object(Path, 'exists', return_value=True), patch.object(Path, 'read_text', return_value=json.dumps(snapshot_fixture())):
            self.assertIsNone(snake.load_contributions(path, 'other-account'))
            self.assertEqual(len(snake.load_contributions(path, 'corerce')['days']), 368)
        with patch.object(Path, 'exists', return_value=True), patch.object(Path, 'read_text', return_value='{broken'):
            with self.assertRaisesRegex(ValueError, 'JSON'):
                snake.load_contributions(path, 'CoreRCE')
        invalid = snapshot_fixture()
        invalid['days'][0]['level'] = True
        with patch.object(Path, 'exists', return_value=True), patch.object(Path, 'read_text', return_value=json.dumps(invalid)):
            with self.assertRaisesRegex(ValueError, 'level'):
                snake.load_contributions(path, 'CoreRCE')

    def test_route_is_closed_adjacent_and_has_no_self_intersections(self):
        cells, columns = snake._calendar_cells(days_fixture())
        self.assertEqual(columns, 53)
        self.assertEqual(cells[0][:2], (0, 0))
        route = snake._route(columns)
        self.assertEqual(route[0], route[-1])
        self.assertEqual(len(set(route[:-1])), len(route) - 1)
        for previous, current in zip(route, route[1:]):
            self.assertEqual(abs(current[0] - previous[0]) + abs(current[1] - previous[1]), 1)
        self.assertTrue(all((x, y) in route for x, y, _ in cells))
        for index in range(len(route) - 1):
            body = [route[(index - offset) % (len(route) - 1)] for offset in range(6)]
            self.assertEqual(len(set(body)), 6)

    def test_svg_is_standalone_truthful_and_supports_reduced_motion(self):
        for theme in ('light', 'dark'):
            output = snake.render_snake(snapshot_fixture(), theme)
            root = ET.fromstring(output)
            ns = {'s': 'http://www.w3.org/2000/svg'}
            self.assertEqual(root.attrib['viewBox'], '0 0 940 210')
            days = [node for node in root.findall('s:rect', ns) if node.get('class') == 'day']
            segments = [node for node in root.findall('s:rect', ns) if 'snake' in node.get('class', '')]
            self.assertEqual(len(days), 368)
            self.assertEqual(len(segments), 6)
            self.assertTrue(all(node.get('fill') for node in days))
            self.assertIn('次数未提供', output)
            self.assertIn('https://github.com/users/CoreRCE/contributions', output)
            self.assertIn('2025-10-12', output)
            self.assertIn('@keyframes travel', output)
            self.assertIn('28s linear infinite', output)
            self.assertIn('prefers-reduced-motion:reduce', output)
            self.assertIn('*{animation:none!important}', output)
            self.assertIn('.snake{display:none}', output)
            self.assertNotIn('<script', output)
            self.assertNotIn('foreignObject', output)
            self.assertNotIn('@font-face', output)
            self.assertNotIn('href=', output)
        with self.assertRaises(ValueError):
            snake.render_snake(snapshot_fixture(), 'unknown')

    def test_render_rejects_untrusted_or_incomplete_snapshot(self):
        for field, value in (('source', 'https://example.com'), ('updated_at', 'not-a-date'), ('days', [])):
            invalid = snapshot_fixture()
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                snake.render_snake(invalid)
        invalid = snapshot_fixture()
        invalid['days'] = invalid['days'][:10] + invalid['days'][11:]
        with self.assertRaisesRegex(ValueError, 'missing dates'):
            snake.render_snake(invalid)


if __name__ == '__main__':
    unittest.main()

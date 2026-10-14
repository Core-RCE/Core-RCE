"""Validate content boundaries and failures that must not overwrite the profile."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate


class GenerateTests(unittest.TestCase):
    def test_link_schemes_and_credentials_are_rejected(self):
        for url in ('javascript:alert(1)', 'http://example.com', 'https://user:pass@example.com', 'https:///missing-host'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                generate.safe_url(url, 'link')
        self.assertEqual(generate.safe_url('https://github.com/corerce', 'link'), 'https://github.com/corerce')

    def test_project_fields_cannot_inject_html(self):
        config = {'projects': [{
            'name': '<script>alert(1)</script>',
            'description': '<img src=x onerror=alert(1)>',
            'url': 'https://github.com/corerce/test',
        }]}
        output = generate.projects_markup(config, generate.EMPTY_SNAPSHOT)
        self.assertNotIn('<script>', output)
        self.assertNotIn('<img src=x', output)
        self.assertIn('&lt;script&gt;', output)

    def test_account_change_does_not_reuse_old_statistics(self):
        with tempfile.TemporaryDirectory(dir=generate.ROOT) as temp:
            root = Path(temp)
            (root / 'data').mkdir()
            (root / 'data/github.json').write_text(json.dumps({'username': 'someone-else', 'available': True}), encoding='utf-8')
            with patch.object(generate, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                snapshot = generate.load_snapshot({'username': 'corerce'})
            self.assertFalse(snapshot['available'])
            self.assertEqual(snapshot['languages'], {})

    def test_sync_failure_preserves_existing_profile_and_data(self):
        with tempfile.TemporaryDirectory(dir=generate.ROOT) as temp:
            root = Path(temp)
            (root / 'README.md').write_text('existing profile', encoding='utf-8')
            with patch.object(generate, 'ROOT', root), \
                 patch.object(generate, 'load_config', return_value={'username': 'corerce'}), \
                 patch.object(generate, 'fetch_snapshot', side_effect=RuntimeError('API unavailable')), \
                 patch.object(sys, 'argv', ['generate.py', '--sync']):
                with self.assertRaisesRegex(RuntimeError, 'API unavailable'):
                    generate.main()
            self.assertEqual((root / 'README.md').read_text(encoding='utf-8'), 'existing profile')
            self.assertFalse((root / 'data/github.json').exists())

    def test_sync_bypasses_broken_cached_data(self):
        with patch.object(generate, 'load_config', return_value={'username': 'corerce'}), \
             patch.object(generate, 'load_snapshot', side_effect=ValueError('broken cache')) as cache, \
             patch.object(generate, 'fetch_snapshot', side_effect=RuntimeError('network invoked')) as fetch, \
             patch.object(sys, 'argv', ['generate.py', '--sync']):
            with self.assertRaisesRegex(RuntimeError, 'network invoked'):
                generate.main()
            cache.assert_not_called()
            fetch.assert_called_once()

    def test_contribution_sync_failure_preserves_existing_profile(self):
        with tempfile.TemporaryDirectory(dir=generate.ROOT) as temp:
            root = Path(temp)
            (root / 'README.md').write_text('existing profile', encoding='utf-8')
            (root / 'snake.svg').write_text('existing animation', encoding='utf-8')
            with patch.object(generate, 'ROOT', root), \
                 patch.object(generate, 'load_config', return_value={'username': 'CoreRCE'}), \
                 patch.object(generate, 'fetch_snapshot', return_value={'available': True}), \
                 patch.object(generate, 'fetch_contributions', side_effect=RuntimeError('calendar unavailable')), \
                 patch.object(sys, 'argv', ['generate.py', '--sync']):
                with self.assertRaisesRegex(RuntimeError, 'calendar unavailable'):
                    generate.main()
            self.assertEqual((root / 'README.md').read_text(encoding='utf-8'), 'existing profile')
            self.assertEqual((root / 'snake.svg').read_text(encoding='utf-8'), 'existing animation')
            self.assertFalse((root / 'data/github.json').exists())

    def test_readme_uses_both_local_snake_themes(self):
        config = generate.load_config()
        readme = generate.readme_markup(config, generate.EMPTY_SNAPSHOT)
        self.assertIn('alt="贡献贪吃蛇"', readme)
        self.assertIn('<source media="(prefers-color-scheme: dark)" srcset="./snake-dark.svg"/>', readme)
        self.assertIn('<source media="(prefers-color-scheme: light)" srcset="./snake.svg"/>', readme)
        self.assertIn('<img src="./snake.svg" width="940"', readme)

    def test_validated_username_is_normalized_before_use(self):
        config = json.loads((generate.ROOT / 'profile.json').read_text(encoding='utf-8'))
        config['username'] = ' corerce '
        with tempfile.TemporaryDirectory(dir=generate.ROOT) as temp:
            root = Path(temp)
            (root / 'profile.json').write_text(json.dumps(config), encoding='utf-8')
            with patch.object(generate, 'ROOT', root):
                self.assertEqual(generate.load_config()['username'], 'corerce')


if __name__ == '__main__':
    unittest.main()

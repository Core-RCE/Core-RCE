"""Network-free tests of public GitHub snapshot fetching."""

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from scripts import github_data


def response(value):
    return io.BytesIO(json.dumps(value).encode("utf-8"))


def repo(name, *, stars=0, updated="2026-10-13T00:00:00Z", fork=False, archived=False):
    return {
        "name": name,
        "description": f"Description for {name}",
        "html_url": f"https://github.com/Corerce/{name}",
        "language": "Python",
        "stargazers_count": stars,
        "updated_at": updated,
        "archived": archived,
        "fork": fork,
        "languages_url": "https://untrusted.example/should-never-be-fetched",
    }


USER = {
    "login": "Corerce",
    "name": "Corerce",
    "bio": None,
    "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
    "public_repos": 104,
    "followers": 7,
    "following": 3,
    "created_at": "2020-01-01T00:00:00Z",
    "blog": "",
    "html_url": "https://github.com/Corerce",
}


class FetchSnapshotTests(unittest.TestCase):
    def test_pagination_filters_sorting_and_language_totals(self):
        first = [repo(f"project-{index}") for index in range(97)]
        first.extend([repo("forked", fork=True), repo("old", archived=True), repo("cOrErCe")])
        second = [
            repo("second-page", stars=4, updated="2026-10-12T00:00:00Z"),
            repo("recent-star", stars=4),
            repo("low-stars", stars=1),
            repo("second-fork", fork=True),
        ]
        calls = []

        def open_mock(request, *, timeout):
            self.assertEqual(timeout, 15)
            parsed = urlparse(request.full_url)
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.netloc, "api.github.com")
            calls.append(request.full_url)
            if parsed.path == "/users/Corerce":
                return response(USER)
            if parsed.path == "/users/Corerce/repos":
                query = parse_qs(parsed.query)
                self.assertEqual(query["per_page"], ["100"])
                self.assertEqual(query["type"], ["owner"])
                return response(first if query["page"] == ["1"] else second)
            self.assertTrue(parsed.path.startswith("/repos/Corerce/"))
            self.assertTrue(parsed.path.endswith("/languages"))
            if parsed.path == "/repos/Corerce/recent-star/languages":
                return response({"Python": 25, "TypeScript": 10})
            if parsed.path == "/repos/Corerce/second-page/languages":
                return response({"Python": 75})
            return response({})

        with patch.object(github_data, "urlopen", side_effect=open_mock):
            snapshot = github_data.fetch_snapshot("Corerce")

        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["profile"]["followers"], 7)
        self.assertIsNone(snapshot["profile"]["bio"])
        self.assertEqual(snapshot["profile"]["public_repos"], 104)
        self.assertEqual(len(snapshot["repos"]), 100)
        self.assertEqual([item["name"] for item in snapshot["repos"][:3]],
                         ["recent-star", "second-page", "low-stars"])
        self.assertEqual(snapshot["languages"], {"Python": 100, "TypeScript": 10})
        self.assertEqual(len(calls), 103)
        self.assertNotIn("forked", " ".join(calls))
        self.assertNotIn("untrusted.example", " ".join(calls))
        self.assertTrue(snapshot["updated_at"].endswith("Z"))
        self.assertEqual(snapshot["scope"], github_data.SCOPE)

    def test_empty_repositories_and_empty_languages_are_successful(self):
        for repositories in ([], [repo("empty-project")]):
            with self.subTest(repositories=repositories):
                replies = [response(USER), response(repositories)]
                if repositories:
                    replies.append(response({}))
                with patch.object(github_data, "urlopen", side_effect=replies):
                    snapshot = github_data.fetch_snapshot("Corerce")
                self.assertTrue(snapshot["available"])
                self.assertEqual(snapshot["languages"], {})

    def test_invalid_handles_fail_before_network_access(self):
        invalid = ["", "-abc", "abc-", "a--b", "a/b", "a?b", "名字", "a" * 40, None]
        with patch.object(github_data, "urlopen") as open_mock:
            for username in invalid:
                with self.subTest(username=username), self.assertRaises(ValueError):
                    github_data.fetch_snapshot(username)
            open_mock.assert_not_called()

    def test_headers_token_and_locally_encoded_repository_path(self):
        for token in (None, "secret-token"):
            with self.subTest(token_supplied=bool(token)):
                with patch.object(github_data, "urlopen", side_effect=[
                    response(USER), response([repo("unexpected/name?#")]), response({})
                ]) as open_mock:
                    github_data.fetch_snapshot("Corerce", token=token)
                first = open_mock.call_args_list[0].args[0]
                self.assertEqual(first.get_header("User-agent"), "corerce-profile-readme")
                self.assertEqual(first.get_header("Accept"), "application/vnd.github+json")
                self.assertEqual(first.get_header("Authorization"),
                                 "Bearer secret-token" if token else None)
                language_request = open_mock.call_args_list[-1].args[0]
                self.assertEqual(language_request.full_url,
                                 "https://api.github.com/repos/Corerce/unexpected%2Fname%3F%23/languages")

    def test_unauthorized_and_missing_user_fail_without_retries(self):
        for status in (401, 404):
            with self.subTest(status=status):
                failure = HTTPError("https://api.github.com/users/Corerce", status,
                                    "potentially sensitive error", {}, io.BytesIO())
                with patch.object(github_data, "urlopen", side_effect=failure) as open_mock:
                    with patch.object(github_data.time, "sleep") as sleep_mock:
                        with self.assertRaisesRegex(RuntimeError, f"HTTP {status}") as error:
                            github_data.fetch_snapshot("Corerce", token="secret-token")
                self.assertEqual(open_mock.call_count, 1)
                sleep_mock.assert_not_called()
                self.assertNotIn("secret-token", str(error.exception))

    def test_temporary_http_failures_are_retried_twice(self):
        for status in (429, 500, 503):
            with self.subTest(status=status):
                failures = [HTTPError("https://api.github.com/users/Corerce", status,
                                      "temporary", {}, io.BytesIO()) for _ in range(2)]
                with patch.object(github_data, "urlopen", side_effect=failures + [response(USER), response([])]) as open_mock:
                    with patch.object(github_data.time, "sleep") as sleep_mock:
                        snapshot = github_data.fetch_snapshot("Corerce")
                self.assertTrue(snapshot["available"])
                self.assertEqual(open_mock.call_count, 4)
                self.assertEqual([call.args[0] for call in sleep_mock.call_args_list], [1, 2])

    def test_retry_exhaustion_and_network_failure_are_not_empty_success(self):
        failures = [
            HTTPError("https://api.github.com/users/Corerce", 503, "temporary", {}, io.BytesIO()),
            URLError("network disconnected"),
            TimeoutError("timeout"),
        ]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                with patch.object(github_data, "urlopen", side_effect=failure) as open_mock:
                    with patch.object(github_data.time, "sleep"):
                        with self.assertRaises(RuntimeError):
                            github_data.fetch_snapshot("Corerce")
                self.assertEqual(open_mock.call_count, 3)

    def test_language_failure_is_propagated(self):
        failure = HTTPError("https://api.github.com/repos/Corerce/project/languages", 403,
                            "limited", {}, io.BytesIO())
        with patch.object(github_data, "urlopen", side_effect=[response(USER), response([repo("project")]), failure]):
            with self.assertRaisesRegex(RuntimeError, "/repos/Corerce/project/languages: HTTP 403"):
                github_data.fetch_snapshot("Corerce")

    def test_malformed_api_payloads_fail(self):
        payloads = [
            [io.BytesIO(b"invalid JSON")],
            [response([])],
            [response({"login": "-invalid"})],
            [response(USER), response({"message": "error"})],
            [response(USER), response([{"name": "missing-required-data"}])],
            [response(USER), response([repo("project")]), response({"Python": -1})],
            [response(USER), response([repo("project")]), response({"Python": True})],
            [response(USER), response([repo("project")]), response([])],
        ]
        for replies in payloads:
            with self.subTest(case=len(replies)):
                with patch.object(github_data, "urlopen", side_effect=replies):
                    with self.assertRaises(RuntimeError):
                        github_data.fetch_snapshot("Corerce")


if __name__ == "__main__":
    unittest.main()

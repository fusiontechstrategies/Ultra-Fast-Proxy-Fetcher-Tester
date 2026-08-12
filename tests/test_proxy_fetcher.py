from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import aiohttp

import proxy_fetcher_ultimate as app


class FakeResponseContext:
    def __init__(self, status: int) -> None:
        self.response = type("FakeResponse", (), {"status": status})()

    async def __aenter__(self) -> Any:
        return self.response

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    def __init__(self, status: int) -> None:
        self.status = status
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponseContext:
        self.calls.append((url, kwargs))
        return FakeResponseContext(self.status)


class FakeContent:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def iter_chunked(self, _size: int) -> Any:
        for chunk in self.chunks:
            yield chunk


class FakeLimitedResponse:
    def __init__(self, chunks: list[bytes], content_length: int | None = None) -> None:
        self.content = FakeContent(chunks)
        self.content_length = content_length


class ProxyParsingTests(unittest.TestCase):
    def test_public_ipv4_policy_rejects_non_public_addresses(self) -> None:
        self.assertTrue(app.is_public_ipv4("8.8.8." + "8"))
        for address in (
            "10.0.0.1",
            "127.0.0.1",
            "169.254.1.1",
            "192.0.2.1",
            "224.0.0.1",
            "999.1.1.1",
            "::1",
        ):
            with self.subTest(address=address):
                self.assertFalse(app.is_public_ipv4(address))

    def test_parser_validates_ports_and_deduplicates(self) -> None:
        text = "\n".join(
            (
                "203.0.113.10:8080",
                "203.0.113.10:8080",
                "203.0.113.11:65535",
                "203.0.113.12:0",
                "999.0.0.1:443",
            )
        )
        targets, rejected = app.parse_proxy_text(
            text,
            "http",
            address_validator=lambda host: host.startswith("203.0.113."),
        )
        self.assertEqual(
            targets,
            (
                app.ProxyTarget("203.0.113.10", 8080, "http"),
                app.ProxyTarget("203.0.113.11", 65535, "http"),
            ),
        )
        self.assertEqual(rejected, 2)

    def test_parser_enforces_per_source_limit(self) -> None:
        targets, rejected = app.parse_proxy_text(
            "203.0.113.1:80\n203.0.113.2:80\n203.0.113.3:80",
            "http",
            address_validator=lambda _host: True,
            max_targets=2,
        )
        self.assertEqual(len(targets), 2)
        self.assertEqual(rejected, 0)

    def test_production_parser_blocks_internal_targets(self) -> None:
        targets, rejected = app.parse_proxy_text(
            "10.0.0.10:8080\n127.0.0.1:3128\n192.0.2.9:9000",
            "http",
        )
        self.assertEqual(targets, ())
        self.assertEqual(rejected, 3)

    def test_source_url_policy_requires_safe_https(self) -> None:
        self.assertTrue(app.is_safe_source_url("https://example.com/list.txt"))
        for url in (
            "http://example.com/list.txt",
            "https://user:password@example.com/list.txt",
            "https://localhost/list.txt",
            "https://127.0.0.1/list.txt",
            "https://service.local/list.txt",
        ):
            with self.subTest(url=url):
                self.assertFalse(app.is_safe_source_url(url))

    def test_sources_are_unique_https_entries(self) -> None:
        self.assertEqual(len(app.PROXY_SOURCES), 52)
        self.assertEqual(len({source.url for source in app.PROXY_SOURCES}), 52)
        self.assertTrue(all(app.is_safe_source_url(source.url) for source in app.PROXY_SOURCES))

    def test_merge_is_fair_deduplicated_and_capped(self) -> None:
        one = app.SourceFetchResult(
            app.SourceSpec("https://one.example/list", "http"),
            (
                app.ProxyTarget("203.0.113.1", 80, "http"),
                app.ProxyTarget("203.0.113.2", 80, "http"),
            ),
        )
        two = app.SourceFetchResult(
            app.SourceSpec("https://two.example/list", "http"),
            (
                app.ProxyTarget("203.0.113.3", 80, "http"),
                app.ProxyTarget("203.0.113.1", 80, "http"),
            ),
        )
        selected, total = app.merge_proxy_targets(
            (one, two),
            protocol="all",
            max_candidates=2,
        )
        self.assertEqual(
            selected,
            [
                app.ProxyTarget("203.0.113.1", 80, "http"),
                app.ProxyTarget("203.0.113.3", 80, "http"),
            ],
        )
        self.assertEqual(total, 3)


class OutputTests(unittest.TestCase):
    def test_speed_category_boundaries(self) -> None:
        self.assertIn("LIGHTNING", app.categorize_by_speed(199.99))
        self.assertIn("VERY FAST", app.categorize_by_speed(200.0))
        self.assertIn("FAST", app.categorize_by_speed(500.0))
        self.assertIn("GOOD", app.categorize_by_speed(1_000.0))
        self.assertIn("DECENT", app.categorize_by_speed(2_000.0))
        self.assertIn("SLOW", app.categorize_by_speed(5_000.0))

    def test_output_is_sorted_and_contains_safety_warning(self) -> None:
        results = (
            app.ProxyCheckResult(
                app.ProxyTarget("198.51.100.2", 8080, "http"),
                True,
                500.0,
            ),
            app.ProxyCheckResult(
                app.ProxyTarget("198.51.100.1", 1080, "socks5"),
                True,
                100.0,
            ),
            app.ProxyCheckResult(
                app.ProxyTarget("198.51.100.3", 3128, "http"),
                False,
                0.0,
                "timeout",
            ),
        )
        output = app.format_results(results)
        self.assertIn("Public proxies are untrusted", output)
        self.assertNotIn("198.51.100.3", output)
        self.assertLess(output.index("198.51.100.1"), output.index("198.51.100.2"))

    def test_atomic_save_replaces_stale_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "proxies.txt"
            destination.write_text("stale", encoding="utf-8")
            saved = app.save_working_proxies((), destination)
            content = destination.read_text(encoding="utf-8")
            self.assertEqual(saved, 0)
            self.assertNotIn("stale", content)
            self.assertIn("Total working proxies: 0", content)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


class AsyncSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_limited_reader_rejects_declared_oversize_body(self) -> None:
        response = cast(
            aiohttp.ClientResponse,
            FakeLimitedResponse([b"unused"], content_length=101),
        )
        with self.assertRaises(app.SourceTooLargeError):
            await app.read_limited_response(response, max_bytes=100)

    async def test_limited_reader_rejects_streamed_oversize_body(self) -> None:
        response = cast(
            aiohttp.ClientResponse,
            FakeLimitedResponse([b"a" * 60, b"b" * 60]),
        )
        with self.assertRaises(app.SourceTooLargeError):
            await app.read_limited_response(response, max_bytes=100)

    async def test_unsafe_source_is_blocked_before_request(self) -> None:
        source = app.SourceSpec("https://127.0.0.1/list.txt", "http")
        session = cast(aiohttp.ClientSession, object())
        result = await app.fetch_source(session, source, asyncio.Semaphore(1))
        self.assertEqual(result.error, "unsafe destination blocked")

    async def test_programmatic_private_target_is_blocked_before_request(self) -> None:
        target = app.ProxyTarget("127.0.0.1", 8080, "http")
        session = FakeSession(204)
        checker = app.FastProxyChecker(concurrent=1)
        result = await checker.check_proxy(
            cast(aiohttp.ClientSession, session),
            target,
        )
        self.assertFalse(result.alive)
        self.assertEqual(result.failure_reason, "unsafe target blocked")
        self.assertEqual(session.calls, [])

    async def test_http_check_requires_exact_204_without_redirects(self) -> None:
        target = app.ProxyTarget("203.0.113.10", 8080, "http")
        checker = app.FastProxyChecker(concurrent=1)

        success_session = FakeSession(204)
        success = await checker._check_http_proxy(
            cast(aiohttp.ClientSession, success_session),
            target,
        )
        self.assertTrue(success.alive)
        self.assertEqual(success_session.calls[0][1]["proxy"], target.url)
        self.assertFalse(success_session.calls[0][1]["allow_redirects"])

        redirect_session = FakeSession(302)
        redirect = await checker._check_http_proxy(
            cast(aiohttp.ClientSession, redirect_session),
            target,
        )
        self.assertFalse(redirect.alive)
        self.assertEqual(redirect.failure_reason, "unexpected status")

    async def test_worker_pool_respects_concurrency_bound(self) -> None:
        class DeterministicChecker(app.FastProxyChecker):
            def __init__(self) -> None:
                super().__init__(concurrent=3)
                self.active = 0
                self.maximum_active = 0

            async def check_proxy(
                self,
                http_session: aiohttp.ClientSession,
                target: app.ProxyTarget,
            ) -> app.ProxyCheckResult:
                del http_session
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
                await asyncio.sleep(0.01)
                self.active -= 1
                return app.ProxyCheckResult(target, True, 10.0)

        checker = DeterministicChecker()
        targets = [app.ProxyTarget(f"203.0.113.{index}", 8080, "http") for index in range(1, 11)]
        results = await checker.check_proxies(targets, show_progress=False)
        self.assertEqual(len(results), 10)
        self.assertLessEqual(checker.maximum_active, 3)

    async def test_no_candidate_run_invalidates_stale_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "proxies.txt"
            destination.write_text("stale endpoint data", encoding="utf-8")
            args = app.build_parser().parse_args(["--quiet", "--output", str(destination)])
            with (
                patch("sys.stdout"),
                patch("sys.stderr"),
                patch.object(
                    app,
                    "fetch_all_sources",
                    new=AsyncMock(return_value=[]),
                ),
            ):
                exit_code = await app.run(args)
            self.assertEqual(exit_code, 2)
            content = destination.read_text(encoding="utf-8")
            self.assertNotIn("stale endpoint data", content)
            self.assertIn("Total working proxies: 0", content)

    async def test_fetch_only_does_not_modify_output(self) -> None:
        target = app.ProxyTarget("203.0.113.10", 8080, "http")
        source_result = app.SourceFetchResult(
            app.SourceSpec("https://example.com/list.txt", "http"),
            (target,),
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "proxies.txt"
            destination.write_text("preserve me", encoding="utf-8")
            args = app.build_parser().parse_args(
                ["--quiet", "--fetch-only", "--output", str(destination)]
            )
            with (
                patch("sys.stdout"),
                patch("sys.stderr"),
                patch.object(
                    app,
                    "fetch_all_sources",
                    new=AsyncMock(return_value=[source_result]),
                ),
            ):
                exit_code = await app.run(args)
            self.assertEqual(exit_code, 0)
            self.assertEqual(destination.read_text(encoding="utf-8"), "preserve me")


class CliTests(unittest.TestCase):
    def test_cli_defaults_are_bounded(self) -> None:
        args = app.build_parser().parse_args([])
        self.assertEqual(args.concurrent, app.DEFAULT_CONCURRENCY)
        self.assertEqual(args.max_candidates, app.DEFAULT_MAX_CANDIDATES)

    def test_cli_rejects_excessive_concurrency(self) -> None:
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            app.build_parser().parse_args(["--concurrent", str(app.MAX_CONCURRENCY + 1)])

    def test_repository_text_contains_no_em_dash(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text_suffixes = {".md", ".py", ".toml", ".txt", ".yml", ".yaml"}
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in text_suffixes:
                continue
            if ".git" in path.parts or "tmp" in path.parts:
                continue
            with self.subTest(path=path.relative_to(root)):
                self.assertNotIn(chr(0x2014), path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

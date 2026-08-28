#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fetch, validate, rank, and save public proxy endpoints responsibly.

The application deliberately uses a fixed HTTPS connectivity endpoint, rejects
non-public IPv4 addresses, limits response sizes, and bounds all concurrency.
Public proxies are untrusted. Never send credentials or sensitive data through
an endpoint produced by this program.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import os
import re
import socket
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import DefaultResolver
from aiohttp_socks import ProxyConnector

VERSION = "2.0.0"
REPOSITORY_URL = "https://github.com/fusiontechstrategies/Ultra-Fast-Proxy-Fetcher-Tester"
TEST_URL = "https://www.gstatic.com/generate_204"
EXPECTED_TEST_STATUS = 204
DEFAULT_CONCURRENCY = 100
DEFAULT_FETCH_CONCURRENCY = 12
DEFAULT_MAX_CANDIDATES = 5_000
DEFAULT_PROXY_TIMEOUT = 8.0
DEFAULT_SOURCE_TIMEOUT = 12.0
MAX_CONCURRENCY = 500
MAX_FETCH_CONCURRENCY = 32
MAX_CANDIDATES = 50_000
MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_ENDPOINTS_PER_SOURCE = 10_000
MAX_REDIRECTS = 3
USER_AGENT = f"Ultra-Fast-Proxy-Fetcher-Tester/{VERSION} (+{REPOSITORY_URL})"

ProxyProtocol = Literal["http", "socks4", "socks5"]


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """A curated public source and the proxy transport it publishes."""

    url: str
    protocol: ProxyProtocol


@dataclass(frozen=True, slots=True)
class ProxyTarget:
    """A validated public proxy endpoint."""

    host: str
    port: int
    protocol: ProxyProtocol

    @property
    def authority(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        return f"{self.protocol}://{self.authority}"


@dataclass(frozen=True, slots=True)
class ProxyCheckResult:
    """The outcome of one proxy connectivity check."""

    target: ProxyTarget
    alive: bool
    response_time_ms: float
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SourceFetchResult:
    """The sanitized result of fetching one source."""

    source: SourceSpec
    targets: tuple[ProxyTarget, ...] = ()
    rejected: int = 0
    bytes_received: int = 0
    error: str | None = None


class UnsafeSourceError(ValueError):
    """Raised when a source or redirect does not meet destination policy."""


class SourceTooLargeError(ValueError):
    """Raised when a source exceeds the configured response limit."""


class PublicResolver(AbstractResolver):
    """Resolve hostnames while refusing every non-public destination."""

    def __init__(self) -> None:
        self._resolver = DefaultResolver()

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[ResolveResult]:
        results = await self._resolver.resolve(host, port, family)
        if not results or any(
            not is_global_unicast(
                ipaddress.ip_address(str(result["host"]).split("%", maxsplit=1)[0])
            )
            for result in results
        ):
            raise OSError("DNS destination policy rejected the source")
        return results

    async def close(self) -> None:
        await self._resolver.close()


# The list intentionally contains only sources that returned candidates during
# the 2026-08-12 maintenance audit. HTTPS lists describe HTTP CONNECT capability,
# so their transport is correctly represented as "http" for aiohttp.
PROXY_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "socks5",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "socks5",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
        "socks5",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
        "socks5",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
        "socks5",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/https.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks4.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt",
        "socks5",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/almroot/proxylist/master/list.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/aslisk/proxyhttps/main/https.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/HTTP.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/hendrikbgr/Free-Proxy-Repo/master/proxy_list.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/saisuiu/Lionkings-Http-Proxys-Proxies/main/free.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/https.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/socks4.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/socks5.txt",
        "socks5",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/https.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks4.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt",
        "socks5",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks4.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks5.txt",
        "socks5",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks4.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks5.txt",
        "socks5",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ObcbO/getproxy/master/file/http.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ObcbO/getproxy/master/file/https.txt",
        "http",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ObcbO/getproxy/master/file/socks4.txt",
        "socks4",
    ),
    SourceSpec(
        "https://raw.githubusercontent.com/ObcbO/getproxy/master/file/socks5.txt",
        "socks5",
    ),
    SourceSpec("https://free-proxy-list.net/", "http"),
    SourceSpec("https://www.sslproxies.org/", "http"),
    SourceSpec("https://www.us-proxy.org/", "http"),
)

PROXY_PATTERN = re.compile(r"(?<![\d.])(?P<host>\d{1,3}(?:\.\d{1,3}){3}):(?P<port>\d{1,5})(?!\d)")

SPEED_CATEGORIES: tuple[tuple[float, str], ...] = (
    (200.0, "LIGHTNING FAST (under 200ms)"),
    (500.0, "VERY FAST (200-499ms)"),
    (1_000.0, "FAST (500-999ms)"),
    (2_000.0, "GOOD (1000-1999ms)"),
    (5_000.0, "DECENT (2000-4999ms)"),
    (float("inf"), "SLOW (5000ms or more)"),
)


def is_global_unicast(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Return True only for a globally routable unicast address."""

    return (
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def is_public_ipv4(host: str) -> bool:
    """Return True only for globally routable unicast IPv4 addresses."""

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.version == 4 and is_global_unicast(address)


def parse_proxy_text(
    text: str,
    protocol: ProxyProtocol,
    *,
    address_validator: Callable[[str], bool] = is_public_ipv4,
    max_targets: int = MAX_ENDPOINTS_PER_SOURCE,
) -> tuple[tuple[ProxyTarget, ...], int]:
    """Extract, validate, and deduplicate proxy endpoints from source text."""

    if max_targets < 1:
        raise ValueError("max_targets must be positive")
    targets: dict[ProxyTarget, None] = {}
    rejected = 0
    for match in PROXY_PATTERN.finditer(text):
        host = match.group("host")
        port = int(match.group("port"))
        if not 1 <= port <= 65_535 or not address_validator(host):
            rejected += 1
            continue
        targets.setdefault(ProxyTarget(host, port, protocol), None)
        if len(targets) >= max_targets:
            break
    return tuple(targets), rejected


def is_safe_source_url(url: str) -> bool:
    """Validate the syntax and scheme of a source URL before connecting."""

    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False
    if port is not None and not 1 <= port <= 65_535:
        return False
    try:
        literal = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        hostname = parsed.hostname.rstrip(".").lower()
        return "." in hostname and hostname != "localhost" and not hostname.endswith(".local")
    return is_global_unicast(literal)


async def ensure_public_source_destination(url: str) -> None:
    """Resolve a source and block destinations containing non-public addresses."""

    if not is_safe_source_url(url):
        raise UnsafeSourceError("source URL rejected")
    parsed = urlparse(url)
    hostname = parsed.hostname
    if hostname is None:
        raise UnsafeSourceError("source hostname missing")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            answers = await loop.getaddrinfo(
                hostname,
                parsed.port or 443,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise UnsafeSourceError("source DNS lookup failed") from exc
        resolved = {str(answer[4][0]).split("%", maxsplit=1)[0] for answer in answers}
        if not resolved or any(
            not is_global_unicast(ipaddress.ip_address(item)) for item in resolved
        ):
            raise UnsafeSourceError("source resolved to a non-public address") from None
    else:
        if is_global_unicast(literal):
            return
        raise UnsafeSourceError("source uses a non-public address")


async def read_limited_response(
    response: aiohttp.ClientResponse,
    max_bytes: int = MAX_SOURCE_BYTES,
) -> bytes:
    """Read a response body while enforcing a decompressed size limit."""

    if response.content_length is not None and response.content_length > max_bytes:
        raise SourceTooLargeError("source response exceeded the size limit")
    content = bytearray()
    async for chunk in response.content.iter_chunked(64 * 1024):
        if len(content) + len(chunk) > max_bytes:
            raise SourceTooLargeError("source response exceeded the size limit")
        content.extend(chunk)
    return bytes(content)


async def fetch_source(
    session: aiohttp.ClientSession,
    source: SourceSpec,
    semaphore: asyncio.Semaphore,
) -> SourceFetchResult:
    """Fetch one source with redirect, destination, and body-size controls."""

    current_url = source.url
    async with semaphore:
        try:
            for redirect_count in range(MAX_REDIRECTS + 1):
                await ensure_public_source_destination(current_url)
                async with session.get(current_url, allow_redirects=False) as response:
                    if 300 <= response.status < 400:
                        location = response.headers.get("Location")
                        if not location or redirect_count == MAX_REDIRECTS:
                            return SourceFetchResult(source, error="redirect rejected")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status != 200:
                        return SourceFetchResult(source, error=f"HTTP {response.status}")
                    payload = await read_limited_response(response)
                    text = payload.decode("utf-8", errors="replace")
                    targets, rejected = parse_proxy_text(text, source.protocol)
                    if not targets:
                        return SourceFetchResult(
                            source,
                            rejected=rejected,
                            bytes_received=len(payload),
                            error="no valid public endpoints",
                        )
                    return SourceFetchResult(
                        source,
                        targets,
                        rejected,
                        len(payload),
                    )
        except asyncio.TimeoutError:
            return SourceFetchResult(source, error="timeout")
        except UnsafeSourceError:
            return SourceFetchResult(source, error="unsafe destination blocked")
        except SourceTooLargeError:
            return SourceFetchResult(source, error="response too large")
        except (aiohttp.ClientError, OSError, ValueError):
            return SourceFetchResult(source, error="connection error")
    return SourceFetchResult(source, error="unexpected redirect state")


async def fetch_all_sources(
    sources: Sequence[SourceSpec],
    *,
    concurrency: int,
    timeout_seconds: float,
    show_progress: bool,
) -> list[SourceFetchResult]:
    """Fetch all configured sources asynchronously."""

    timeout = aiohttp.ClientTimeout(
        total=timeout_seconds,
        connect=min(5.0, timeout_seconds),
        sock_connect=min(5.0, timeout_seconds),
        sock_read=timeout_seconds,
    )
    connector = aiohttp.TCPConnector(
        limit=concurrency,
        ttl_dns_cache=300,
        resolver=PublicResolver(),
    )
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/plain,text/html;q=0.8,*/*;q=0.1",
    }
    semaphore = asyncio.Semaphore(concurrency)
    results: list[SourceFetchResult] = []
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers=headers,
        cookie_jar=aiohttp.DummyCookieJar(),
        trust_env=False,
    ) as session:
        tasks = [
            asyncio.create_task(fetch_source(session, source, semaphore)) for source in sources
        ]
        for completed, task in enumerate(asyncio.as_completed(tasks), start=1):
            results.append(await task)
            if show_progress:
                print(
                    f"\rFetching sources: {completed:,}/{len(tasks):,}",
                    end="",
                    flush=True,
                )
    if show_progress:
        print()
    results_by_source = {result.source: result for result in results}
    return [results_by_source[source] for source in sources]


def merge_proxy_targets(
    source_results: Sequence[SourceFetchResult],
    *,
    protocol: str,
    max_candidates: int,
) -> tuple[list[ProxyTarget], int]:
    """Deduplicate targets fairly across sources and apply the candidate cap."""

    iterators = [iter(result.targets) for result in source_results if result.targets]
    active = iterators
    unique: dict[ProxyTarget, None] = {}
    while active:
        next_round = []
        for iterator in active:
            try:
                target = next(iterator)
            except StopIteration:
                continue
            next_round.append(iterator)
            if protocol == "all" or target.protocol == protocol:
                unique.setdefault(target, None)
        active = next_round
    all_targets = list(unique)
    return all_targets[:max_candidates], len(all_targets)


class ProgressReporter:
    """Render aggregate progress without printing third-party endpoints."""

    def __init__(self, total: int, enabled: bool) -> None:
        self.total = total
        self.enabled = enabled
        self.completed = 0
        self.working = 0
        self.last_rendered = 0.0

    def update(self, result: ProxyCheckResult) -> None:
        self.completed += 1
        self.working += int(result.alive)
        now = time.perf_counter()
        if not self.enabled or (self.completed != self.total and now - self.last_rendered < 0.1):
            return
        percentage = self.completed / self.total * 100
        print(
            f"\rTesting: {self.completed:,}/{self.total:,} "
            f"({percentage:5.1f}%) | Working: {self.working:,}",
            end="",
            flush=True,
        )
        self.last_rendered = now

    def finish(self) -> None:
        if self.enabled:
            print()


class FastProxyChecker:
    """Validate proxies using bounded async workers and an HTTPS 204 check."""

    def __init__(
        self,
        *,
        concurrent: int = DEFAULT_CONCURRENCY,
        timeout_seconds: float = DEFAULT_PROXY_TIMEOUT,
        test_url: str = TEST_URL,
        expected_status: int = EXPECTED_TEST_STATUS,
    ) -> None:
        if not 1 <= concurrent <= MAX_CONCURRENCY:
            raise ValueError(f"concurrent must be between 1 and {MAX_CONCURRENCY}")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.concurrent = concurrent
        self.test_url = test_url
        self.expected_status = expected_status
        self.timeout = aiohttp.ClientTimeout(
            total=timeout_seconds,
            connect=min(5.0, timeout_seconds),
            sock_connect=min(5.0, timeout_seconds),
            sock_read=timeout_seconds,
        )

    async def _check_http_proxy(
        self,
        session: aiohttp.ClientSession,
        target: ProxyTarget,
    ) -> ProxyCheckResult:
        started = time.perf_counter()
        async with session.get(
            self.test_url,
            proxy=target.url,
            allow_redirects=False,
        ) as response:
            elapsed = (time.perf_counter() - started) * 1_000
            if response.status == self.expected_status:
                return ProxyCheckResult(target, True, elapsed)
            return ProxyCheckResult(target, False, elapsed, "unexpected status")

    async def _check_socks_proxy(self, target: ProxyTarget) -> ProxyCheckResult:
        started = time.perf_counter()
        connector = ProxyConnector.from_url(target.url, limit=1)
        async with (
            aiohttp.ClientSession(
                connector=connector,
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT},
                cookie_jar=aiohttp.DummyCookieJar(),
                trust_env=False,
            ) as session,
            session.get(self.test_url, allow_redirects=False) as response,
        ):
            elapsed = (time.perf_counter() - started) * 1_000
            if response.status == self.expected_status:
                return ProxyCheckResult(target, True, elapsed)
            return ProxyCheckResult(target, False, elapsed, "unexpected status")

    async def check_proxy(
        self,
        http_session: aiohttp.ClientSession,
        target: ProxyTarget,
    ) -> ProxyCheckResult:
        """Check one target while containing all untrusted network failures."""

        if not is_public_ipv4(target.host) or not 1 <= target.port <= 65_535:
            return ProxyCheckResult(target, False, 0.0, "unsafe target blocked")
        try:
            if target.protocol == "http":
                return await self._check_http_proxy(http_session, target)
            return await self._check_socks_proxy(target)
        except asyncio.TimeoutError:
            return ProxyCheckResult(target, False, 0.0, "timeout")
        except (aiohttp.ClientConnectorCertificateError, aiohttp.ClientSSLError):
            return ProxyCheckResult(target, False, 0.0, "TLS failure")
        except (aiohttp.ClientError, OSError, ValueError):
            return ProxyCheckResult(target, False, 0.0, "connection failure")
        except Exception:  # noqa: BLE001 - isolates failures from untrusted endpoints
            return ProxyCheckResult(target, False, 0.0, "unexpected failure")

    async def check_proxies(
        self,
        targets: Sequence[ProxyTarget],
        *,
        show_progress: bool,
    ) -> list[ProxyCheckResult]:
        """Check targets through a fixed-size worker pool."""

        if not targets:
            return []
        queue: asyncio.Queue[ProxyTarget | None] = asyncio.Queue()
        for target in targets:
            queue.put_nowait(target)

        results: list[ProxyCheckResult] = []
        progress = ProgressReporter(len(targets), show_progress)
        connector = aiohttp.TCPConnector(
            limit=self.concurrent,
            ttl_dns_cache=300,
        )
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            headers={"User-Agent": USER_AGENT},
            cookie_jar=aiohttp.DummyCookieJar(),
            trust_env=False,
        ) as http_session:

            async def worker() -> None:
                while True:
                    target = await queue.get()
                    try:
                        if target is None:
                            return
                        result = await self.check_proxy(http_session, target)
                        results.append(result)
                        progress.update(result)
                    finally:
                        queue.task_done()

            worker_count = min(self.concurrent, len(targets))
            workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
            await queue.join()
            for _ in workers:
                queue.put_nowait(None)
            await asyncio.gather(*workers)
        progress.finish()
        return results


def categorize_by_speed(response_time_ms: float) -> str:
    """Return the output category for a measured response time."""

    for upper_bound, category in SPEED_CATEGORIES:
        if response_time_ms < upper_bound:
            return category
    raise AssertionError("speed categories must include an infinite upper bound")


def format_results(results: Sequence[ProxyCheckResult]) -> str:
    """Create the complete output document for an atomic write."""

    working = sorted(
        (result for result in results if result.alive),
        key=lambda result: result.response_time_ms,
    )
    lines = [
        "# " + "=" * 76,
        "# WORKING PUBLIC PROXIES",
        f"# Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"# Total working proxies: {len(working)}",
        "# Format: protocol://IP:PORT  # response_time",
        "# WARNING: Public proxies are untrusted. Never send credentials or sensitive data.",
        "# " + "=" * 76,
        "",
    ]
    grouped: dict[str, list[ProxyCheckResult]] = {category: [] for _, category in SPEED_CATEGORIES}
    for result in working:
        grouped[categorize_by_speed(result.response_time_ms)].append(result)
    for _, category in SPEED_CATEGORIES:
        category_results = grouped[category]
        if not category_results:
            continue
        lines.append(f"# {category}")
        lines.extend(
            f"{result.target.url:<34}  # {result.response_time_ms:.2f}ms"
            for result in category_results
        )
        lines.append("")
    return "\n".join(lines) + "\n"


def save_working_proxies(
    results: Sequence[ProxyCheckResult],
    output_file: str | Path,
) -> int:
    """Atomically replace the output, including when no proxies are working."""

    destination = Path(output_file).expanduser().resolve()
    if destination.exists() and destination.is_dir():
        raise IsADirectoryError(f"output path is a directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = format_results(results)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return sum(result.alive for result in results)


def integer_between(minimum: int, maximum: int) -> Callable[[str], int]:
    """Build an argparse integer validator."""

    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("must be an integer") from exc
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return parsed

    return parse


def float_between(minimum: float, maximum: float) -> Callable[[str], float]:
    """Build an argparse floating-point validator."""

    def parse(value: str) -> float:
        try:
            parsed = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("must be a number") from exc
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum:g} and {maximum:g}")
        return parsed

    return parse


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Fetch, validate, rank, and save public HTTP and SOCKS proxies "
            "with bounded asynchronous concurrency."
        ),
        epilog=(
            "Public proxies are untrusted. Use this tool only for authorized, "
            "lawful testing and never transmit secrets through discovered endpoints."
        ),
    )
    parser.add_argument(
        "--concurrent",
        type=integer_between(1, MAX_CONCURRENCY),
        default=DEFAULT_CONCURRENCY,
        metavar="N",
        help=f"proxy checks running at once (default: {DEFAULT_CONCURRENCY}, max: {MAX_CONCURRENCY})",
    )
    parser.add_argument(
        "--fetch-concurrent",
        type=integer_between(1, MAX_FETCH_CONCURRENCY),
        default=DEFAULT_FETCH_CONCURRENCY,
        metavar="N",
        help=f"source downloads running at once (default: {DEFAULT_FETCH_CONCURRENCY})",
    )
    parser.add_argument(
        "--max-candidates",
        type=integer_between(1, MAX_CANDIDATES),
        default=DEFAULT_MAX_CANDIDATES,
        metavar="N",
        help=f"maximum endpoints to test (default: {DEFAULT_MAX_CANDIDATES:,})",
    )
    parser.add_argument(
        "--timeout",
        type=float_between(1.0, 30.0),
        default=DEFAULT_PROXY_TIMEOUT,
        metavar="SECONDS",
        help=f"timeout for each proxy check (default: {DEFAULT_PROXY_TIMEOUT:g})",
    )
    parser.add_argument(
        "--source-timeout",
        type=float_between(3.0, 30.0),
        default=DEFAULT_SOURCE_TIMEOUT,
        metavar="SECONDS",
        help=f"timeout for each source download (default: {DEFAULT_SOURCE_TIMEOUT:g})",
    )
    parser.add_argument(
        "--protocol",
        choices=("all", "http", "socks4", "socks5"),
        default="all",
        help="protocol to test (default: all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("proxies.txt"),
        help="atomic output path (default: proxies.txt)",
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="fetch and validate source data without testing or saving endpoints",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="hide live progress while retaining the final summary",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Ultra-Fast Proxy Fetcher & Tester {VERSION}",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    """Execute one command-line run and return a process exit code."""

    print(f"Ultra-Fast Proxy Fetcher & Tester {VERSION}")
    print("Public proxies are untrusted. Never use them for sensitive traffic.")
    fetch_started = time.perf_counter()
    source_results = await fetch_all_sources(
        PROXY_SOURCES,
        concurrency=args.fetch_concurrent,
        timeout_seconds=args.source_timeout,
        show_progress=not args.quiet,
    )
    fetch_elapsed = time.perf_counter() - fetch_started
    successful_sources = sum(result.error is None for result in source_results)
    rejected = sum(result.rejected for result in source_results)
    candidates, total_unique = merge_proxy_targets(
        source_results,
        protocol=args.protocol,
        max_candidates=args.max_candidates,
    )
    print(f"Sources: {successful_sources:,}/{len(PROXY_SOURCES):,} usable in {fetch_elapsed:.2f}s")
    print(f"Rejected non-public or malformed entries: {rejected:,}")
    print(f"Unique {args.protocol.upper()} candidates: {total_unique:,}")
    if len(candidates) < total_unique:
        print(f"Candidate safety cap applied: selected {len(candidates):,}")

    source_errors = Counter(result.error for result in source_results if result.error is not None)
    if source_errors and not args.quiet:
        summary = ", ".join(f"{reason}: {count}" for reason, count in sorted(source_errors.items()))
        print(f"Unavailable source summary: {summary}")

    if not candidates:
        if not args.fetch_only:
            try:
                save_working_proxies((), args.output)
            except OSError as exc:
                print(f"Could not invalidate stale output: {exc}", file=sys.stderr)
                return 1
        print("No valid public proxy candidates were collected.", file=sys.stderr)
        return 2
    if args.fetch_only:
        print("Fetch-only validation complete. No proxy endpoints were saved.")
        return 0

    try:
        save_working_proxies((), args.output)
    except OSError as exc:
        print(f"Could not initialize output: {exc}", file=sys.stderr)
        return 1

    print(
        f"Testing {len(candidates):,} candidates with {args.concurrent:,} bounded workers "
        f"and a {args.timeout:g}s timeout."
    )
    checker = FastProxyChecker(
        concurrent=args.concurrent,
        timeout_seconds=args.timeout,
    )
    test_started = time.perf_counter()
    results = await checker.check_proxies(
        candidates,
        show_progress=not args.quiet,
    )
    test_elapsed = time.perf_counter() - test_started
    working = [result for result in results if result.alive]
    failures = Counter(
        result.failure_reason for result in results if result.failure_reason is not None
    )
    throughput = len(results) / test_elapsed if test_elapsed else 0.0

    print("\nResults")
    print(f"Test time: {test_elapsed:.2f}s")
    print(f"Throughput: {throughput:.1f} checks/second")
    print(f"Working: {len(working):,}/{len(results):,}")
    if working:
        timings = [result.response_time_ms for result in working]
        print(
            "Response time: "
            f"min {min(timings):.2f}ms, "
            f"average {sum(timings) / len(timings):.2f}ms, "
            f"max {max(timings):.2f}ms"
        )
        protocol_counts = Counter(result.target.protocol for result in working)
        print(
            "Working by protocol: "
            + ", ".join(
                f"{protocol.upper()} {count:,}"
                for protocol, count in sorted(protocol_counts.items())
            )
        )
    if failures:
        print(
            "Failure summary: "
            + ", ".join(f"{reason}: {count:,}" for reason, count in sorted(failures.items()))
        )

    try:
        saved = save_working_proxies(results, args.output)
    except OSError as exc:
        print(f"Could not write output: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {saved:,} working proxies to {args.output}")
    if not working:
        print("No working proxies were found. The output was safely replaced with an empty report.")
        return 3
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the application."""

    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

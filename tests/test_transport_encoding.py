"""Real loopback HTTP checks for encoded-source expansion before byte budgets."""

import asyncio
import gzip
import unittest
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import web

import proxy_fetcher_ultimate as app


class IdentityTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_compressed_response_is_rejected_before_decompression(self):
        endpoint = ("8.8.8.8" + ":8080\n").encode()
        expanded = endpoint * (app.MAX_SOURCE_BYTES // 12 + 1)
        compressed = gzip.compress(expanded)
        self.assertGreater(len(expanded), app.MAX_SOURCE_BYTES)
        self.assertLess(len(compressed), 100_000)
        observed = []

        async def serve(request):
            observed.append(request.headers.get("Accept-Encoding"))
            if request.path == "/encoded":
                return web.Response(body=compressed, headers={"Content-Encoding": "gzip"})
            return web.Response(body=endpoint)

        server = web.Application()
        server.router.add_get("/{name}", serve)
        runner = web.AppRunner(server)
        await runner.setup()
        # Port zero obtains an ephemeral loopback listener without public traffic.
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = runner.addresses[0][1]
        try:
            # The caller deliberately uses aiohttp's decompression default. The
            # fetcher's per-request override must still protect this code path.
            async with aiohttp.ClientSession() as session:
                with patch.object(app, "ensure_public_source_destination", AsyncMock()):
                    encoded = await app.fetch_source(
                        session,
                        app.SourceSpec(f"http://127.0.0.1:{port}/encoded", "http"),
                        asyncio.Semaphore(1),
                    )
                    identity = await app.fetch_source(
                        session,
                        app.SourceSpec(f"http://127.0.0.1:{port}/identity", "http"),
                        asyncio.Semaphore(1),
                    )
            self.assertEqual(encoded.error, "response too large")
            self.assertEqual(encoded.bytes_received, 0)
            self.assertFalse(identity.error)
            self.assertEqual(identity.bytes_received, 13)
            self.assertEqual(observed, ["identity", "identity"])
        finally:
            await runner.cleanup()

    async def test_any_nonidentity_encoding_is_refused_without_reading_content(self):
        class UnreadableContent:
            def iter_chunked(self, size):
                raise AssertionError("Encoded body must not be consumed")

        for encoding in ("gzip", "deflate", "br", "gzip, identity", "unknown"):
            response = type(
                "EncodedResponse",
                (),
                {"headers": {"Content-Encoding": encoding}, "content": UnreadableContent()},
            )()
            with self.subTest(encoding=encoding), self.assertRaises(app.SourceTooLargeError):
                await app.read_limited_response(response)

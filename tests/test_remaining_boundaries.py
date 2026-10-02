"""Offline hostile-body, output-link and archive-budget regressions."""

import asyncio
import io
import os
import struct
import tarfile
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import proxy_fetcher_ultimate as app
from scripts import verify_distribution as verifier


class CandidateWorkTests(unittest.TestCase):
    def test_duplicates_and_rejected_candidates_consume_total_budget(self):
        for accepted in (False, True):
            calls = []

            def validate(host, calls=calls, accepted=accepted):
                calls.append(host)
                return accepted

            with self.assertRaises(app.SourceTooLargeError):
                app.parse_proxy_text(
                    "8.8.8.8:80\n" * 500, "http", address_validator=validate, max_validations=20
                )
            self.assertEqual(len(calls), 20)


class CooperativeParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_dense_duplicate_work_yields_to_deadline(self):
        calls = []

        def slow_validator(host):
            calls.append(host)
            time.sleep(0.001)
            return True

        with (
            patch.object(app, "is_public_ipv4", side_effect=slow_validator),
            self.assertRaises(asyncio.TimeoutError),
        ):
            await asyncio.wait_for(
                app.parse_proxy_text_async("8.8.8.8:80\n" * 5000, "http"), timeout=0.01
            )
        # Host timer granularity varies. Cancellation must bound completed work,
        # rather than require a universal subsecond wall-clock threshold.
        self.assertGreater(len(calls), 0)
        self.assertLessEqual(len(calls), 512)


class OutputBoundaryTests(unittest.TestCase):
    def test_output_link_never_changes_target_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            victim, output = root / "victim.txt", root / "output.txt"
            victim.write_text("unchanged")
            try:
                output.symlink_to(victim)
            except OSError as exc:
                self.skipTest(f"Symlink creation unavailable: {exc}")
            with self.assertRaises((PermissionError, OSError)):
                app.save_working_proxies((), output)
            self.assertEqual(victim.read_text(), "unchanged")

    @unittest.skipUnless(os.name == "nt", "Windows directory sharing")
    def test_windows_pinned_parent_cannot_be_renamed(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "parent"
            parent.mkdir()
            with app.pinned_output_parent(parent), self.assertRaises(PermissionError):
                parent.rename(Path(directory) / "replacement")

    @unittest.skipIf(os.name == "nt", "POSIX ancestor permissions")
    def test_unsafe_nonsticky_ancestor_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            unsafe = Path(directory) / "shared"
            unsafe.mkdir(mode=0o777)
            unsafe.chmod(0o777)
            parent = unsafe / "private"
            parent.mkdir(mode=0o700)
            try:
                with self.assertRaises(PermissionError):
                    app.save_working_proxies((), parent / "output.txt")
            finally:
                unsafe.chmod(0o700)


class ArchiveBudgetTests(unittest.TestCase):
    def test_zip64_legacy_zero_record_is_rejected_before_zipfile(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "test.whl"
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                for index in range(5000):
                    archive.writestr(str(index), b"x")
            raw = stream.getvalue()
            end = len(raw) - 22
            _, _, _, _, count, cd_bytes, cd_offset, _ = struct.unpack("<4s4H2LH", raw[end:])
            zip64 = struct.pack(
                "<4sQ2H2L4Q",
                b"PK\x06\x06",
                44,
                45,
                45,
                0,
                0,
                count,
                count,
                cd_bytes,
                cd_offset,
            )
            locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, end, 1)
            for comment_size in (0, 65516, 65535):
                legacy_zero = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 0, 0, 0, 0, comment_size)
                crafted = raw[:end] + zip64 + locator + legacy_zero + b"x" * comment_size
                with zipfile.ZipFile(io.BytesIO(crafted)) as archive:
                    self.assertEqual(len(archive.infolist()), 5000)
                wheel.write_bytes(crafted)
                with (
                    self.subTest(comment_size=comment_size),
                    patch.object(
                        verifier.zipfile, "ZipFile", side_effect=AssertionError("too late")
                    ),
                    self.assertRaisesRegex(ValueError, "ZIP64"),
                    verifier.bounded_wheel(wheel),
                ):
                    pass

    def test_zip_member_decoder_size_and_count_budgets(self):
        for kind in ("decoder", "size", "count"):
            with tempfile.TemporaryDirectory() as directory:
                wheel = Path(directory) / "test.whl"
                compression = zipfile.ZIP_LZMA if kind == "decoder" else zipfile.ZIP_DEFLATED
                with zipfile.ZipFile(wheel, "w", compression=compression) as archive:
                    if kind == "count":
                        for index in range(verifier.MAX_ARCHIVE_MEMBERS + 1):
                            archive.writestr(str(index), b"x")
                    else:
                        archive.writestr(
                            "member",
                            b"x" * (verifier.MAX_MEMBER_BYTES + 1 if kind == "size" else 1),
                        )
                with self.assertRaises(ValueError), verifier.bounded_wheel(wheel):
                    pass

    def test_tar_declared_size_budget_precedes_contents_read(self):
        with tempfile.TemporaryDirectory() as directory:
            sdist = Path(directory) / "test.tar.gz"
            with tarfile.open(sdist, "w:gz") as archive:
                member = tarfile.TarInfo("member")
                member.size = verifier.MAX_MEMBER_BYTES + 1
                archive.addfile(member, io.BytesIO(b"x" * member.size))
            with self.assertRaises(ValueError), verifier.bounded_sdist(sdist):
                pass

    def test_invisible_pax_expansion_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            sdist = Path(directory) / "test.tar.gz"
            with tarfile.open(sdist, "w:gz", format=tarfile.PAX_FORMAT) as archive:
                member = tarfile.TarInfo("member")
                member.pax_headers = {"comment": "x" * (verifier.MAX_EXPANDED_BYTES + 1)}
                archive.addfile(member)
            with self.assertRaises(ValueError), verifier.bounded_sdist(sdist):
                pass


if __name__ == "__main__":
    unittest.main()

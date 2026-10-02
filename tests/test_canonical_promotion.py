"""Trusted promotion canonical bytes and cross-platform package boundaries."""

from __future__ import annotations

import copy
import gzip
import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

import test_security_regressions as fixtures
from test_publication_followups import rewrite_wheel

from scripts import (
    normalize_sdist,
    normalize_wheel,
    prepare_release,
    verify_distribution,
    verify_release_handoff,
)

ROOT = fixtures.ROOT
VERSION, COMMIT, EPOCH = "2.0.1", "a" * 40, 1767225600


class CanonicalHandoff(unittest.TestCase):
    def candidate(self, root):
        dist = root / "dist"
        dist.mkdir()
        wheel, sdist = fixtures.DistributionSecurityTests().fixture_distributions(dist)
        normalize_wheel.normalize_wheel(wheel, EPOCH)
        normalize_sdist.normalize_sdist(sdist, EPOCH)
        return dist, wheel, sdist

    def test_logically_valid_noncanonical_wheel_is_rejected_after_producer_rehash(self):
        for mutation in ("comment", "order", "timestamp", "extra", "mode", "compression"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                dist, wheel, _ = self.candidate(root)
                with zipfile.ZipFile(wheel) as archive:
                    entries = [(copy.copy(info), archive.read(info)) for info in archive.infolist()]
                if mutation == "order":
                    entries.reverse()
                if mutation == "timestamp":
                    entries[0][0].date_time = (2020, 1, 1, 0, 0, 0)
                if mutation == "extra":
                    entries[0][0].extra = b"\xff\xff\x04\x00bait"
                if mutation == "mode":
                    entries[0][0].external_attr = 0o100777 << 16
                if mutation == "compression":
                    entries[0][0].compress_type = zipfile.ZIP_DEFLATED
                with zipfile.ZipFile(wheel, "w") as archive:
                    if mutation == "comment":
                        archive.comment = b"unreviewed producer metadata"
                    for info, data in entries:
                        archive.writestr(info, data)
                assets = root / "assets"
                prepare_release.prepare_release(
                    ROOT, dist, assets, VERSION, "v" + VERSION, COMMIT, EPOCH
                )
                with self.assertRaisesRegex(ValueError, "not canonical"):
                    verify_release_handoff.verify_handoff(assets, ROOT, COMMIT, EPOCH)

    def test_logically_valid_noncanonical_sdist_is_rejected_after_producer_rehash(self):
        for mutation in ("gzip", "order", "owner", "mode", "timestamp", "pax"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                dist, _, sdist = self.candidate(root)
                with tarfile.open(sdist, "r:gz") as archive:
                    entries = [
                        (
                            copy.copy(member),
                            archive.extractfile(member).read() if member.isfile() else None,
                        )
                        for member in archive
                    ]
                if mutation == "order":
                    entries.reverse()
                if mutation == "owner":
                    entries[0][0].uid, entries[0][0].uname = 123, "unreviewed"
                if mutation == "mode":
                    entries[0][0].mode = 0o777
                if mutation == "timestamp":
                    entries[0][0].mtime = EPOCH + 1
                if mutation == "pax":
                    entries[0][0].pax_headers = {"comment": "unreviewed"}
                raw = io.BytesIO()
                with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for info, data in entries:
                        archive.addfile(info, None if data is None else io.BytesIO(data))
                sdist.write_bytes(
                    gzip.compress(raw.getvalue(), mtime=EPOCH + 1)
                    if mutation == "gzip"
                    else normalize_sdist.build_stored_gzip(raw.getvalue(), EPOCH)
                )
                assets = root / "assets"
                prepare_release.prepare_release(
                    ROOT, dist, assets, VERSION, "v" + VERSION, COMMIT, EPOCH
                )
                with self.assertRaisesRegex(ValueError, "not canonical"):
                    verify_release_handoff.verify_handoff(assets, ROOT, COMMIT, EPOCH)

    def test_canonical_handoff_rejects_wrong_authenticated_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist, _, _ = self.candidate(root)
            assets = root / "assets"
            prepare_release.prepare_release(
                ROOT, dist, assets, VERSION, "v" + VERSION, COMMIT, EPOCH
            )
            with self.assertRaisesRegex(ValueError, "authenticated source identity"):
                verify_release_handoff.verify_handoff(assets, ROOT, COMMIT, EPOCH + 2)

    def test_canonical_handoff_accepts_reviewed_distributions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist, _, _ = self.candidate(root)
            assets = root / "assets"
            prepare_release.prepare_release(
                ROOT, dist, assets, VERSION, "v" + VERSION, COMMIT, EPOCH
            )
            result = verify_release_handoff.verify_handoff(assets, ROOT, COMMIT, EPOCH)
            self.assertEqual(result["tag"], "v" + VERSION)
            self.assertEqual(len(result["manifest"]), 7)

    def test_rehashed_extra_marker_tautology_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, _ = fixtures.DistributionSecurityTests().fixture_distributions(root)
            verify_distribution.verify_distribution(root, ROOT, VERSION)
            with zipfile.ZipFile(wheel) as archive:
                name = next(name for name in archive.namelist() if name.endswith("/METADATA"))
                value = archive.read(name).replace(
                    b"Requires-Dist: aiohttp==3.14.3",
                    b'Requires-Dist: aiohttp==3.14.3; extra == "aws" or extra != "aws"',
                )
            rewrite_wheel(wheel, {name: value})
            with self.assertRaisesRegex(ValueError, "dependencies"):
                verify_distribution.verify_distribution(root, ROOT, VERSION)

    def test_unreviewed_windows_shortname_members_are_rejected(self):
        for name in ("pyproj~1.tom", "setup~1.cfg", "requir~1.txt"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, sdist = fixtures.DistributionSecurityTests().fixture_distributions(root)
                verify_distribution.verify_distribution(root, ROOT, VERSION)
                with tarfile.open(sdist, "r:gz") as archive:
                    members = [(member, archive.extractfile(member).read()) for member in archive]
                with tarfile.open(sdist, "w:gz") as archive:
                    for member, data in members:
                        archive.addfile(member, io.BytesIO(data))
                    extra = tarfile.TarInfo(
                        "ultra_fast_proxy_fetcher_tester-" + VERSION + "/" + name
                    )
                    value = b"unreviewed source build configuration"
                    extra.size = len(value)
                    archive.addfile(extra, io.BytesIO(value))
                with self.assertRaisesRegex(ValueError, "unreviewed installation members"):
                    verify_distribution.verify_distribution(root, ROOT, VERSION)

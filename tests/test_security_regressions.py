"""Offline adversarial checks for complete deadlines and publication byte binding."""

from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import io
import shutil
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import proxy_fetcher_ultimate as app
from scripts import verify_distribution
from scripts import verify_release_integrity as integrity

ROOT = Path(__file__).resolve().parents[1]


class SourceDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_timed_out_dns_child_is_killed_and_reaped(self):
        original = asyncio.create_subprocess_exec
        children = []

        async def controlled_child(*args, **kwargs):
            process = await original(args[0], "-I", "-c", "import time; time.sleep(30)", **kwargs)
            children.append(process)
            return process

        with patch.object(asyncio, "create_subprocess_exec", side_effect=controlled_child):
            result = await app.fetch_source(
                object(),
                app.SourceSpec("https://public.example.invalid/list", "http"),
                asyncio.Semaphore(1),
                timeout_seconds=0.2,
            )
        self.assertEqual(result.error, "timeout")
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)

    async def test_slow_preflight_dns_is_inside_source_deadline(self):
        source = app.SourceSpec("https://public.example.invalid/list.txt", "http")
        gate = asyncio.Event()

        async def slow_dns(*args, **kwargs):
            await gate.wait()

        with patch.object(app, "cancellable_dns", side_effect=slow_dns):
            result = await app.fetch_source(
                object(), source, asyncio.Semaphore(1), timeout_seconds=0.02
            )
        self.assertEqual(result.error, "timeout")

    async def test_manual_redirects_share_one_deadline(self):
        calls = []

        class Context:
            async def __aenter__(self):
                await asyncio.sleep(0.03)
                return SimpleNamespace(
                    status=302, headers={"Location": "https://public.example.invalid/next"}
                )

            async def __aexit__(self, *args):
                return None

        class Session:
            def get(self, url, **kwargs):
                calls.append(url)
                return Context()

        with patch.object(app, "ensure_public_source_destination", AsyncMock()):
            result = await app.fetch_source(
                Session(),
                app.SourceSpec("https://public.example.invalid/start", "http"),
                asyncio.Semaphore(1),
                timeout_seconds=0.05,
            )
        self.assertEqual(result.error, "timeout")
        self.assertLess(len(calls), app.MAX_REDIRECTS + 1)


class DistributionSecurityTests(unittest.TestCase):
    def fixture_distributions(self, directory):
        version = "2.0.1"
        wheel = directory / f"ultra_fast_proxy_fetcher_tester-{version}-py3-none-any.whl"
        sdist = directory / f"ultra_fast_proxy_fetcher_tester-{version}.tar.gz"
        metadata = f"Metadata-Version: 2.4\nName: ultra-fast-proxy-fetcher-tester\nVersion: {version}\nRequires-Dist: aiohttp==3.14.3\nRequires-Dist: aiohttp-socks==0.12.0\nRequires-Python: <3.15,>=3.10\nDescription-Content-Type: text/markdown\nLicense-Expression: MIT\nLicense-File: LICENSE\n"
        project = verify_distribution.reviewed_project(ROOT)["project"]
        metadata += f"Summary: {project['description']}\nAuthor: {project['authors'][0]['name']}\n"
        metadata += "".join(
            f"Project-URL: {label}, {url}\n" for label, url in project["urls"].items()
        )
        metadata += "".join(f"Classifier: {value}\n" for value in project["classifiers"])
        metadata = (metadata + "\n" + (ROOT / "README.md").read_text(encoding="utf-8")).encode(
            "utf-8"
        )
        entry = b"[console_scripts]\nproxy-fetcher-tester = proxy_fetcher_ultimate:main\n"
        prefix = f"ultra_fast_proxy_fetcher_tester-{version}.dist-info/"
        values = {
            verify_distribution.MODULE: (ROOT / verify_distribution.MODULE).read_bytes(),
            prefix + "METADATA": metadata,
            prefix
            + "WHEEL": b"Wheel-Version: 1.0\nGenerator: setuptools (84.0.0)\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            prefix + "entry_points.txt": entry,
            prefix + "top_level.txt": b"proxy_fetcher_ultimate\n",
            prefix + "licenses/LICENSE": (ROOT / "LICENSE").read_bytes(),
        }
        record = io.StringIO(newline="")
        writer = csv.writer(record)
        for name, data in values.items():
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            writer.writerow([name, "sha256=" + digest, len(data)])
        writer.writerow([prefix + "RECORD", "", ""])
        values[prefix + "RECORD"] = record.getvalue().encode()
        with zipfile.ZipFile(wheel, "w") as archive:
            for name, data in values.items():
                archive.writestr(name, data)
        reviewed = {
            verify_distribution.MODULE,
            "LICENSE",
            "README.md",
            "pyproject.toml",
            "requirements.txt",
        }
        reviewed.update(
            path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").glob("test_*.py")
        )
        members = {name: (ROOT / name).read_bytes() for name in reviewed}
        members.update(
            {"PKG-INFO": metadata, "setup.cfg": b"[egg_info]\ntag_build = \ntag_date = 0\n"}
        )
        generated = {
            "PKG-INFO": metadata,
            "dependency_links.txt": b"\n",
            "entry_points.txt": entry,
            "top_level.txt": b"proxy_fetcher_ultimate\n",
        }
        generated["requires.txt"] = (ROOT / "requirements.txt").read_bytes()
        for name, data in generated.items():
            members[f"ultra_fast_proxy_fetcher_tester.egg-info/{name}"] = data
        listed = (set(members) - {"PKG-INFO", "setup.cfg"}) | {
            "ultra_fast_proxy_fetcher_tester.egg-info/SOURCES.txt"
        }
        members["ultra_fast_proxy_fetcher_tester.egg-info/SOURCES.txt"] = "\n".join(
            sorted(listed)
        ).encode()
        with tarfile.open(sdist, "w:gz") as archive:
            for name, data in members.items():
                info = tarfile.TarInfo(f"ultra_fast_proxy_fetcher_tester-{version}/{name}")
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        return wheel, sdist

    def test_added_installation_active_wheel_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, _ = self.fixture_distributions(root)
            verify_distribution.verify_distribution(root, ROOT, "2.0.1")
            with zipfile.ZipFile(wheel, "a") as archive:
                archive.writestr("startup.pth", "import synthetic")
            with self.assertRaisesRegex(ValueError, "unreviewed installation members"):
                verify_distribution.verify_distribution(root, ROOT, "2.0.1")

    def test_added_installation_active_sdist_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, sdist = self.fixture_distributions(root)
            with tarfile.open(sdist, "r:gz") as archive:
                members = [(member, archive.extractfile(member).read()) for member in archive]
            with tarfile.open(sdist, "w:gz") as archive:
                for member, data in members:
                    archive.addfile(member, io.BytesIO(data))
                archive.addfile(tarfile.TarInfo("ultra_fast_proxy_fetcher_tester-2.0.1/setup.py"))
            with self.assertRaisesRegex(ValueError, "unreviewed installation members"):
                verify_distribution.verify_distribution(root, ROOT, "2.0.1")

    def test_publication_copy_mutation_cannot_hide_behind_original_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release, dist = root / "release", root / "dist"
            release.mkdir()
            dist.mkdir()
            names = [
                "candidate.whl",
                "candidate.tar.gz",
                "runtime.py",
                "runtime.zip",
                "sbom.json",
                "SHA256SUMS.txt",
                "evidence.json",
            ]
            for name in names:
                (release / name).write_bytes(b"verified original")
            captured = integrity.manifest(release)
            for name in names[:2]:
                shutil.copyfile(release / name, dist / name)
            integrity.verify_distributions(dist, captured)
            (dist / names[0]).write_bytes(b"substituted copy")
            with self.assertRaisesRegex(ValueError, "attested original"):
                integrity.verify_distributions(dist, captured)
            integrity.verify_assets(release, captured)

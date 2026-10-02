"""Special-purpose addresses must stay blocked across Python patch versions."""

import ipaddress
import unittest
from unittest.mock import PropertyMock, patch

import proxy_fetcher_ultimate as app


class SpecialAddressPolicy(unittest.TestCase):
    def test_special_registry_blocks_do_not_depend_on_stdlib_is_global(self):
        addresses = (
            "0.1.2.3",
            "10.1.2.3",
            "100.64.0.1",
            "127.0.0.1",
            "169.254.169.254",
            "172.16.0.1",
            "192.0.0.8",
            "192.0.0.9",
            "192.0.2.1",
            "192.31.196.1",
            "192.52.193.1",
            "192.88.99.2",
            "192.168.1.1",
            "192.175.48.1",
            "198.18.0.1",
            "198.51.100.1",
            "203.0.113.1",
            "224.0.0.1",
            "240.0.0.1",
            "::",
            "::1",
            "::ffff:127.0.0.1",
            "64:ff9b::a00:1",
            "64:ff9b:1::1",
            "100::1",
            "100:0:0:1::1",
            "2001::1",
            "2001:1::1",
            "2001:20::1",
            "2001:db8::1",
            "2002:a00:1::1",
            "2620:4f:8000::1",
            "3fff::1",
            "5f00::1",
            "fc00::1",
            "fe80::1",
            "fec0::1",
            "ff02::1",
        )
        with (
            patch.object(
                ipaddress.IPv4Address, "is_global", new_callable=PropertyMock, return_value=True
            ),
            patch.object(
                ipaddress.IPv6Address, "is_global", new_callable=PropertyMock, return_value=True
            ),
        ):
            for address in addresses:
                with self.subTest(address=address):
                    self.assertFalse(app.is_global_unicast(ipaddress.ip_address(address)))

    def test_ordinary_public_endpoints_remain_allowed(self):
        for address in (
            "8.8.8.8",
            "1.1.1.1",
            "9.9.9.9",
            "2606:4700:4700::1111",
            "2001:4860:4860::8888",
        ):
            with self.subTest(address=address):
                self.assertTrue(app.is_global_unicast(ipaddress.ip_address(address)))

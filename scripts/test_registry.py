#!/usr/bin/env python3
"""
test_registry.py - Automated test suite for modify_registry.py.
"""

import os
import shutil
import tempfile
import unittest
import subprocess

from modify_registry import HivexLib, HiveEditor


class TestModifyRegistry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.sample_hive = "/opt/homebrew/share/hivex/test/large"
        if not os.path.exists(self.sample_hive):
            self.skipTest(f"Sample hive not found at {self.sample_hive}")
        self.test_hive = os.path.join(self.temp_dir, "test_hive")
        shutil.copyfile(self.sample_hive, self.test_hive)
        self.hlib = HivexLib()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_set_dword_and_string(self):
        with HiveEditor(self.test_hive, self.hlib) as h:
            h.set_dword("Setup\\LabConfig", "BypassTPMCheck", 1)
            h.set_string("Setup\\LabConfig", "TestString", "Hello Tiny11")

        # Verify via hivexget command
        out_dword = subprocess.check_output(
            ["hivexget", self.test_hive, r"Setup\LabConfig", "BypassTPMCheck"],
            text=True,
        ).strip()
        self.assertEqual(out_dword, "1")

        out_str = subprocess.check_output(
            ["hivexget", self.test_hive, r"Setup\LabConfig", "TestString"],
            text=True,
        ).strip()
        self.assertEqual(out_str, "Hello Tiny11")

    def test_delete_key(self):
        with HiveEditor(self.test_hive, self.hlib) as h:
            h.get_or_create_key("Custom\\Key\\ToDelete")

        with HiveEditor(self.test_hive, self.hlib) as h:
            node = h.get_key("Custom\\Key\\ToDelete")
            self.assertIsNotNone(node)
            h.delete_key("Custom\\Key\\ToDelete")

        with HiveEditor(self.test_hive, self.hlib) as h:
            node = h.get_key("Custom\\Key\\ToDelete")
            self.assertIsNone(node)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
test_unattend.py - Tests validation and customization of autounattend.xml
"""

import xml.etree.ElementTree as ET
import subprocess
import tempfile
import os
import unittest


class TestUnattend(unittest.TestCase):
    def setUp(self):
        self.xml_path = os.path.join(os.path.dirname(__file__), "..", "autounattend.xml")

    def test_xml_structure_validity(self):
        tree = ET.parse(self.xml_path)
        root = tree.getroot()
        self.assertTrue(root.tag.endswith("unattend"))

        # Every child of <unattend> must be <settings>
        child_tags = [c.tag.split("}")[-1] for c in root]
        self.assertTrue(all(tag in ("settings", "servicing") for tag in child_tags))

        # Check passes present
        passes = [c.attrib.get("pass") for c in root if c.tag.endswith("settings")]
        self.assertIn("windowsPE", passes)
        self.assertIn("specialize", passes)
        self.assertIn("oobeSystem", passes)

    def test_sed_templating(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            temp_path = tf.name

        try:
            # Emulate tiny11maker.sh sed replacement
            cmd = (
                f"sed -e 's/processorArchitecture=\"amd64\"/processorArchitecture=\"arm64\"/g' "
                f"-e 's/<Name>Tiny11<\\/Name>/<Name>CustomUser<\\/Name>/g' "
                f"-e 's/<DisplayName>Tiny11<\\/DisplayName>/<DisplayName>CustomUser<\\/DisplayName>/g' "
                f"-e 's/<Username>Tiny11<\\/Username>/<Username>CustomUser<\\/Username>/g' "
                f"'{self.xml_path}' > '{temp_path}'"
            )
            subprocess.check_call(cmd, shell=True)

            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn('processorArchitecture="arm64"', content)
            self.assertNotIn('processorArchitecture="amd64"', content)
            self.assertIn("<Name>CustomUser</Name>", content)
            self.assertIn("<Username>CustomUser</Username>", content)
            self.assertIn("<HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>", content)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()

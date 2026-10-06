#!/usr/bin/env python3
"""
test_unattend.py - Tests validation and customization of autounattend.xml in both
default interactive mode and automated unattended mode.
"""

import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


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

    def test_default_mode(self):
        """Default mode: standard interactive setup, no automated user accounts"""
        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            temp_path = tf.name

        try:
            # Emulate default tiny11maker.sh behavior (AUTO_USER=0)
            subprocess.check_call(
                f"sed -e 's/processorArchitecture=\"amd64\"/processorArchitecture=\"arm64\"/g' "
                f"'{self.xml_path}' > '{temp_path}'",
                shell=True,
            )
            subprocess.check_call(
                f"sed -i.bak '/<!-- USER_ACCOUNTS_PLACEHOLDER -->/d' '{temp_path}' && rm -f '{temp_path}.bak'",
                shell=True,
            )

            # Check valid XML parse
            tree = ET.parse(temp_path)
            self.assertIsNotNone(tree.getroot())

            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn('processorArchitecture="arm64"', content)
            self.assertNotIn("USER_ACCOUNTS_PLACEHOLDER", content)
            self.assertNotIn("<UserAccounts>", content)
            self.assertNotIn("<AutoLogon>", content)
            self.assertIn("<HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>", content)
            self.assertIn("<HideOnlineAccountScreens>true</HideOnlineAccountScreens>", content)
            self.assertIn("BypassNRO", content)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_skip_user_creation_mode(self):
        """Unattended mode with auto-created user and auto-logon"""
        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            temp_path = tf.name

        try:
            username = "DevUser"
            subprocess.check_call(
                f"sed -e 's/processorArchitecture=\"amd64\"/processorArchitecture=\"arm64\"/g' "
                f"'{self.xml_path}' > '{temp_path}'",
                shell=True,
            )

            user_xml = (
                "            <UserAccounts>\n"
                "                <LocalAccounts>\n"
                "                    <LocalAccount wcm:action=\"add\">\n"
                "                        <Description>Local Administrator</Description>\n"
                f"                        <DisplayName>{username}</DisplayName>\n"
                "                        <Group>Administrators</Group>\n"
                f"                        <Name>{username}</Name>\n"
                "                        <Password>\n"
                "                            <Value></Value>\n"
                "                            <PlainText>true</PlainText>\n"
                "                        </Password>\n"
                "                    </LocalAccount>\n"
                "                </LocalAccounts>\n"
                "            </UserAccounts>\n"
                "            <AutoLogon>\n"
                "                <Enabled>true</Enabled>\n"
                "                <LogonCount>1</LogonCount>\n"
                f"                <Username>{username}</Username>\n"
                "                <Password>\n"
                "                    <Value></Value>\n"
                "                    <PlainText>true</PlainText>\n"
                "                </Password>\n"
                "            </AutoLogon>"
            )

            with open(temp_path, "r", encoding="utf-8") as f:
                c = f.read()
            c = c.replace("<!-- USER_ACCOUNTS_PLACEHOLDER -->", user_xml)
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(c)

            # Check valid XML parse
            tree = ET.parse(temp_path)
            self.assertIsNotNone(tree.getroot())

            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn(f"<Name>{username}</Name>", content)
            self.assertIn(f"<Username>{username}</Username>", content)
            self.assertIn("<AutoLogon>", content)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_skip_autologon_mode(self):
        """Unattended mode with auto-created user but no auto-logon"""
        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            temp_path = tf.name

        try:
            username = "AdminUser"
            subprocess.check_call(
                f"sed -e 's/processorArchitecture=\"amd64\"/processorArchitecture=\"amd64\"/g' "
                f"'{self.xml_path}' > '{temp_path}'",
                shell=True,
            )

            user_xml = (
                "            <UserAccounts>\n"
                "                <LocalAccounts>\n"
                "                    <LocalAccount wcm:action=\"add\">\n"
                "                        <Description>Local Administrator</Description>\n"
                f"                        <DisplayName>{username}</DisplayName>\n"
                "                        <Group>Administrators</Group>\n"
                f"                        <Name>{username}</Name>\n"
                "                        <Password>\n"
                "                            <Value></Value>\n"
                "                            <PlainText>true</PlainText>\n"
                "                        </Password>\n"
                "                    </LocalAccount>\n"
                "                </LocalAccounts>\n"
                "            </UserAccounts>"
            )

            with open(temp_path, "r", encoding="utf-8") as f:
                c = f.read()
            c = c.replace("<!-- USER_ACCOUNTS_PLACEHOLDER -->", user_xml)
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(c)

            # Check valid XML parse
            tree = ET.parse(temp_path)
            self.assertIsNotNone(tree.getroot())

            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn(f"<Name>{username}</Name>", content)
            self.assertNotIn("<AutoLogon>", content)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()

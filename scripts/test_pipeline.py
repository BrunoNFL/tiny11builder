#!/usr/bin/env python3
"""
test_pipeline.py - Comprehensive verification of tiny11builder pipeline components.
Tests dummy WIM creation, hive extraction, modification, WIM in-place updating, and xorriso ISO creation.
"""

import os
import shutil
import subprocess
import tempfile
import unittest


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="tiny11_pipe_")
        self.sample_hive = "/opt/homebrew/share/hivex/test/large"
        if not os.path.exists(self.sample_hive):
            self.skipTest(f"Sample hive not found at {self.sample_hive}")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_full_pipeline(self):
        # 1. Create dummy install root
        install_root = os.path.join(self.td, "install_root")
        os.makedirs(os.path.join(install_root, "Windows/System32/config"), exist_ok=True)
        os.makedirs(os.path.join(install_root, "Users/Default"), exist_ok=True)
        os.makedirs(os.path.join(install_root, "Program Files (x86)/Microsoft/Edge"), exist_ok=True)
        os.makedirs(os.path.join(install_root, "Program Files (x86)/Microsoft/EdgeUpdate"), exist_ok=True)
        os.makedirs(os.path.join(install_root, "Program Files (x86)/Microsoft/EdgeCore"), exist_ok=True)
        os.makedirs(os.path.join(install_root, "Windows/System32/Microsoft-Edge-Webview"), exist_ok=True)
        os.makedirs(
            os.path.join(install_root, "Windows/System32/Tasks/Microsoft/Windows/Application Experience"),
            exist_ok=True,
        )

        with open(os.path.join(install_root, "Windows/System32/OneDriveSetup.exe"), "w") as f:
            f.write("dummy onedrive")
        with open(
            os.path.join(
                install_root,
                "Windows/System32/Tasks/Microsoft/Windows/Application Experience/Microsoft Compatibility Appraiser",
            ),
            "w",
        ) as f:
            f.write("dummy task")

        # Copy sample hives
        shutil.copyfile(self.sample_hive, os.path.join(install_root, "Windows/System32/config/default"))
        shutil.copyfile(self.sample_hive, os.path.join(install_root, "Users/Default/ntuser.dat"))
        shutil.copyfile(self.sample_hive, os.path.join(install_root, "Windows/System32/config/SYSTEM"))
        shutil.copyfile(self.sample_hive, os.path.join(install_root, "Windows/System32/config/SOFTWARE"))

        # 2. Capture install.wim using wimlib-imagex
        wim_path = os.path.join(self.td, "install.wim")
        subprocess.check_call(
            ["wimlib-imagex", "capture", install_root, wim_path, "Windows 11 Pro", "Windows 11 Pro"]
        )

        # 3. Extract hives
        hives_out = os.path.join(self.td, "hives_out")
        os.makedirs(hives_out, exist_ok=True)
        subprocess.check_call([
            "wimlib-imagex", "extract", wim_path, "1",
            "/Windows/System32/config/default",
            "/Users/Default/ntuser.dat",
            "/Windows/System32/config/SOFTWARE",
            "/Windows/System32/config/SYSTEM",
            f"--dest-dir={hives_out}", "--nullglob"
        ])

        # 4. Modify hives using scripts/modify_registry.py
        subprocess.check_call(["python3", "scripts/modify_registry.py", "--hive-dir", hives_out, "--target", "install"])

        # 5. In-place update WIM
        cmd_file = os.path.join(self.td, "cmd.txt")
        with open(cmd_file, "w") as f:
            f.write(f"""delete --force --recursive "/Program Files (x86)/Microsoft/Edge"
delete --force --recursive "/Program Files (x86)/Microsoft/EdgeUpdate"
delete --force --recursive "/Program Files (x86)/Microsoft/EdgeCore"
delete --force --recursive "/Windows/System32/Microsoft-Edge-Webview"
delete --force "/Windows/System32/OneDriveSetup.exe"
delete --force "/Windows/System32/Tasks/Microsoft/Windows/Application Experience/Microsoft Compatibility Appraiser"
add "{hives_out}/default" /Windows/System32/config/default
add "{hives_out}/ntuser.dat" /Users/Default/ntuser.dat
add "{hives_out}/SOFTWARE" /Windows/System32/config/SOFTWARE
add "{hives_out}/SYSTEM" /Windows/System32/config/SYSTEM
add "autounattend.xml" /Windows/System32/Sysprep/autounattend.xml
add "scripts/SetupComplete.cmd" /Windows/Setup/Scripts/SetupComplete.cmd
add "scripts/tiny11-debloat.ps1" /Windows/Setup/Scripts/tiny11-debloat.ps1
""")
        with open(cmd_file, "rb") as cf:
            subprocess.check_call(["wimlib-imagex", "update", wim_path, "1"], stdin=cf)

        # Verify deletions
        dir_out = subprocess.check_output(
            ["wimlib-imagex", "dir", wim_path, "1", "--path=/Windows/System32"],
            text=True,
        )
        self.assertNotIn("OneDriveSetup.exe", dir_out)

        # 6. Test ISO mastering with xorriso
        iso_tree = os.path.join(self.td, "iso_tree")
        os.makedirs(os.path.join(iso_tree, "boot"), exist_ok=True)
        os.makedirs(os.path.join(iso_tree, "efi/microsoft/boot"), exist_ok=True)
        os.makedirs(os.path.join(iso_tree, "sources"), exist_ok=True)
        shutil.copyfile(wim_path, os.path.join(iso_tree, "sources/install.wim"))
        with open(os.path.join(iso_tree, "boot/etfsboot.com"), "wb") as f:
            f.write(b"BOOT" * 512)
        with open(os.path.join(iso_tree, "efi/microsoft/boot/efisys.bin"), "wb") as f:
            f.write(b"EFIB" * 512)

        out_iso = os.path.join(self.td, "test.iso")
        subprocess.check_call([
            "xorriso", "-as", "mkisofs",
            "-iso-level", "3",
            "-allow-lowercase",
            "-relaxed-filenames",
            "-J", "-joliet-long",
            "-volid", "TINY11",
            "-b", "boot/etfsboot.com",
            "-no-emul-boot", "-boot-load-size", "8",
            "-eltorito-alt-boot",
            "-e", "efi/microsoft/boot/efisys.bin",
            "-no-emul-boot",
            "-isohybrid-gpt-basdat",
            "-o", out_iso,
            iso_tree
        ])

        report = subprocess.check_output(["xorriso", "-indev", out_iso, "-report_el_torito", "plain"], text=True)
        self.assertIn("El Torito catalog", report)
        self.assertIn("BIOS", report)
        self.assertIn("UEFI", report)
        self.assertIn("/boot/etfsboot.com", report)
        self.assertIn("/efi/microsoft/boot/efisys.bin", report)


if __name__ == "__main__":
    unittest.main()

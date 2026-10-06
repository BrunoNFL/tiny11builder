#!/usr/bin/env python3
"""
modify_registry.py - Offline Windows Registry editor for tiny11builder on macOS / Linux.
Uses libhivex via ctypes to safely add, modify, and delete keys and values without mounting.
"""

import argparse
import ctypes
import ctypes.util
import os
import struct
import sys

# Hivex constants
HIVEX_OPEN_WRITE = 4

# Windows Registry types
REG_NONE = 0
REG_SZ = 1
REG_EXPAND_SZ = 2
REG_BINARY = 3
REG_DWORD = 4
REG_DWORD_BIG_ENDIAN = 5
REG_LINK = 6
REG_MULTI_SZ = 7
REG_QWORD = 11


class HiveSetValue(ctypes.Structure):
    _fields_ = [
        ("key", ctypes.c_char_p),
        ("t", ctypes.c_int),
        ("len", ctypes.c_size_t),
        ("value", ctypes.c_char_p),
    ]


class HivexLib:
    def __init__(self, lib_path=None):
        if not lib_path:
            lib_path = self._find_library()
        if not lib_path or not os.path.exists(lib_path):
            raise RuntimeError(
                f"Could not find libhivex library. Install with: brew install hivex (macOS) or apt install libhivex0 (Linux)."
            )
        self.lib = ctypes.CDLL(lib_path)
        self._setup_bindings()

    @staticmethod
    def _find_library():
        candidates = [
            "/opt/homebrew/lib/libhivex.dylib",
            "/usr/local/lib/libhivex.dylib",
            "/usr/lib/libhivex.dylib",
            "/usr/lib/x86_64-linux-gnu/libhivex.so.0",
            "/usr/lib/aarch64-linux-gnu/libhivex.so.0",
            "/usr/lib/libhivex.so.0",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        found = ctypes.util.find_library("hivex")
        if found:
            return found
        return None

    def _setup_bindings(self):
        self.lib.hivex_open.argtypes = [ctypes.c_char_p, ctypes.c_int]
        self.lib.hivex_open.restype = ctypes.c_void_p

        self.lib.hivex_close.argtypes = [ctypes.c_void_p]
        self.lib.hivex_close.restype = ctypes.c_int

        self.lib.hivex_commit.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self.lib.hivex_commit.restype = ctypes.c_int

        self.lib.hivex_root.argtypes = [ctypes.c_void_p]
        self.lib.hivex_root.restype = ctypes.c_size_t

        self.lib.hivex_node_get_child.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p]
        self.lib.hivex_node_get_child.restype = ctypes.c_size_t

        self.lib.hivex_node_add_child.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p]
        self.lib.hivex_node_add_child.restype = ctypes.c_size_t

        self.lib.hivex_node_delete_child.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        self.lib.hivex_node_delete_child.restype = ctypes.c_int

        self.lib.hivex_node_set_value.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(HiveSetValue),
            ctypes.c_int,
        ]
        self.lib.hivex_node_set_value.restype = ctypes.c_int


class HiveEditor:
    def __init__(self, hive_path, hivex_lib):
        self.hive_path = hive_path
        self.hlib = hivex_lib
        if not os.path.exists(hive_path):
            raise FileNotFoundError(f"Hive file not found: {hive_path}")
        self.handle = self.hlib.lib.hivex_open(hive_path.encode("utf-8"), HIVEX_OPEN_WRITE)
        if not self.handle:
            raise RuntimeError(f"Failed to open hive: {hive_path}")
        self.root = self.hlib.lib.hivex_root(self.handle)
        if not self.root:
            raise RuntimeError(f"Failed to get root node for hive: {hive_path}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.handle:
            if exc_type is None:
                res = self.hlib.lib.hivex_commit(self.handle, None, 0)
                if res != 0:
                    print(f"Warning: Failed to commit hive {self.hive_path}", file=sys.stderr)
            self.hlib.lib.hivex_close(self.handle)
            self.handle = None

    def get_or_create_key(self, path):
        """Navigate to or create a key path like 'Control Panel/UnsupportedHardwareNotificationCache'"""
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        curr = self.root
        for part in parts:
            part_bytes = part.encode("utf-8")
            child = self.hlib.lib.hivex_node_get_child(self.handle, curr, part_bytes)
            if not child:
                child = self.hlib.lib.hivex_node_add_child(self.handle, curr, part_bytes)
                if not child:
                    raise RuntimeError(f"Failed to create registry subkey: {part} under node {curr}")
            curr = child
        return curr

    def get_key(self, path):
        """Navigate to a key path if it exists, otherwise return None"""
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        curr = self.root
        for part in parts:
            part_bytes = part.encode("utf-8")
            child = self.hlib.lib.hivex_node_get_child(self.handle, curr, part_bytes)
            if not child:
                return None
            curr = child
        return curr

    def set_dword(self, path, name, value):
        node = self.get_or_create_key(path)
        data = struct.pack("<I", int(value))
        sv = HiveSetValue(key=name.encode("utf-8"), t=REG_DWORD, len=len(data), value=data)
        res = self.hlib.lib.hivex_node_set_value(self.handle, node, ctypes.byref(sv), 0)
        if res != 0:
            raise RuntimeError(f"Failed to set DWORD {name}={value} at {path}")
        print(f"  Set DWORD: {path}\\{name} = {value}")

    def set_string(self, path, name, value):
        node = self.get_or_create_key(path)
        # Windows Registry strings in hives are UTF-16LE with null terminator
        data = value.encode("utf-16le") + b"\x00\x00"
        sv = HiveSetValue(key=name.encode("utf-8"), t=REG_SZ, len=len(data), value=data)
        res = self.hlib.lib.hivex_node_set_value(self.handle, node, ctypes.byref(sv), 0)
        if res != 0:
            raise RuntimeError(f"Failed to set STRING {name} at {path}")
        print(f"  Set STRING: {path}\\{name} = {value}")

    def delete_key(self, path):
        node = self.get_key(path)
        if not node:
            # Already nonexistent
            return
        res = self.hlib.lib.hivex_node_delete_child(self.handle, node)
        if res == 0:
            print(f"  Deleted key: {path}")
        else:
            print(f"  Warning: Failed to delete key {path}")


def apply_default_tweaks(hive_path, hlib):
    print(f"Applying tweaks to DEFAULT hive: {hive_path}")
    with HiveEditor(hive_path, hlib) as h:
        h.set_dword("Control Panel\\UnsupportedHardwareNotificationCache", "SV1", 0)
        h.set_dword("Control Panel\\UnsupportedHardwareNotificationCache", "SV2", 0)


def apply_ntuser_tweaks(hive_path, hlib):
    print(f"Applying tweaks to NTUSER hive: {hive_path}")
    with HiveEditor(hive_path, hlib) as h:
        # Unsupported hardware notifications
        h.set_dword("Control Panel\\UnsupportedHardwareNotificationCache", "SV1", 0)
        h.set_dword("Control Panel\\UnsupportedHardwareNotificationCache", "SV2", 0)

        # Content Delivery Manager / Sponsored apps
        cdm = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager"
        h.set_dword(cdm, "OemPreInstalledAppsEnabled", 0)
        h.set_dword(cdm, "PreInstalledAppsEnabled", 0)
        h.set_dword(cdm, "SilentInstalledAppsEnabled", 0)
        h.set_dword(cdm, "ContentDeliveryAllowed", 0)
        h.set_dword(cdm, "FeatureManagementEnabled", 0)
        h.set_dword(cdm, "PreInstalledAppsEverEnabled", 0)
        h.set_dword(cdm, "SoftLandingEnabled", 0)
        h.set_dword(cdm, "SubscribedContentEnabled", 0)
        h.set_dword(cdm, "SubscribedContent-310093Enabled", 0)
        h.set_dword(cdm, "SubscribedContent-338388Enabled", 0)
        h.set_dword(cdm, "SubscribedContent-338389Enabled", 0)
        h.set_dword(cdm, "SubscribedContent-338393Enabled", 0)
        h.set_dword(cdm, "SubscribedContent-353694Enabled", 0)
        h.set_dword(cdm, "SubscribedContent-353696Enabled", 0)
        h.set_dword(cdm, "SystemPaneSuggestionsEnabled", 0)
        h.delete_key(f"{cdm}\\Subscriptions")
        h.delete_key(f"{cdm}\\SuggestedApps")

        # Chat icon / Taskbar
        h.set_dword("SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "TaskbarMn", 0)

        # Telemetry & Advertising & Privacy
        h.set_dword("Software\\Microsoft\\Windows\\CurrentVersion\\AdvertisingInfo", "Enabled", 0)
        h.set_dword("Software\\Microsoft\\Windows\\CurrentVersion\\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0)
        h.set_dword("Software\\Microsoft\\Speech_OneCore\\Settings\\OnlineSpeechPrivacy", "HasAccepted", 0)
        h.set_dword("Software\\Microsoft\\Input\\TIPC", "Enabled", 0)
        h.set_dword("Software\\Microsoft\\InputPersonalization", "RestrictImplicitInkCollection", 1)
        h.set_dword("Software\\Microsoft\\InputPersonalization", "RestrictImplicitTextCollection", 1)
        h.set_dword("Software\\Microsoft\\InputPersonalization\\TrainedDataStore", "HarvestContacts", 0)
        h.set_dword("Software\\Microsoft\\Personalization\\Settings", "AcceptedPrivacyPolicy", 0)


def apply_system_tweaks(hive_path, hlib):
    print(f"Applying tweaks to SYSTEM hive: {hive_path}")
    with HiveEditor(hive_path, hlib) as h:
        # Hardware bypass checks
        lab_config = "Setup\\LabConfig"
        h.set_dword(lab_config, "BypassCPUCheck", 1)
        h.set_dword(lab_config, "BypassRAMCheck", 1)
        h.set_dword(lab_config, "BypassSecureBootCheck", 1)
        h.set_dword(lab_config, "BypassStorageCheck", 1)
        h.set_dword(lab_config, "BypassTPMCheck", 1)

        # MoSetup bypass
        h.set_dword("Setup\\MoSetup", "AllowUpgradesWithUnsupportedTPMOrCPU", 1)

        # BitLocker device encryption disable
        h.set_dword("ControlSet001\\Control\\BitLocker", "PreventDeviceEncryption", 1)

        # Telemetry service disable
        h.set_dword("ControlSet001\\Services\\dmwappushservice", "Start", 4)


def apply_software_tweaks(hive_path, hlib):
    print(f"Applying tweaks to SOFTWARE hive: {hive_path}")
    with HiveEditor(hive_path, hlib) as h:
        # Cloud content & sponsored apps
        h.set_dword("Policies\\Microsoft\\Windows\\CloudContent", "DisableWindowsConsumerFeatures", 1)
        h.set_dword("Policies\\Microsoft\\Windows\\CloudContent", "DisableConsumerAccountStateContent", 1)
        h.set_dword("Policies\\Microsoft\\Windows\\CloudContent", "DisableCloudOptimizedContent", 1)
        h.set_string("Microsoft\\PolicyManager\\current\\device\\Start", "ConfigureStartPins", '{"pinnedList": [{}]}')
        h.set_dword("Policies\\Microsoft\\PushToInstall", "DisablePushToInstall", 1)
        h.set_dword("Policies\\Microsoft\\MRT", "DontOfferThroughWUAU", 1)

        # Local account on OOBE
        h.set_dword("Microsoft\\Windows\\CurrentVersion\\OOBE", "BypassNRO", 1)

        # Reserved storage disable
        h.set_dword("Microsoft\\Windows\\CurrentVersion\\ReserveManager", "ShippedWithReserves", 0)

        # Chat icon policy
        h.set_dword("Policies\\Microsoft\\Windows\\Windows Chat", "ChatIcon", 3)

        # Remove Edge uninstall registry entries
        h.delete_key("WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Microsoft Edge")
        h.delete_key("WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Microsoft Edge Update")

        # OneDrive sync disable
        h.set_dword("Policies\\Microsoft\\Windows\\OneDrive", "DisableFileSyncNGSC", 1)

        # Telemetry policy
        h.set_dword("Policies\\Microsoft\\Windows\\DataCollection", "AllowTelemetry", 0)

        # Prevent DevHome and Outlook background updates
        h.set_dword("Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Orchestrator\\UScheduler_Oobe\\OutlookUpdate", "workCompleted", 1)
        h.set_dword("Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Orchestrator\\UScheduler\\OutlookUpdate", "workCompleted", 1)
        h.set_dword("Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Orchestrator\\UScheduler\\DevHomeUpdate", "workCompleted", 1)
        h.delete_key("Microsoft\\WindowsUpdate\\Orchestrator\\UScheduler_Oobe\\OutlookUpdate")
        h.delete_key("Microsoft\\WindowsUpdate\\Orchestrator\\UScheduler_Oobe\\DevHomeUpdate")

        # Copilot disable
        h.set_dword("Policies\\Microsoft\\Windows\\WindowsCopilot", "TurnOffWindowsCopilot", 1)
        h.set_dword("Policies\\Microsoft\\Edge", "HubsSidebarEnabled", 0)
        h.set_dword("Policies\\Microsoft\\Windows\\Explorer", "DisableSearchBoxSuggestions", 1)

        # Teams disable
        h.set_dword("Policies\\Microsoft\\Teams", "DisableInstallation", 1)

        # Prevent New Outlook run
        h.set_dword("Policies\\Microsoft\\Windows\\Windows Mail", "PreventRun", 1)


def find_hive_file(hive_dir, name):
    """Find a hive file directly in hive_dir or recursively (case-insensitive)."""
    direct = os.path.join(hive_dir, name)
    if os.path.exists(direct):
        return direct
    name_lower = name.lower()
    for root, _, files in os.walk(hive_dir):
        for f in files:
            if f.lower() == name_lower:
                return os.path.join(root, f)
    return None


def apply_boot_tweaks(hive_dir, hlib):
    """Applies bypasses to boot.wim (index 2) extracted hives."""
    print(f"Applying tweaks to boot.wim hives in {hive_dir}...")
    default_path = find_hive_file(hive_dir, "default")
    ntuser_path = find_hive_file(hive_dir, "ntuser.dat")
    system_path = find_hive_file(hive_dir, "SYSTEM")

    if default_path and os.path.exists(default_path):
        with HiveEditor(default_path, hlib) as h:
            h.set_dword("Control Panel\\UnsupportedHardwareNotificationCache", "SV1", 0)
            h.set_dword("Control Panel\\UnsupportedHardwareNotificationCache", "SV2", 0)

    if ntuser_path and os.path.exists(ntuser_path):
        with HiveEditor(ntuser_path, hlib) as h:
            h.set_dword("Control Panel\\UnsupportedHardwareNotificationCache", "SV1", 0)
            h.set_dword("Control Panel\\UnsupportedHardwareNotificationCache", "SV2", 0)

    if system_path and os.path.exists(system_path):
        with HiveEditor(system_path, hlib) as h:
            lab_config = "Setup\\LabConfig"
            h.set_dword(lab_config, "BypassCPUCheck", 1)
            h.set_dword(lab_config, "BypassRAMCheck", 1)
            h.set_dword(lab_config, "BypassSecureBootCheck", 1)
            h.set_dword(lab_config, "BypassStorageCheck", 1)
            h.set_dword(lab_config, "BypassTPMCheck", 1)
            h.set_dword("Setup\\MoSetup", "AllowUpgradesWithUnsupportedTPMOrCPU", 1)


def apply_install_tweaks(hive_dir, hlib):
    """Applies all tiny11 tweaks to install.wim extracted hives."""
    print(f"Applying tweaks to install.wim hives in {hive_dir}...")
    default_path = find_hive_file(hive_dir, "default")
    ntuser_path = find_hive_file(hive_dir, "ntuser.dat")
    system_path = find_hive_file(hive_dir, "SYSTEM")
    software_path = find_hive_file(hive_dir, "SOFTWARE")

    if default_path and os.path.exists(default_path):
        apply_default_tweaks(default_path, hlib)
    else:
        print(f"Warning: default hive not found in {hive_dir}")

    if ntuser_path and os.path.exists(ntuser_path):
        apply_ntuser_tweaks(ntuser_path, hlib)
    else:
        print(f"Warning: ntuser.dat hive not found in {hive_dir}")

    if system_path and os.path.exists(system_path):
        apply_system_tweaks(system_path, hlib)
    else:
        print(f"Warning: SYSTEM hive not found in {hive_dir}")

    if software_path and os.path.exists(software_path):
        apply_software_tweaks(software_path, hlib)
    else:
        print(f"Warning: SOFTWARE hive not found in {hive_dir}")


def main():
    parser = argparse.ArgumentParser(description="Modify Windows Registry hives offline via hivex.")
    parser.add_argument("--hive-dir", required=True, help="Directory containing extracted hives (SYSTEM, SOFTWARE, etc.)")
    parser.add_argument("--target", required=True, choices=["install", "boot"], help="Target image type: install or boot")
    parser.add_argument("--hivex-lib", default=None, help="Optional path to libhivex.dylib / libhivex.so")

    args = parser.parse_args()
    hlib = HivexLib(args.hivex_lib)

    if args.target == "install":
        apply_install_tweaks(args.hive_dir, hlib)
    elif args.target == "boot":
        apply_boot_tweaks(args.hive_dir, hlib)

    print(f"Successfully modified {args.target} registry hives!")


if __name__ == "__main__":
    main()

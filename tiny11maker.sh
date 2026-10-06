#!/usr/bin/env bash
# ==============================================================================
# tiny11maker.sh
# macOS and Linux port of tiny11builder
# Builds a trimmed-down, bloatware-free Windows 11 image without requiring Windows.
#
# Requirements:
#   - wimlib (brew install wimlib)
#   - hivex (brew install hivex)
#   - xorriso (brew install xorriso)
#   - python3 (standard on macOS)
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$(which python3 || echo "python3")"

# Default settings
ISO_PATH=""
SCRATCH_DIR=""
OUTPUT_ISO=""
WIMLIB_BIN=""
SELECTED_INDEX=""
COMPRESS_MODE="LZMS" # Default recovery compression
KEEP_SCRATCH=0
MOUNTED_VOLUME=""
AUTO_USER=0
USERNAME_VAL=""
SKIP_AUTOLOGON=0

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "=========================================================="
    echo "         tiny11 builder for macOS / Linux                 "
    echo "=========================================================="
    echo -e "${NC}"
}

print_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -i, --iso <path>         Path to the Windows 11 ISO file"
    echo "  -s, --scratch <dir>      Scratch workspace directory (default: ./scratch_tiny11)"
    echo "  -o, --output <path>      Output ISO file path (default: ./tiny11.iso)"
    echo "  -n, --index <number>     Windows image SKU index to export (optional, prompts if omitted)"
    echo "  -w, --wimlib <path>          Custom path to wimlib-imagex executable"
    echo "  -u, --username <name>        Create local admin account and skip user creation (default: Tiny11)"
    echo "      --skip-user-creation     Skip manual user creation in OOBE and auto-create local account"
    echo "      --auto-user [name]       Alias for --skip-user-creation (optional account name)"
    echo "      --skip-autologon         Do not auto-logon to desktop when local account is created"
    echo "      --fast                   Use LZX compression instead of LZMS (faster export, slightly larger ISO)"
    echo "      --keep-scratch           Do not delete scratch directory after completion"
    echo "      --check-deps             Verify installed prerequisites and exit"
    echo "  -h, --help               Display this help message"
    echo ""
    echo "Example:"
    echo "  $0 -i ~/Downloads/Win11_24H2_English_x64.iso"
}

cleanup() {
    local exit_code=$?
    if [[ -n "$MOUNTED_VOLUME" && -d "$MOUNTED_VOLUME" ]]; then
        echo -e "${YELLOW}Detaching mounted ISO volume: $MOUNTED_VOLUME...${NC}"
        if [[ "$(uname)" == "Darwin" ]]; then
            hdiutil detach "$MOUNTED_VOLUME" -force >/dev/null 2>&1 || true
        else
            sudo umount "$MOUNTED_VOLUME" >/dev/null 2>&1 || true
        fi
    fi

    if [[ $KEEP_SCRATCH -eq 0 && -n "$SCRATCH_DIR" && -d "$SCRATCH_DIR" ]]; then
        if [[ $exit_code -eq 0 ]]; then
            echo -e "${BLUE}Cleaning up scratch directory...${NC}"
            rm -rf "$SCRATCH_DIR" || true
        else
            echo -e "${YELLOW}Scratch directory preserved for debugging: $SCRATCH_DIR${NC}"
        fi
    fi
}

trap cleanup EXIT INT TERM

check_dependencies() {
    local missing=0

    echo -e "${BLUE}Checking dependencies...${NC}"

    # 1. Python 3
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        echo -e "  [${RED}MISSING${NC}] python3"
        missing=1
    else
        echo -e "  [${GREEN}OK${NC}] python3 ($($PYTHON_BIN --version))"
    fi

    # 2. wimlib-imagex
    if [[ -z "$WIMLIB_BIN" ]]; then
        if command -v wimlib-imagex >/dev/null 2>&1; then
            WIMLIB_BIN="$(command -v wimlib-imagex)"
        elif [[ -x "/opt/homebrew/bin/wimlib-imagex" ]]; then
            WIMLIB_BIN="/opt/homebrew/bin/wimlib-imagex"
        elif [[ -x "/usr/local/bin/wimlib-imagex" ]]; then
            WIMLIB_BIN="/usr/local/bin/wimlib-imagex"
        elif [[ -x "$HOME/Downloads/wimlib-1.14.5/programs/wimlib-imagex" ]]; then
            WIMLIB_BIN="$HOME/Downloads/wimlib-1.14.5/programs/wimlib-imagex"
        fi
    fi

    if [[ -n "$WIMLIB_BIN" && -x "$WIMLIB_BIN" ]]; then
        local wim_ver
        wim_ver=$("$WIMLIB_BIN" --version 2>&1 | head -n 1 || echo "")
        echo -e "  [${GREEN}OK${NC}] wimlib-imagex ($wim_ver) at $WIMLIB_BIN"
    else
        echo -e "  [${RED}MISSING${NC}] wimlib-imagex. Install via Homebrew: ${BOLD}brew install wimlib${NC}"
        missing=1
    fi

    # 3. hivex
    if "$PYTHON_BIN" -c "import ctypes, ctypes.util, os; [exit(0) for p in ['/opt/homebrew/lib/libhivex.dylib', '/usr/local/lib/libhivex.dylib', '/usr/lib/libhivex.dylib', ctypes.util.find_library('hivex')] if p and os.path.exists(p)]; exit(1)" >/dev/null 2>&1; then
        echo -e "  [${GREEN}OK${NC}] libhivex (Registry hive library)"
    else
        echo -e "  [${RED}MISSING${NC}] libhivex. Install via Homebrew: ${BOLD}brew install hivex${NC}"
        missing=1
    fi

    # 4. xorriso
    if command -v xorriso >/dev/null 2>&1; then
        local xor_ver
        xor_ver=$(xorriso -version 2>&1 | head -n 1 || echo "")
        echo -e "  [${GREEN}OK${NC}] xorriso ($xor_ver)"
    else
        echo -e "  [${RED}MISSING${NC}] xorriso. Install via Homebrew: ${BOLD}brew install xorriso${NC}"
        missing=1
    fi

    # 5. OS tools
    if [[ "$(uname)" == "Darwin" ]]; then
        if ! command -v hdiutil >/dev/null 2>&1; then
            echo -e "  [${RED}MISSING${NC}] hdiutil (required on macOS)"
            missing=1
        fi
    fi

    echo ""
    if [[ $missing -ne 0 ]]; then
        echo -e "${RED}${BOLD}Error: Missing prerequisites!${NC}"
        if [[ "$(uname)" == "Darwin" ]]; then
            echo "You can install all missing dependencies on macOS with:"
            echo -e "  ${BOLD}brew install wimlib hivex xorriso${NC}"
        else
            echo "Install wimtools, libhivex, and xorriso using your Linux package manager."
        fi
        exit 1
    fi
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--iso)
            ISO_PATH="$2"
            shift 2
            ;;
        -s|--scratch)
            SCRATCH_DIR="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_ISO="$2"
            shift 2
            ;;
        -n|--index)
            SELECTED_INDEX="$2"
            shift 2
            ;;
        -w|--wimlib)
            WIMLIB_BIN="$2"
            shift 2
            ;;
        -u|--username)
            AUTO_USER=1
            USERNAME_VAL="$2"
            shift 2
            ;;
        --skip-user-creation)
            AUTO_USER=1
            if [[ -n "$2" && "$2" != -* ]]; then
                USERNAME_VAL="$2"
                shift 2
            else
                shift 1
            fi
            ;;
        --auto-user)
            AUTO_USER=1
            if [[ -n "$2" && "$2" != -* ]]; then
                USERNAME_VAL="$2"
                shift 2
            else
                shift 1
            fi
            ;;
        --skip-autologon)
            SKIP_AUTOLOGON=1
            shift
            ;;
        --fast)
            COMPRESS_MODE="LZX"
            shift
            ;;
        --keep-scratch)
            KEEP_SCRATCH=1
            shift
            ;;
        --check-deps)
            print_banner
            check_dependencies
            echo -e "${GREEN}All dependencies are satisfied!${NC}"
            exit 0
            ;;
        -h|--help)
            print_banner
            print_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            print_usage
            exit 1
            ;;
    esac
done

print_banner
check_dependencies

# Prompt for ISO path if not provided
if [[ -z "$ISO_PATH" ]]; then
    read -rp "Please enter the path to the Windows 11 ISO: " ISO_PATH
    # Trim quotes
    ISO_PATH="${ISO_PATH%\"}"
    ISO_PATH="${ISO_PATH#\"}"
    ISO_PATH="${ISO_PATH%\'}"
    ISO_PATH="${ISO_PATH#\'}"
fi

if [[ ! -f "$ISO_PATH" ]]; then
    echo -e "${RED}Error: ISO file not found at: $ISO_PATH${NC}"
    exit 1
fi

# Set defaults for scratch and output
if [[ -z "$SCRATCH_DIR" ]]; then
    SCRATCH_DIR="$SCRIPT_DIR/scratch_tiny11"
fi
if [[ -z "$OUTPUT_ISO" ]]; then
    OUTPUT_ISO="$SCRIPT_DIR/tiny11.iso"
fi

# Ensure scratch directory is ready
mkdir -p "$SCRATCH_DIR/tiny11"

# ------------------------------------------------------------------------------
# STEP 1: Mount ISO & Copy Contents
# ------------------------------------------------------------------------------
echo -e "${BLUE}${BOLD}[Step 1/8] Mounting Windows 11 ISO...${NC}"
if [[ "$(uname)" == "Darwin" ]]; then
    ATTACH_OUTPUT=$(hdiutil attach -nobrowse -readonly "$ISO_PATH" 2>&1)
    MOUNTED_VOLUME=$(echo "$ATTACH_OUTPUT" | grep -E '/Volumes/' | tail -n 1 | awk -F'/Volumes/' '{print "/Volumes/" $2}' | sed 's/[[:space:]]*$//')
    if [[ -z "$MOUNTED_VOLUME" || ! -d "$MOUNTED_VOLUME" ]]; then
        echo -e "${RED}Failed to mount ISO with hdiutil. Output:${NC}\n$ATTACH_OUTPUT"
        exit 1
    fi
    echo -e "Mounted at: ${CYAN}$MOUNTED_VOLUME${NC}"
    echo -e "${BLUE}Copying files to scratch directory... (This may take a minute)${NC}"
    cp -R "$MOUNTED_VOLUME/"* "$SCRATCH_DIR/tiny11/"
    chmod -R u+w "$SCRATCH_DIR/tiny11"
    hdiutil detach "$MOUNTED_VOLUME" -force >/dev/null 2>&1 || true
    MOUNTED_VOLUME=""
else
    LINUX_MNT="$SCRATCH_DIR/mnt_iso"
    mkdir -p "$LINUX_MNT"
    sudo mount -o loop,ro "$ISO_PATH" "$LINUX_MNT"
    MOUNTED_VOLUME="$LINUX_MNT"
    echo -e "Mounted at: ${CYAN}$LINUX_MNT${NC}"
    echo -e "${BLUE}Copying files to scratch directory...${NC}"
    cp -R "$LINUX_MNT/"* "$SCRATCH_DIR/tiny11/"
    chmod -R u+w "$SCRATCH_DIR/tiny11"
    sudo umount "$LINUX_MNT" || true
    rmdir "$LINUX_MNT" || true
    MOUNTED_VOLUME=""
fi
echo -e "${GREEN}ISO files extracted successfully!${NC}"

# ------------------------------------------------------------------------------
# STEP 2: Detect Image Format (install.wim vs install.esd vs install.swm)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 2/8] Inspecting Windows image in sources/...${NC}"
SOURCES_DIR="$SCRATCH_DIR/tiny11/sources"
INSTALL_WIM="$SOURCES_DIR/install.wim"
INSTALL_ESD="$SOURCES_DIR/install.esd"

if [[ ! -f "$INSTALL_WIM" ]]; then
    if [[ -f "$INSTALL_ESD" ]]; then
        echo -e "${YELLOW}Found install.esd (Electronic Software Download).${NC}"
        echo "Listing available editions in install.esd:"
        "$WIMLIB_BIN" info "$INSTALL_ESD" | grep -E "^(Index|Name|Architecture|Description):" || true

        if [[ -z "$SELECTED_INDEX" ]]; then
            read -rp "Please enter the image index to convert: " SELECTED_INDEX
        fi

        echo -e "${BLUE}Converting install.esd to install.wim (Index $SELECTED_INDEX)...${NC}"
        "$WIMLIB_BIN" export "$INSTALL_ESD" "$SELECTED_INDEX" "$INSTALL_WIM" --compress=LZX --check
        rm -f "$INSTALL_ESD"
        SELECTED_INDEX="1" # The exported WIM now contains only that selected image as index 1
    elif compgen -G "$SOURCES_DIR/install*.swm" > /dev/null; then
        echo -e "${YELLOW}Found split WIM (install*.swm). Combining into install.wim...${NC}"
        "$WIMLIB_BIN" join "$INSTALL_WIM" "$SOURCES_DIR/install"*.swm --check
        rm -f "$SOURCES_DIR/install"*.swm
    else
        echo -e "${RED}Error: Neither install.wim, install.esd, nor install.swm was found in sources/.${NC}"
        exit 1
    fi
fi

# ------------------------------------------------------------------------------
# STEP 3: SKU Index Selection & Architecture Detection
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 3/8] Reading image information...${NC}"
IMAGE_COUNT=$("$WIMLIB_BIN" info "$INSTALL_WIM" | grep -E "^Image Count:" | awk '{print $3}')

if [[ "$IMAGE_COUNT" -eq 1 ]]; then
    SELECTED_INDEX="1"
    echo -e "Only one edition present (Index 1). Auto-selected."
elif [[ -z "$SELECTED_INDEX" ]]; then
    echo -e "\nAvailable editions in install.wim:"
    "$WIMLIB_BIN" info "$INSTALL_WIM" | grep -E "^(Index|Name|Architecture):" || true
    echo ""
    read -rp "Please enter the desired image index [1-$IMAGE_COUNT]: " SELECTED_INDEX
fi

# Detect architecture of chosen index
RAW_ARCH=$("$WIMLIB_BIN" info "$INSTALL_WIM" "$SELECTED_INDEX" | grep -E "^Architecture:" | head -n 1 | awk '{print $2}')
case "$RAW_ARCH" in
    x86_64)
        ARCH="amd64"
        ;;
    ARM64|aarch64)
        ARCH="arm64"
        ;;
    x86)
        ARCH="x86"
        ;;
    *)
        ARCH="amd64"
        ;;
esac
echo -e "Target Index: ${CYAN}$SELECTED_INDEX${NC} | Architecture: ${CYAN}$ARCH${NC}"

extract_hives() {
    local wim_file="$1"
    local index="$2"
    local dest_dir="$3"

    mkdir -p "$dest_dir"

    local cfg_list
    cfg_list=$("$WIMLIB_BIN" dir "$wim_file" "$index" --path=/Windows/System32/config 2>/dev/null || true)
    local usr_list
    usr_list=$("$WIMLIB_BIN" dir "$wim_file" "$index" --path=/Users/Default 2>/dev/null || true)

    local extract_args=()

    local def_match
    def_match=$(echo "$cfg_list" | grep -Ei "/Windows/System32/config/default$" | head -n 1 || true)
    if [[ -n "$def_match" ]]; then
        extract_args+=("$def_match")
    fi

    local soft_match
    soft_match=$(echo "$cfg_list" | grep -Ei "/Windows/System32/config/software$" | head -n 1 || true)
    if [[ -n "$soft_match" ]]; then
        extract_args+=("$soft_match")
    fi

    local sys_match
    sys_match=$(echo "$cfg_list" | grep -Ei "/Windows/System32/config/system$" | head -n 1 || true)
    if [[ -n "$sys_match" ]]; then
        extract_args+=("$sys_match")
    fi

    local nt_match
    nt_match=$(echo "$usr_list" | grep -Ei "/Users/Default/ntuser.dat$" | head -n 1 || true)
    if [[ -n "$nt_match" ]]; then
        extract_args+=("$nt_match")
    fi

    if [[ ${#extract_args[@]} -gt 0 ]]; then
        "$WIMLIB_BIN" extract "$wim_file" "$index" "${extract_args[@]}" --dest-dir="$dest_dir" --preserve-dir-structure >/dev/null
    fi
}

# ------------------------------------------------------------------------------
# STEP 4: Modify Registry Hives in install.wim (via hivex)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 4/8] Extracting and modifying offline registry hives...${NC}"
HIVES_INSTALL="$SCRATCH_DIR/hives_install"
mkdir -p "$HIVES_INSTALL"

extract_hives "$INSTALL_WIM" "$SELECTED_INDEX" "$HIVES_INSTALL"

"$PYTHON_BIN" "$SCRIPT_DIR/scripts/modify_registry.py" --hive-dir "$HIVES_INSTALL" --target install

# ------------------------------------------------------------------------------
# STEP 5: Prepare autounattend.xml & Debloat Scripts
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 5/8] Preparing unattended answers and debloater scripts...${NC}"
AUTOUNATTEND_SRC="$SCRIPT_DIR/autounattend.xml"
AUTOUNATTEND_SCRATCH="$SCRATCH_DIR/autounattend.xml"

# Update processorArchitecture dynamically in autounattend.xml (index remains 1 for single-SKU exported image)
sed -e "s/processorArchitecture=\"amd64\"/processorArchitecture=\"$ARCH\"/g" \
    "$AUTOUNATTEND_SRC" > "$AUTOUNATTEND_SCRATCH"

if [[ $AUTO_USER -eq 1 ]]; then
    if [[ -z "$USERNAME_VAL" ]]; then
        USERNAME_VAL="Tiny11"
    fi
    echo -e "Automating local user creation with account: ${CYAN}$USERNAME_VAL${NC}"
    USER_XML="            <UserAccounts>\n                <LocalAccounts>\n                    <LocalAccount wcm:action=\"add\">\n                        <Description>Local Administrator</Description>\n                        <DisplayName>$USERNAME_VAL</DisplayName>\n                        <Group>Administrators</Group>\n                        <Name>$USERNAME_VAL</Name>\n                        <Password>\n                            <Value></Value>\n                            <PlainText>true</PlainText>\n                        </Password>\n                    </LocalAccount>\n                </LocalAccounts>\n            </UserAccounts>"

    if [[ $SKIP_AUTOLOGON -eq 0 ]]; then
        USER_XML="$USER_XML\n            <AutoLogon>\n                <Enabled>true</Enabled>\n                <LogonCount>1</LogonCount>\n                <Username>$USERNAME_VAL</Username>\n                <Password>\n                    <Value></Value>\n                    <PlainText>true</PlainText>\n                </Password>\n            </AutoLogon>"
    fi

    "$PYTHON_BIN" -c "
with open('$AUTOUNATTEND_SCRATCH', 'r', encoding='utf-8') as f:
    c = f.read()
repl = '''$USER_XML'''.replace('\\\\n', '\n')
c = c.replace('<!-- USER_ACCOUNTS_PLACEHOLDER -->', repl)
with open('$AUTOUNATTEND_SCRATCH', 'w', encoding='utf-8') as f:
    f.write(c)
"
else
    # Remove placeholder comment for standard interactive setup
    sed -i.bak '/<!-- USER_ACCOUNTS_PLACEHOLDER -->/d' "$AUTOUNATTEND_SCRATCH" && rm -f "$AUTOUNATTEND_SCRATCH.bak"
fi

# Build WIM update command file
WIM_CMD_FILE="$SCRATCH_DIR/install_wim_commands.txt"
cat <<EOF > "$WIM_CMD_FILE"
delete --force --recursive "/Program Files (x86)/Microsoft/Edge"
delete --force --recursive "/Program Files (x86)/Microsoft/EdgeUpdate"
delete --force --recursive "/Program Files (x86)/Microsoft/EdgeCore"
delete --force --recursive "/Program Files (x86)/Microsoft/EdgeWebView"
delete --force --recursive "/Program Files/Microsoft/Edge"
delete --force --recursive "/Program Files/Microsoft/EdgeUpdate"
delete --force --recursive "/Program Files/Microsoft/EdgeCore"
delete --force --recursive "/Program Files/Microsoft/EdgeWebView"
delete --force --recursive "/Windows/System32/Microsoft-Edge-Webview"
delete --force "/Windows/System32/OneDriveSetup.exe"
delete --force "/Windows/System32/Tasks/Microsoft/Windows/Application Experience/Microsoft Compatibility Appraiser"
delete --force --recursive "/Windows/System32/Tasks/Microsoft/Windows/Customer Experience Improvement Program"
delete --force "/Windows/System32/Tasks/Microsoft/Windows/Application Experience/ProgramDataUpdater"
delete --force "/Windows/System32/Tasks/Microsoft/Windows/Chkdsk/Proxy"
delete --force "/Windows/System32/Tasks/Microsoft/Windows/Windows Error Reporting/QueueReporting"
EOF

# Dynamically add all modified hives found on disk
find "$HIVES_INSTALL" -type f | while read -r hive_file; do
    rel_path="${hive_file#$HIVES_INSTALL}"
    echo "add \"$hive_file\" \"$rel_path\"" >> "$WIM_CMD_FILE"
done

cat <<EOF >> "$WIM_CMD_FILE"
add "$AUTOUNATTEND_SCRATCH" /Windows/System32/Sysprep/autounattend.xml
add "$AUTOUNATTEND_SCRATCH" /Windows/Panther/unattend.xml
add "$SCRIPT_DIR/scripts/SetupComplete.cmd" /Windows/Setup/Scripts/SetupComplete.cmd
add "$SCRIPT_DIR/scripts/tiny11-debloat.ps1" /Windows/Setup/Scripts/tiny11-debloat.ps1
EOF

echo -e "${BLUE}Applying in-place modifications to install.wim...${NC}"
"$WIMLIB_BIN" update "$INSTALL_WIM" "$SELECTED_INDEX" < "$WIM_CMD_FILE" >/dev/null
echo -e "${GREEN}install.wim modifications applied successfully!${NC}"

# ------------------------------------------------------------------------------
# STEP 6: Modify boot.wim (Hardware Requirements Bypass for Setup)
# ------------------------------------------------------------------------------
BOOT_WIM="$SOURCES_DIR/boot.wim"
if [[ -f "$BOOT_WIM" ]]; then
    echo -e "\n${BLUE}${BOLD}[Step 6/8] Modifying boot.wim (setup image requirements bypass)...${NC}"
    HIVES_BOOT="$SCRATCH_DIR/hives_boot"
    mkdir -p "$HIVES_BOOT"

    extract_hives "$BOOT_WIM" 2 "$HIVES_BOOT"

    "$PYTHON_BIN" "$SCRIPT_DIR/scripts/modify_registry.py" --hive-dir "$HIVES_BOOT" --target boot

    BOOT_CMD_FILE="$SCRATCH_DIR/boot_wim_commands.txt"
    > "$BOOT_CMD_FILE"
    find "$HIVES_BOOT" -type f | while read -r hive_file; do
        rel_path="${hive_file#$HIVES_BOOT}"
        echo "add \"$hive_file\" \"$rel_path\"" >> "$BOOT_CMD_FILE"
    done

    "$WIMLIB_BIN" update "$BOOT_WIM" 2 < "$BOOT_CMD_FILE" >/dev/null
    "$WIMLIB_BIN" optimize "$BOOT_WIM" --check >/dev/null 2>&1 || true
    echo -e "${GREEN}boot.wim setup bypasses applied successfully!${NC}"
fi

# ------------------------------------------------------------------------------
# STEP 7: Re-export & Compress install.wim
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 7/8] Re-exporting install.wim with $COMPRESS_MODE compression...${NC}"
EXPORT_WIM="$SCRATCH_DIR/install_export.wim"
"$WIMLIB_BIN" export "$INSTALL_WIM" "$SELECTED_INDEX" "$EXPORT_WIM" --compress="$COMPRESS_MODE" --check
mv "$EXPORT_WIM" "$INSTALL_WIM"
echo -e "${GREEN}Image export and compression complete!${NC}"

# ------------------------------------------------------------------------------
# STEP 8: Create Bootable ISO (via xorriso)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 8/8] Mastering bootable hybrid ISO with xorriso...${NC}"
# Copy autounattend.xml to ISO root
cp "$AUTOUNATTEND_SCRATCH" "$SCRATCH_DIR/tiny11/autounattend.xml"
cp "$AUTOUNATTEND_SCRATCH" "$SCRATCH_DIR/tiny11/AutoUnattend.xml"

ETFS_BOOT="boot/etfsboot.com"
EFI_SYS="efi/microsoft/boot/efisys.bin"

if [[ ! -f "$SCRATCH_DIR/tiny11/$ETFS_BOOT" || ! -f "$SCRATCH_DIR/tiny11/$EFI_SYS" ]]; then
    echo -e "${YELLOW}Warning: Standard El Torito boot files not found at expected paths. Checking EFI...${NC}"
fi

xorriso -as mkisofs \
    -iso-level 3 \
    -allow-lowercase \
    -relaxed-filenames \
    -J -joliet-long \
    -volid "TINY11" \
    -b "$ETFS_BOOT" \
    -no-emul-boot -boot-load-size 8 \
    -eltorito-alt-boot \
    -e "$EFI_SYS" \
    -no-emul-boot \
    -isohybrid-gpt-basdat \
    -o "$OUTPUT_ISO" \
    "$SCRATCH_DIR/tiny11"

echo ""
echo -e "${GREEN}${BOLD}==========================================================${NC}"
echo -e "${GREEN}${BOLD}          Tiny11 ISO successfully created!                ${NC}"
echo -e "${GREEN}${BOLD}==========================================================${NC}"
echo -e "Output ISO : ${CYAN}$OUTPUT_ISO${NC}"
if [[ -f "$OUTPUT_ISO" ]]; then
    ISO_SIZE=$(du -h "$OUTPUT_ISO" | awk '{print $1}')
    echo -e "File Size  : ${CYAN}$ISO_SIZE${NC}"
fi
echo ""
echo "You can now burn this ISO to a USB flash drive or mount it in a VM!"

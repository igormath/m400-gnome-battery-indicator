#!/usr/bin/env bash
#
# install.sh - Automated installer for Delux M400 Battery Monitor & GNOME Extension
#
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT_UUID="delux-battery@igazev.local"
EXT_DEST="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"
BIN_DEST="$HOME/.local/bin"

echo "=== Delux M400 Battery Monitor Installer ==="

# 1. Compile C binary
echo "[1/4] Compiling native C binary..."
gcc -O2 -Wall -Wextra -o "$REPO_DIR/delux-battery" "$REPO_DIR/delux_battery.c"

# 2. Install binary to ~/.local/bin
echo "[2/4] Installing binary to $BIN_DEST..."
mkdir -p "$BIN_DEST"
cp "$REPO_DIR/delux-battery" "$BIN_DEST/delux-battery"
chmod +x "$BIN_DEST/delux-battery"

# 3. Install GNOME Shell extension
echo "[3/4] Installing GNOME Shell extension..."
mkdir -p "$HOME/.local/share/gnome-shell/extensions"
rm -rf "$EXT_DEST"
cp -r "$REPO_DIR/extension" "$EXT_DEST"

# 4. Install udev rule (requires sudo)
echo "[4/4] Verifying udev rules for /dev/hidraw..."
if [ -f "/etc/udev/rules.d/99-delux-mouse.rules" ]; then
    echo " -> udev rule already present in /etc/udev/rules.d/99-delux-mouse.rules"
else
    echo " -> Installing /etc/udev/rules.d/99-delux-mouse.rules (requires sudo)..."
    sudo cp "$REPO_DIR/99-delux-mouse.rules" /etc/udev/rules.d/
    sudo udevadm control --reload-rules && sudo udevadm trigger
fi

echo ""
echo "=== Installation Completed Successfully! ==="
echo "To enable the extension now:"
echo "  gnome-extensions enable $EXT_UUID"
echo ""
echo "If this is the first time you install the extension on this machine, you may need"
echo "to Log out and Log back in for GNOME Shell to index the new directory."

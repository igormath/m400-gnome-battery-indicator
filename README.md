# Delux M400 Mouse Battery Monitor

A complete solution to monitor battery levels and charging status for the **Delux M400** mouse on Linux (Manjaro, Arch, Fedora, Ubuntu, etc.), supporting both **2.4GHz USB Dongle** and **USB-C Wired** connections.

Features:
- 🧩 **GNOME Shell Extension:** Battery percentage and icon directly in the Top Bar with a detailed status popup menu.
- ⚡ **Native C Binary (`delux-battery`):** Ultra-fast, lightweight CLI utility (~17 KB, <70ms, zero external dependencies) outputting JSON or formatted text.
- 🐍 **Python CLI Script (`delux_m400.py`):** Standalone monitoring script with desktop notifications (`notify-send`).

---

## 🧩 GNOME Shell Extension

The extension displays the mouse icon and battery percentage on the top panel, automatically refreshing asynchronously every 60 seconds (without blocking the UI).

### 🖥️ Supported GNOME Shell Versions
- **GNOME Shell 45, 46, 47, 48, 49, and 50+** (Modern ES Modules / GJS).
- Tested and verified on **Manjaro Linux with GNOME Shell 50.4**.

---

### ⚡ Quick Installation (Automated)

Clone the repository and run the install script:

```bash
git clone https://github.com/igormath/delux-battery.git
cd delux-battery
./install.sh
```

The script will:
1. Compile the native C binary `delux-battery`.
2. Install the binary to `~/.local/bin/`.
3. Install the extension to `~/.local/share/gnome-shell/extensions/delux-battery@igazev.local`.
4. Install the udev rule in `/etc/udev/rules.d/` to grant non-root read/write access.
5. Enable the extension in GNOME Shell.

> **First-time installation note:** If this is the first time you are installing the extension on this machine, **Log out and Log back in** to your GNOME session so the shell discovers the new directory. Then ensure it is enabled with:
> ```bash
> gnome-extensions enable delux-battery@igazev.local
> ```

---

### 🛠️ Manual Installation (Step by Step)

If you prefer installing components manually:

#### 1. Install udev rule (Hardware Permissions):
By default on Linux, `/dev/hidraw*` device nodes require `root` permissions. Install the udev rule to allow standard users to communicate with the mouse without `sudo`:

```bash
sudo cp 99-delux-mouse.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```
*(Optional: Unplug and reconnect the 2.4GHz USB dongle if permissions are not applied immediately).*

#### 2. Build and install the C binary:
```bash
make
mkdir -p ~/.local/bin
cp delux-battery ~/.local/bin/
```

#### 3. Install the Extension directory:
```bash
mkdir -p ~/.local/share/gnome-shell/extensions
cp -r extension ~/.local/share/gnome-shell/extensions/delux-battery@igazev.local
```

*(Developer tip: if you want to edit the code directly in your repository without copying files back and forth, create a symbolic link instead):*
```bash
ln -sfn "$(pwd)/extension" ~/.local/share/gnome-shell/extensions/delux-battery@igazev.local
```

#### 4. Enable the Extension:
After logging out and in (or on initial setup):
```bash
gnome-extensions enable delux-battery@igazev.local
```

#### 🔄 Hot-Reload the Extension after making code changes:
```bash
gnome-extensions disable delux-battery@igazev.local && gnome-extensions enable delux-battery@igazev.local
```

---

## ⚡ Native C Binary (`delux-battery`)

The C implementation ([`delux_battery.c`](file:///home/igazev/46c02c9e-c8ba-4166-86b2-de869199e8f3/Coding/delux_test/delux_battery.c)) is built for performance and simplicity:

- **Binary size:** ~17 KB
- **Execution time:** < 70ms (primarily bounded by 2.4GHz RF round-trip latency)
- **Zero external dependencies:** Uses pure POSIX system calls (`open`, `write`, `read`, `select` on `/dev/hidraw`).

### Commands:
```bash
# JSON output (default - consumed by the GNOME extension):
./delux-battery
# Returns: {"battery":88,"charging":false,"mode":"wireless","device":"/dev/hidraw7"}

# Human-readable text output:
./delux-battery --text
# Returns: Delux M400 (wireless) | Bateria: 88% [Descarregando] (/dev/hidraw7)
```

---

## 🐍 Python Script (`delux_m400.py`)

Standalone Python utility suitable for terminal usage, Waybar, Polybar, or custom shell scripts:

```bash
# Single query (human-readable):
./delux_m400.py

# Structured JSON output:
./delux_m400.py --json

# Continuous monitoring every N seconds:
./delux_m400.py --watch 5

# Desktop notifications via notify-send when battery <= 20%:
./delux_m400.py --watch 60 --notify 20
```

---

## ⚙️ Running as a User Service (`systemd --user`)

If you are not using the GNOME extension and prefer background notifications when the battery runs low:

```bash
mkdir -p ~/.config/systemd/user
cp delux-m400-battery.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now delux-m400-battery.service
```

---

## 🔬 Reverse-Engineered HID Protocol

Reverse-engineered from the official vendor software (`DELUX-M400.exe` / `DeviceDriver.exe` / layout `MOUSE_DM204`):

- **Vendor ID:** `0x1A2C` (China Resource Semico / Shinetek Technology)
- **Product ID (2.4GHz Dongle):** `0x8FFF`
- **Product ID (USB Cable):** `0x9046`
- **HID Interface:** Interface 0 (`MI_00` / corresponding `/dev/hidrawX` node) with 64-byte report size (`0x40`).

### Packet Layout:
1. **Query Command (64-byte Output Report on Interface 0):**
   - **2.4GHz Wireless Mode:**
     `BB AA 99 88 09 FD 00 00 ...` (64 bytes, zero-padded)
   - **USB Wired Mode:**
     `08 FD 00 00 ...` (64 bytes, zero-padded)

2. **Telemetry Response (64-byte Input Report received):**
   - `Bytes [0..3]`: Magic header verification `AA 55 CC 33`
   - `Byte [5]`: **Battery percentage** (integer `0` to `100`)
   - `Byte [6]`: **Charging state** (`1` = Discharging / Normal, `3` = Charging)

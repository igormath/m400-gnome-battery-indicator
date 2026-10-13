#!/usr/bin/env python3
"""
Delux M400 Wireless / Wired Mouse Battery Monitor for Linux
Supports:
- 2.4GHz Dongle (VID 1a2c, PID 8fff)
- Wired USB (VID 1a2c, PID 9046)

Reverse-engineered from official Delux M400 software (MOUSE_DM204 / Shinetek Semico).
"""

import os
import sys
import time
import glob
import json
import argparse
import subprocess
from typing import Optional, Tuple, Dict, Any

# Device Identifiers
VENDOR_ID = 0x1A2C
PID_DONGLE = 0x8FFF
PID_WIRED = 0x9046

# Magic Commands (64-byte HID Output Reports on Interface 0)
# 2.4G Wireless command: BB AA 99 88 09 FD ...
CMD_WIRELESS = bytes([0xBB, 0xAA, 0x99, 0x88, 0x09, 0xFD] + [0x00] * 58)
# Wired command: 08 FD ...
CMD_WIRED = bytes([0x08, 0xFD] + [0x00] * 62)

# Expected response header: AA 55 CC 33
RESP_HEADER = bytes([0xAA, 0x55, 0xCC, 0x33])


def find_m400_hidraw_device() -> Optional[Tuple[str, str]]:
    """
    Finds the /dev/hidraw* device path for Delux M400 interface 0.
    Returns (device_path, mode) where mode is 'wireless' or 'wired', or None.
    """
    hidraw_base = '/sys/class/hidraw'
    if not os.path.isdir(hidraw_base):
        return None

    # Inspect all hidraw nodes in sysfs
    for node in sorted(os.listdir(hidraw_base)):
        dev_sys_path = os.path.join(hidraw_base, node)
        uevent_file = os.path.join(dev_sys_path, 'device', 'uevent')
        if not os.path.isfile(uevent_file):
            continue

        try:
            with open(uevent_file, 'r') as f:
                uevent = f.read().upper()
        except OSError:
            continue

        # Check for Vendor ID 1A2C and Product IDs 8FFF or 9046
        is_wireless = ('00001A2C:00008FFF' in uevent or '1A2C:8FFF' in uevent)
        is_wired = ('00001A2C:00009046' in uevent or '1A2C:9046' in uevent)

        if not (is_wireless or is_wired):
            continue

        # Check if this node corresponds to Interface 0 (input0 / MI_00)
        # Check HID_PHYS or device path
        phys = ""
        for line in uevent.splitlines():
            if line.startswith('HID_PHYS='):
                phys = line.split('=', 1)[1]

        # Interface 0 is typically input0 or :1.0 in USB path
        dev_link = os.path.realpath(dev_sys_path)
        if ':1.0' in dev_link or 'input0' in phys or ':1.0/' in phys:
            dev_path = os.path.join('/dev', node)
            mode = 'wireless' if is_wireless else 'wired'
            return (dev_path, mode)

    # Fallback: if interface 0 matching via string was ambiguous, check report descriptor length
    for node in sorted(os.listdir(hidraw_base)):
        dev_sys_path = os.path.join(hidraw_base, node)
        uevent_file = os.path.join(dev_sys_path, 'device', 'uevent')
        desc_file = os.path.join(dev_sys_path, 'device', 'report_descriptor')
        if not (os.path.isfile(uevent_file) and os.path.isfile(desc_file)):
            continue

        try:
            with open(uevent_file, 'r') as f:
                uevent = f.read().upper()
            if not ('1A2C' in uevent and ('8FFF' in uevent or '9046' in uevent)):
                continue
            with open(desc_file, 'rb') as f:
                desc = f.read()
            # Interface 0 vendor report descriptor is 34 bytes (Usage Page 0xFF02)
            if len(desc) == 34 and b'\x06\x02\xff' in desc:
                dev_path = os.path.join('/dev', node)
                mode = 'wireless' if '8FFF' in uevent else 'wired'
                return (dev_path, mode)
        except OSError:
            continue

    return None


def query_battery_hidraw(dev_path: str, mode: str, timeout: float = 1.0) -> Dict[str, Any]:
    """
    Sends battery status query to /dev/hidraw node and reads the response.
    """
    cmd = CMD_WIRELESS if mode == 'wireless' else CMD_WIRED

    # Open device non-blocking or with select
    import select

    fd = os.open(dev_path, os.O_RDWR | os.O_NONBLOCK)
    try:
        # Write the 64-byte query report
        # On Linux hidraw, if no Report ID is used, writing raw 64 bytes is expected
        os.write(fd, cmd)

        # Wait for response up to timeout
        r_ready, _, _ = select.select([fd], [], [], timeout)
        if not r_ready:
            raise TimeoutError("Sem resposta do mouse dentro do tempo limite.")

        response = os.read(fd, 64)
        if len(response) < 7:
            raise ValueError(f"Resposta muito curta: {len(response)} bytes")

        # Validate header
        if response[:4] != RESP_HEADER:
            # Check if there is an offset (e.g. 1 byte report ID prepended)
            if len(response) >= 8 and response[1:5] == RESP_HEADER:
                response = response[1:]
            else:
                hex_resp = response[:16].hex()
                raise ValueError(f"Cabeçalho inesperado: {hex_resp} (esperado {RESP_HEADER.hex()})")

        # Response layout:
        # [0..3]: AA 55 CC 33
        # [4]: Mode / Sub-cmd
        # [5]: Battery Percentage (0-100)
        # [6]: Status (1 = Normal / Descarregando, 3 = Carregando)
        battery_pct = response[5]
        status_code = response[6]
        charging = (status_code == 3)

        return {
            "device": dev_path,
            "mode": mode,
            "battery": int(battery_pct),
            "charging": charging,
            "status_code": int(status_code),
            "raw_hex": response[:16].hex()
        }
    finally:
        os.close(fd)


def send_desktop_notification(percentage: int, charging: bool):
    """Sends a desktop notification via notify-send if battery is low."""
    if charging:
        return
    title = "Delux M400 - Bateria Fraca"
    message = f"O nível de bateria está em {percentage}%. Conecte o cabo USB para recarregar."
    try:
        subprocess.run(["notify-send", "-u", "critical", "-i", "battery-caution", title, message], check=False)
    except FileNotFoundError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Monitor de Bateria do mouse Delux M400 no Linux")
    parser.add_argument("--json", action="store_true", help="Saída em formato JSON estruturado")
    parser.add_argument("--watch", "-w", type=int, nargs="?", const=5, help="Monitoramento contínuo em segundos (padrão: 5s)")
    parser.add_argument("--notify", type=int, default=15, help="Disparar notificação do sistema se bateria <= X%% (padrão: 15%%)")
    parser.add_argument("--device", "-d", type=str, help="Forçar caminho específico de /dev/hidrawX")
    args = parser.parse_args()

    last_notified = 0.0

    while True:
        try:
            if args.device:
                dev_path = args.device
                mode = "wireless"
            else:
                found = find_m400_hidraw_device()
                if not found:
                    if not args.watch:
                        err_msg = "Mouse Delux M400 ou Dongle 2.4GHz não foi encontrado nos nós /dev/hidraw."
                        if args.json:
                            print(json.dumps({"error": err_msg}))
                        else:
                            print(f"[ERRO] {err_msg}", file=sys.stderr)
                            print("Verifique se o dongle USB (1a2c:8fff) ou cabo (1a2c:9046) está conectado.", file=sys.stderr)
                        sys.exit(1)
                    else:
                        if not args.json:
                            print("[INFO] Mouse/dongle desconectado. Aguardando reconexão...", file=sys.stderr)
                        time.sleep(args.watch)
                        continue
                dev_path, mode = found

            info = query_battery_hidraw(dev_path, mode)
            
            if args.json:
                print(json.dumps(info))
            else:
                charge_str = "Carregando" if info["charging"] else "Descarregando"
                print(f"Delux M400 ({info['mode']}) | Bateria: {info['battery']}% [{charge_str}] (Dispositivo: {dev_path})")

            # Notification check
            if not info["charging"] and info["battery"] <= args.notify:
                now = time.time()
                if now - last_notified > 300: # Notificar no máximo uma vez a cada 5 minutos
                    send_desktop_notification(info["battery"], info["charging"])
                    last_notified = now

        except PermissionError:
            err_msg = (
                f"Permissão negada ao acessar {dev_path}.\n"
                "Instale a regra udev para permitir acesso sem sudo:\n"
                "  sudo cp 99-delux-mouse.rules /etc/udev/rules.d/\n"
                "  sudo udevadm control --reload-rules && sudo udevadm trigger"
            )
            if args.json:
                print(json.dumps({"error": "Permission denied", "device": dev_path}))
            else:
                print(f"[ERRO] {err_msg}", file=sys.stderr)
            sys.exit(2)

        except Exception as e:
            if args.json:
                print(json.dumps({"error": str(e)}))
            else:
                print(f"[AVISO] Falha na comunicação ({e}). Tentando novamente...", file=sys.stderr)

        if not args.watch:
            break

        time.sleep(args.watch)


if __name__ == '__main__':
    main()

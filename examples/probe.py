#!/usr/bin/env python3
"""
Sperax RM-01 Walking Pad BLE Protocol Probe
Interactive tool to send commands and observe responses.

Known from APK decompilation (com.spreax.fitness202412):
  Manufacturer: wi-linktech, Model: WLT6200
  Service FF10: FF12 (write), FF11 (notify)
  Service FFF0: FFF1 (read/notify), FFF2 (write)

  Command bytes found in binary:
    0x01 = deviceInfoUpdate
    0x02 = statusUpdate
    0x04 = dataQueryUpdate
    0x09 0x02 = getDeviceState
    0x1D = snCode
    0xD0 = deviceAck
    0xD1 = resetSpeed
    0xD2 = checkHandle
"""

import asyncio
import sys
import time
from bleak import BleakScanner, BleakClient

DEVICE_NAME = "SPERAX_RM01"

# Service FF10
CHAR_FF12_WRITE = "0000ff12-0000-1000-8000-00805f9b34fb"
CHAR_FF11_NOTIFY = "0000ff11-0000-1000-8000-00805f9b34fb"

# Service FFF0
CHAR_FFF1_NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
CHAR_FFF2_WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"

notification_log = []
start_time = time.time()


def on_notify(name):
    def handler(sender, data):
        elapsed = time.time() - start_time
        hex_str = data.hex(' ')
        nonzero = bytes(b for b in data if b != 0)
        entry = f"[{elapsed:7.2f}s] {name} ({len(data)}B): {hex_str[:120]}"
        if len(nonzero) < len(data) and len(nonzero) > 0:
            entry += f"\n           non-zero: {nonzero.hex(' ')}"
        print(entry)
        notification_log.append((elapsed, name, data))
    return handler


def simple_crc(data):
    """Try XOR-based CRC (common in Chinese BLE devices)."""
    crc = 0
    for b in data:
        crc ^= b
    return crc & 0xFF


def additive_checksum(data):
    """Simple additive checksum mod 256."""
    return sum(data) & 0xFF


async def main():
    print(f"Scanning for {DEVICE_NAME}...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10)
    if not device:
        print("Not found!")
        return

    print(f"Connecting to {device.name}...")

    async with BleakClient(device) as client:
        print(f"Connected!\n")

        # Subscribe to all notify characteristics
        await client.start_notify(CHAR_FF11_NOTIFY, on_notify("FF11"))
        await client.start_notify(CHAR_FFF1_NOTIFY, on_notify("FFF1"))
        print("Subscribed to FF11 and FFF1 notifications.\n")

        # Read initial state
        for name, uuid in [("FF12", CHAR_FF12_WRITE), ("FFF2", CHAR_FFF2_WRITE)]:
            val = await client.read_gatt_char(uuid)
            nonzero = bytes(b for b in val if b != 0)
            print(f"Initial {name}: {nonzero.hex(' ')} ({len(val)}B total)")

        print("\n" + "=" * 60)
        print("INTERACTIVE PROBE MODE")
        print("=" * 60)
        print("""
Commands:
  raw <hex bytes>          - Send raw bytes to FFF2 (e.g., raw 09 02)
  rawff <hex bytes>        - Send raw bytes to FF12
  read                     - Read current values from FFF1 and FFF2
  wait <seconds>           - Wait and collect notifications
  log                      - Show notification log
  quit                     - Exit

Known command bytes from APK:
  01 = deviceInfoUpdate    02 = statusUpdate
  04 = dataQueryUpdate     09 02 = getDeviceState
  1D = snCode              D0 = deviceAck
  D1 = resetSpeed          D2 = checkHandle
""")

        loop = asyncio.get_event_loop()

        while True:
            try:
                cmd = await loop.run_in_executor(None, lambda: input("probe> ").strip())
            except (EOFError, KeyboardInterrupt):
                break

            if not cmd:
                continue

            if cmd == "quit":
                break

            elif cmd == "read":
                for name, uuid in [("FF12", CHAR_FF12_WRITE), ("FFF2", CHAR_FFF2_WRITE),
                                    ("FFF1", CHAR_FFF1_NOTIFY)]:
                    try:
                        val = await client.read_gatt_char(uuid)
                        nonzero = bytes(b for b in val if b != 0)
                        print(f"  {name}: {nonzero.hex(' ')} ({len(val)}B total)")
                    except Exception as e:
                        print(f"  {name}: read failed - {e}")

            elif cmd == "log":
                for elapsed, name, data in notification_log[-20:]:
                    nonzero = bytes(b for b in data if b != 0)
                    print(f"  [{elapsed:7.2f}s] {name}: {nonzero.hex(' ')}")

            elif cmd.startswith("wait"):
                try:
                    secs = float(cmd.split()[1]) if len(cmd.split()) > 1 else 5
                except ValueError:
                    secs = 5
                print(f"  Waiting {secs}s for notifications...")
                await asyncio.sleep(secs)
                print(f"  Done. Got {len(notification_log)} total notifications.")

            elif cmd.startswith("raw ") or cmd.startswith("rawff "):
                try:
                    use_ff12 = cmd.startswith("rawff ")
                    hex_str = cmd.split(" ", 1)[1] if cmd.startswith("rawff ") else cmd[4:]
                    data = bytes.fromhex(hex_str.replace(" ", ""))
                    char = CHAR_FF12_WRITE if use_ff12 else CHAR_FFF2_WRITE
                    char_name = "FF12" if use_ff12 else "FFF2"

                    print(f"  Sending to {char_name}: {data.hex(' ')}")
                    count_before = len(notification_log)
                    await client.write_gatt_char(char, data, response=False)
                    await asyncio.sleep(1.0)
                    new_notifs = notification_log[count_before:]
                    if new_notifs:
                        print(f"  Got {len(new_notifs)} notification(s) in response")
                    else:
                        print(f"  No notifications received")

                except ValueError as e:
                    print(f"  Invalid hex: {e}")
                except Exception as e:
                    print(f"  Write failed: {e}")

            else:
                print(f"  Unknown command: {cmd}")

        print("\nDisconnecting...")
        print(f"\nTotal notifications received: {len(notification_log)}")

        # Dump full log
        if notification_log:
            print("\n--- Full Notification Log ---")
            for elapsed, name, data in notification_log:
                nonzero = bytes(b for b in data if b != 0)
                print(f"[{elapsed:7.2f}s] {name}: {nonzero.hex(' ')} (full: {data[:20].hex(' ')}...)")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Sperax RM-01 BLE Protocol Probe v2
Now with proper F5..FA framing based on response analysis.

Frame format (hypothesis):
  F5 <len> <cmd> [payload...] <checksum> FA

Header: F5
Trailer: FA
Length: total packet length including header/trailer
Checksum: XOR of bytes between header and checksum (exclusive)
"""

import asyncio
import sys
import time
from bleak import BleakScanner, BleakClient

DEVICE_NAME = "SPERAX_RM01"

CHAR_FF12_WRITE = "0000ff12-0000-1000-8000-00805f9b34fb"
CHAR_FF11_NOTIFY = "0000ff11-0000-1000-8000-00805f9b34fb"
CHAR_FFF1_NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
CHAR_FFF2_WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"

notification_log = []
start_time = time.time()


def on_notify(name):
    def handler(sender, data):
        elapsed = time.time() - start_time
        hex_str = data.hex(' ')
        nonzero = bytes(b for b in data if b != 0)
        entry = f"[{elapsed:7.2f}s] {name} ({len(data)}B): {hex_str}"
        print(entry)
        notification_log.append((elapsed, name, data))
    return handler


def build_frame(cmd_bytes):
    """Build a properly framed command: F5 <len> <cmd...> <checksum> FA"""
    # Length = header(1) + len(1) + cmd(n) + checksum(1) + trailer(1)
    length = 1 + 1 + len(cmd_bytes) + 1 + 1
    # Build packet without checksum
    packet = [0xF5, length] + list(cmd_bytes)
    # XOR checksum of everything between header and checksum position
    checksum = 0
    for b in packet[1:]:  # skip F5 header
        checksum ^= b
    packet.append(checksum)
    packet.append(0xFA)
    return bytes(packet)


def build_frame_v2(cmd_bytes):
    """Alternative: checksum is sum mod 256."""
    length = 1 + 1 + len(cmd_bytes) + 1 + 1
    packet = [0xF5, length] + list(cmd_bytes)
    checksum = sum(packet[1:]) & 0xFF
    packet.append(checksum)
    packet.append(0xFA)
    return bytes(packet)


def build_frame_v3(cmd_bytes):
    """Alternative: length doesn't include header/trailer."""
    length = len(cmd_bytes) + 1  # cmd + checksum
    packet = [0xF5, length] + list(cmd_bytes)
    checksum = 0
    for b in packet[1:]:
        checksum ^= b
    packet.append(checksum)
    packet.append(0xFA)
    return bytes(packet)


def verify_response_checksum(data):
    """Try to figure out the checksum algorithm from response F5 08 00 0E 02 14 47 FA."""
    if len(data) < 4 or data[0] != 0xF5 or data[-1] != 0xFA:
        return "Not a valid frame"

    body = data[1:-2]  # between header and checksum
    expected_cs = data[-2]

    xor_cs = 0
    for b in body:
        xor_cs ^= b

    sum_cs = sum(body) & 0xFF

    results = []
    results.append(f"Body bytes: {body.hex(' ')}")
    results.append(f"Expected checksum: 0x{expected_cs:02X}")
    results.append(f"XOR checksum: 0x{xor_cs:02X} {'MATCH!' if xor_cs == expected_cs else ''}")
    results.append(f"SUM checksum: 0x{sum_cs:02X} {'MATCH!' if sum_cs == expected_cs else ''}")

    # Try XOR including header
    xor_all = 0
    for b in data[:-2]:
        xor_all ^= b
    results.append(f"XOR (incl header): 0x{xor_all:02X} {'MATCH!' if xor_all == expected_cs else ''}")

    # Try sum including header
    sum_all = sum(data[:-2]) & 0xFF
    results.append(f"SUM (incl header): 0x{sum_all:02X} {'MATCH!' if sum_all == expected_cs else ''}")

    # CRC8
    crc = 0
    for b in body:
        crc = (crc + b) & 0xFF
    results.append(f"Additive CRC body: 0x{crc:02X} {'MATCH!' if crc == expected_cs else ''}")

    return "\n".join(results)


async def main():
    # First, let's verify the checksum algorithm from the known response
    known_response = bytes([0xF5, 0x08, 0x00, 0x0E, 0x02, 0x14, 0x47, 0xFA])
    print("=== Checksum Analysis of Known Response ===")
    print(f"Response: {known_response.hex(' ')}")
    print(verify_response_checksum(known_response))
    print()

    print(f"Scanning for {DEVICE_NAME}...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10)
    if not device:
        print("Not found!")
        return

    print(f"Connecting to {device.name}...")

    async with BleakClient(device) as client:
        print(f"Connected!\n")

        await client.start_notify(CHAR_FF11_NOTIFY, on_notify("FF11"))
        await client.start_notify(CHAR_FFF1_NOTIFY, on_notify("FFF1"))
        print("Subscribed to notifications.\n")

        await asyncio.sleep(3)  # Wait for initial notifications

        print("=== Sending Framed Commands to FFF2 ===\n")

        # Try different framing approaches for device state query (0x09, 0x02)
        test_commands = [
            ("getDeviceState raw", bytes([0x09, 0x02])),
            ("getDeviceState framed v1 (XOR)", build_frame(bytes([0x09, 0x02]))),
            ("getDeviceState framed v2 (SUM)", build_frame_v2(bytes([0x09, 0x02]))),
            ("getDeviceState framed v3 (short len)", build_frame_v3(bytes([0x09, 0x02]))),
            ("status query raw 02", bytes([0x02])),
            ("status framed v1", build_frame(bytes([0x02]))),
            ("deviceInfo raw 01", bytes([0x01])),
            ("deviceInfo framed v1", build_frame(bytes([0x01]))),
            ("ack raw D0", bytes([0xD0])),
            ("ack framed v1", build_frame(bytes([0xD0]))),
        ]

        for name, cmd in test_commands:
            count_before = len(notification_log)
            print(f"--- {name}: {cmd.hex(' ')} ---")
            await client.write_gatt_char(CHAR_FFF2_WRITE, cmd, response=False)
            await asyncio.sleep(1.5)
            new = notification_log[count_before:]
            if new:
                for _, nname, ndata in new:
                    print(f"    Response: {ndata.hex(' ')}")
            else:
                print(f"    No response")
            print()

        # Also try writing to FF12 instead
        print("=== Now trying FF12 write characteristic ===\n")

        ff12_commands = [
            ("FF12 getDeviceState raw", bytes([0x09, 0x02])),
            ("FF12 getDeviceState framed", build_frame(bytes([0x09, 0x02]))),
            ("FF12 status raw 02", bytes([0x02])),
            ("FF12 status framed", build_frame(bytes([0x02]))),
        ]

        for name, cmd in ff12_commands:
            count_before = len(notification_log)
            print(f"--- {name}: {cmd.hex(' ')} ---")
            await client.write_gatt_char(CHAR_FF12_WRITE, cmd, response=False)
            await asyncio.sleep(1.5)
            new = notification_log[count_before:]
            if new:
                for _, nname, ndata in new:
                    print(f"    Response on {nname}: {ndata.hex(' ')}")
            else:
                print(f"    No response")
            print()

        print(f"\nTotal notifications: {len(notification_log)}")
        print("\n--- Unique Responses ---")
        seen = set()
        for _, name, data in notification_log:
            key = data.hex()
            if key not in seen:
                seen.add(key)
                print(f"  {name}: {data.hex(' ')}")


if __name__ == "__main__":
    asyncio.run(main())

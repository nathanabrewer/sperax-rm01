#!/usr/bin/env python3
"""
Sperax RM-01 Walking Pad - Command Tester
Sends properly framed commands one at a time for verification.

Protocol: F5 <total_len> 00 <data...> <CRC_lo> <CRC_hi> FA
CRC-16: polynomial 0xA327, init 0xFFFF
"""

import asyncio
import sys
import time
from bleak import BleakScanner, BleakClient

DEVICE_NAME = "SPERAX_RM01"
CHAR_FFF1_NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
CHAR_FFF2_WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"

notification_log = []
start_time = time.time()


def crc16(data):
    """CRC-16 with polynomial 0xA327, init 0xFFFF."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA327
            else:
                crc >>= 1
    return crc & 0xFFFF


def build_frame(cmd_data):
    """Build a properly framed command with CRC."""
    total_len = 3 + len(cmd_data) + 2 + 1  # header(1) + len(1) + 0x00(1) + data + crc(2) + trailer(1)
    pre_crc = [0xF5, total_len, 0x00] + list(cmd_data)
    crc = crc16(pre_crc)
    frame = pre_crc + [crc & 0xFF, (crc >> 8) & 0xFF, 0xFA]
    return bytes(frame)


def on_notify(sender, data):
    elapsed = time.time() - start_time
    hex_str = data.hex(' ')
    print(f"  << RESPONSE [{elapsed:7.2f}s] ({len(data)}B): {hex_str}")
    notification_log.append((elapsed, data))


# Pre-built commands
COMMANDS = {
    "requestControl": build_frame(bytes([0x00])),
    "startRun":       build_frame(bytes([0x07])),
    "stopRun":        build_frame(bytes([0x08, 0x01])),
    "pauseRun":       build_frame(bytes([0x08, 0x02])),
    "speed_10":       build_frame(bytes([0x02, 0x0A, 0x00])),  # 1.0 km/h
    "speed_20":       build_frame(bytes([0x02, 0x14, 0x00])),  # 2.0 km/h
    "speed_30":       build_frame(bytes([0x02, 0x1E, 0x00])),  # 3.0 km/h
    "speed_50":       build_frame(bytes([0x02, 0x32, 0x00])),  # 5.0 km/h
    "getData":        build_frame(bytes([0x19])),
    "readSNCode":     build_frame(bytes([0x1D])),
    "restart":        build_frame(bytes([0x0C])),
}


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "interactive"

    print("=" * 60)
    print("  SPERAX RM-01 COMMAND TESTER")
    print("  CRC-16 poly=0xA327 init=0xFFFF")
    print("=" * 60)
    print()

    # Show all pre-built commands
    print("Available commands:")
    for name, frame in COMMANDS.items():
        print(f"  {name:20s} -> {frame.hex(' ')}")
    print()

    if mode == "safe":
        # Just send requestControl and getData — non-destructive
        commands_to_send = ["requestControl", "getData", "readSNCode"]
    elif mode == "start":
        # Full start sequence
        commands_to_send = ["requestControl", "startRun"]
    elif mode == "stop":
        commands_to_send = ["stopRun"]
    elif mode == "interactive":
        commands_to_send = None  # Will prompt
    else:
        # Single command by name
        if mode in COMMANDS:
            commands_to_send = [mode]
        else:
            print(f"Unknown command: {mode}")
            print(f"Available: {', '.join(COMMANDS.keys())}")
            return

    print(f"Scanning for {DEVICE_NAME}...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10)
    if not device:
        print("Device not found! Make sure the walking pad is on.")
        return

    print(f"Found {device.name}")
    print(f"Connecting...")

    async with BleakClient(device) as client:
        print(f"Connected!\n")

        await client.start_notify(CHAR_FFF1_NOTIFY, on_notify)
        print("Subscribed to FFF1 notifications.")
        await asyncio.sleep(2)  # Wait for initial notifications

        if commands_to_send:
            # Batch mode
            for cmd_name in commands_to_send:
                frame = COMMANDS[cmd_name]
                print(f"\n>> Sending {cmd_name}: {frame.hex(' ')}")
                count_before = len(notification_log)
                await client.write_gatt_char(CHAR_FFF2_WRITE, frame, response=False)
                await asyncio.sleep(2)
                new_responses = notification_log[count_before:]
                if not new_responses:
                    print("  (no response)")
        else:
            # Interactive mode
            print("\nInteractive mode. Type command name or 'q' to quit.")
            print(f"Commands: {', '.join(COMMANDS.keys())}")
            print("Or type 'raw XX XX XX' to send raw hex bytes as command data (will be framed).\n")

            while True:
                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("cmd> ").strip()
                    )
                except EOFError:
                    break

                if not user_input or user_input == 'q':
                    break

                if user_input.startswith("raw "):
                    # Parse raw hex bytes and frame them
                    try:
                        hex_parts = user_input[4:].split()
                        cmd_bytes = bytes(int(h, 16) for h in hex_parts)
                        frame = build_frame(cmd_bytes)
                        cmd_name = f"raw({user_input[4:]})"
                    except ValueError:
                        print("Invalid hex. Example: raw 02 0A 00")
                        continue
                elif user_input.startswith("speed "):
                    # Quick speed setter: "speed 3.5"
                    try:
                        speed_kmh = float(user_input.split()[1])
                        speed_val = int(speed_kmh * 10)
                        frame = build_frame(bytes([0x02, speed_val & 0xFF, (speed_val >> 8) & 0xFF]))
                        cmd_name = f"setSpeed({speed_kmh})"
                    except (ValueError, IndexError):
                        print("Usage: speed 3.5  (km/h)")
                        continue
                elif user_input in COMMANDS:
                    frame = COMMANDS[user_input]
                    cmd_name = user_input
                else:
                    print(f"Unknown: {user_input}")
                    continue

                count_before = len(notification_log)
                print(f">> Sending {cmd_name}: {frame.hex(' ')}")
                await client.write_gatt_char(CHAR_FFF2_WRITE, frame, response=False)
                await asyncio.sleep(2)
                new_responses = notification_log[count_before:]
                if not new_responses:
                    print("  (no response)")

        print("\n\nDisconnecting...")

    # Summary
    print("\n" + "=" * 60)
    print("  SESSION LOG")
    print("=" * 60)
    for elapsed, data in notification_log:
        print(f"  [{elapsed:7.2f}s] {data.hex(' ')}")
    print(f"\nTotal responses: {len(notification_log)}")


if __name__ == "__main__":
    asyncio.run(main())

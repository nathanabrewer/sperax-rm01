#!/usr/bin/env python3
"""Subscribe to Sperax walking pad notifications and log everything it sends."""

import asyncio
import time
from bleak import BleakScanner, BleakClient

DEVICE_NAME = "SPERAX_RM01"

# Both services have notify characteristics
NOTIFY_CHARS = {
    "FF11": "0000ff11-0000-1000-8000-00805f9b34fb",  # Service FF10
    "FFF1": "0000fff1-0000-1000-8000-00805f9b34fb",  # Service FFF0
}

WRITE_CHARS = {
    "FF12": "0000ff12-0000-1000-8000-00805f9b34fb",  # Service FF10
    "FFF2": "0000fff2-0000-1000-8000-00805f9b34fb",  # Service FFF0
}

start_time = time.time()

def make_handler(name):
    def handler(sender, data):
        elapsed = time.time() - start_time
        hex_str = data.hex(' ')
        # Try to interpret non-zero bytes
        nonzero = [b for b in data if b != 0]
        print(f"[{elapsed:7.2f}s] {name} ({len(data)}B): {hex_str[:80]}")
        if len(nonzero) < len(data):
            print(f"           non-zero bytes: {' '.join(f'{b:02x}' for b in nonzero)}")
    return handler

async def main():
    print(f"Scanning for {DEVICE_NAME}...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10)
    if not device:
        print("Not found! Is it powered on?")
        return

    print(f"Found {device.name} ({device.address})")
    print(f"Connecting...")

    async with BleakClient(device) as client:
        print(f"Connected!\n")

        # Read initial values from writable chars
        for name, uuid in WRITE_CHARS.items():
            try:
                val = await client.read_gatt_char(uuid)
                nonzero = [b for b in val if b != 0]
                print(f"Initial {name}: {' '.join(f'{b:02x}' for b in nonzero)} ({len(val)}B total)")
            except Exception as e:
                print(f"Read {name} failed: {e}")

        print()

        # Subscribe to all notify characteristics
        for name, uuid in NOTIFY_CHARS.items():
            try:
                await client.start_notify(uuid, make_handler(name))
                print(f"Subscribed to {name} notifications")
            except Exception as e:
                print(f"Failed to subscribe to {name}: {e}")

        print(f"\nListening for notifications... (Ctrl+C to stop)")
        print(f"Try using the Sperax remote or pressing buttons on the pad.\n")

        # Keep listening
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")

if __name__ == "__main__":
    asyncio.run(main())

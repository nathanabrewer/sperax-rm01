#!/usr/bin/env python3
"""Scan for Sperax walking pad and enumerate GATT services/characteristics."""

import asyncio
from bleak import BleakScanner, BleakClient

SCAN_SECONDS = 10

async def main():
    print(f"Scanning for BLE devices ({SCAN_SECONDS}s)...")
    devices = await BleakScanner.discover(timeout=SCAN_SECONDS, return_adv=True)

    sperax = None
    print(f"\nFound {len(devices)} devices:\n")
    for addr, (device, adv) in devices.items():
        name = adv.local_name or device.name or "Unknown"
        if "sperax" in name.lower() or "rm01" in name.lower() or "rm-01" in name.lower() or "walkingpad" in name.lower():
            print(f"  >>> {name}  addr={addr}  RSSI={adv.rssi}dBm  <<<")
            sperax = device
        else:
            print(f"  {name}  addr={addr}  RSSI={adv.rssi}dBm")

    if not sperax:
        print("\nNo Sperax device found. Is it powered on and not connected to another app?")
        return

    print(f"\n{'='*60}")
    print(f"Connecting to {sperax.name} ({sperax.address})...")
    print(f"{'='*60}\n")

    async with BleakClient(sperax) as client:
        print(f"Connected: {client.is_connected}\n")

        for service in client.services:
            print(f"Service: {service.uuid}  [{service.description}]")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  Char: {char.uuid}  [{char.description}]")
                print(f"    Properties: {props}")
                print(f"    Handle: 0x{char.handle:04X}")

                # If readable, try to read current value
                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char)
                        print(f"    Value: {value.hex(' ')} ({value})")
                    except Exception as e:
                        print(f"    Read failed: {e}")

                for desc in char.descriptors:
                    print(f"    Descriptor: {desc.uuid}  [{desc.description}]")
                    try:
                        value = await client.read_gatt_char(desc)
                        print(f"      Value: {value.hex(' ')} ({value})")
                    except Exception:
                        pass
            print()

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Sperax RM-01 Walking Pad BLE Clone / MITM
Impersonates the walking pad's GATT profile so the real app or remote
connects to us. Logs every command they send.
"""

import asyncio
import time
import logging
from bless import BlessServer, BlessGATTCharacteristic, GATTCharacteristicProperties, GATTAttributePermissions

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

start_time = time.time()
command_log = []

IDLE_RESPONSE = bytes([0xF5, 0x08, 0x00, 0x0E, 0x02, 0x14, 0x47, 0xFA])
CONNECT_NOTIFY = bytes([0x12, 0x13, 0x14])


def log_command(char_uuid, data, direction="WRITE"):
    elapsed = time.time() - start_time
    hex_str = data.hex(' ')
    print(f"\n{'='*60}")
    print(f"  >>> [{elapsed:7.2f}s] {direction} {char_uuid}: {hex_str} <<<")
    print(f"{'='*60}")
    command_log.append((elapsed, char_uuid, direction, data))


def write_handler(characteristic: BlessGATTCharacteristic, value: bytearray, **kwargs):
    uuid_short = characteristic.uuid.split('-')[0][-4:].upper()
    log_command(uuid_short, bytes(value), "WRITE")


def read_handler(characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
    uuid_short = characteristic.uuid.split('-')[0][-4:].upper()
    elapsed = time.time() - start_time
    print(f"[{elapsed:7.2f}s] READ request on {uuid_short}")
    return characteristic.value


async def main():
    print("=" * 60)
    print("  SPERAX_RM01 BLE CLONE")
    print("  Turn off the real walking pad!")
    print("  Connect the Sperax app or remote to this clone.")
    print("=" * 60)
    print()

    server = BlessServer(name="SPERAX_RM01")
    server.write_request_func = write_handler
    server.read_request_func = read_handler

    # Service: Device Information (0x180A) - read-only chars are fine
    svc_180a = "0000180a-0000-1000-8000-00805f9b34fb"
    await server.add_new_service(svc_180a)

    device_info = {
        "00002a25": b'1537003908E0\x00',
        "00002a28": b'R22_V227.04.03\x00',
        "00002a27": b'V1.0.0\x00',
        "00002a29": b'wi-linktech\x00\x00\x00\x00\x00\x00\x00\x00\x00',
        "00002a24": b'WLT6200\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
    }
    for uuid_prefix, value in device_info.items():
        await server.add_new_characteristic(
            svc_180a,
            uuid_prefix + "-0000-1000-8000-00805f9b34fb",
            GATTCharacteristicProperties.read,
            bytearray(value),
            GATTAttributePermissions.readable,
        )

    # Service FFF0 - the main one
    svc_fff0 = "0000fff0-0000-1000-8000-00805f9b34fb"
    await server.add_new_service(svc_fff0)

    # FFF1 - notify only (CoreBluetooth: no cached value for non-read-only)
    await server.add_new_characteristic(
        svc_fff0,
        "0000fff1-0000-1000-8000-00805f9b34fb",
        GATTCharacteristicProperties.notify,
        None,
        GATTAttributePermissions.readable,
    )

    # FFF2 - write-without-response only
    await server.add_new_characteristic(
        svc_fff0,
        "0000fff2-0000-1000-8000-00805f9b34fb",
        GATTCharacteristicProperties.write_without_response,
        None,
        GATTAttributePermissions.writeable,
    )

    print("Starting BLE GATT server...")
    # prioritize_local_name=False so service UUIDs are advertised (app scans by UUID)
    await server.start(prioritize_local_name=False)
    print("Server started! Advertising as SPERAX_RM01 with FFF0 service UUID")
    print("Waiting for connections... (Ctrl+C to stop)\n")

    try:
        while True:
            await asyncio.sleep(5)
            # Try to send connect notification periodically
            try:
                char = server.get_characteristic("0000fff1-0000-1000-8000-00805f9b34fb")
                if char:
                    char.value = bytearray(CONNECT_NOTIFY)
                    await server.update_value(svc_fff0, "0000fff1-0000-1000-8000-00805f9b34fb")
            except Exception:
                pass
    except KeyboardInterrupt:
        pass

    await server.stop()

    print("\n\n" + "=" * 60)
    print("  CAPTURED COMMAND LOG")
    print("=" * 60)
    for elapsed, uuid, direction, data in command_log:
        print(f"[{elapsed:7.2f}s] {direction} {uuid}: {data.hex(' ')}")

    with open("captured_commands.log", "w") as f:
        for elapsed, uuid, direction, data in command_log:
            f.write(f"{elapsed:.2f}\t{direction}\t{uuid}\t{data.hex(' ')}\n")
    print(f"\nLog saved to captured_commands.log")


if __name__ == "__main__":
    asyncio.run(main())

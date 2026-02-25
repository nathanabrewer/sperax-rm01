#!/usr/bin/env python3
"""
sperax-walk -- Interactive terminal controller for the Sperax RM-01 walking pad.

Commands:
  start       - Start belt at 2.0 km/h
  stop        - Stop the belt
  1.0 - 6.0   - Set speed in km/h (just type the number)
  +           - Speed up 0.5 km/h
  -           - Slow down 0.5 km/h
  status      - Query device data
  q           - Stop belt and quit
"""

from __future__ import annotations

import asyncio

from .pad import SperaxPad
from .protocol import (
    RESP_STATUS,
    STATUS_NAMES,
    CMD_DEVICE_ACK,
    CMD_GET_DATA,
    SPEED_MIN,
    SPEED_MAX,
)


def _make_notification_printer():
    """Return a callback that pretty-prints pad notifications."""

    def _on_notify(data: bytes) -> None:
        if len(data) >= 4 and data[0] == 0xF5 and data[-1] == 0xFA:
            cmd = data[3] if len(data) > 3 else 0
            if cmd == CMD_DEVICE_ACK:
                pass  # quiet ack
            elif cmd == RESP_STATUS:
                state = data[4] if len(data) > 4 else 0xFF
                print(f"  [pad: {STATUS_NAMES.get(state, f'0x{state:02x}')}]")
            elif cmd == CMD_GET_DATA:
                print(f"  [telemetry: {data.hex(' ')}]")
            else:
                print(f"  [{data.hex(' ')}]")
        elif data == bytes([0x12, 0x13, 0x14]):
            print("  [connected]")

    return _on_notify


async def _run() -> None:
    print("=" * 40)
    print("  SPERAX RM-01 CONTROLLER")
    print("=" * 40)
    print("  start  stop  q")
    print(f"  {SPEED_MIN}-{SPEED_MAX}  +  -  status")
    print()

    pad = SperaxPad()
    pad.on_notification = _make_notification_printer()

    print(f"Scanning for {pad._device_name}...")
    try:
        await pad.connect()
    except ConnectionError as exc:
        print(str(exc))
        return

    await asyncio.sleep(0.5)
    print("Connected!\n")

    loop = asyncio.get_event_loop()

    try:
        while True:
            try:
                prompt = f"[{'OFF' if not pad.running else f'{pad.speed} km/h'}] > "
                user_input = await loop.run_in_executor(
                    None, lambda: input(prompt).strip()
                )
            except (EOFError, KeyboardInterrupt):
                user_input = "q"

            if not user_input:
                continue

            if user_input == "q":
                if pad.running:
                    await pad.stop()
                    await asyncio.sleep(1)
                break
            elif user_input == "start":
                await pad.start()
            elif user_input == "stop":
                await pad.stop()
            elif user_input == "+":
                if pad.running:
                    await pad.set_speed(pad.speed + 0.5)
            elif user_input == "-":
                if pad.running and pad.speed > SPEED_MIN:
                    await pad.set_speed(pad.speed - 0.5)
            elif user_input == "status":
                await pad.query_data()
            else:
                try:
                    speed = float(user_input)
                    if SPEED_MIN <= speed <= SPEED_MAX:
                        await pad.set_speed(speed)
                    else:
                        print(f"  {SPEED_MIN} - {SPEED_MAX} km/h")
                except ValueError:
                    print("  ?")
    finally:
        await pad.disconnect()
        print("Disconnected.")


def main() -> None:
    """Entry point for the ``sperax-walk`` console script."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()

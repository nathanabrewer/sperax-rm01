"""
SperaxPad -- async BLE controller for the Sperax RM-01 walking pad.

Usage::

    from sperax_rm01 import SperaxPad

    pad = SperaxPad()
    await pad.connect()
    await pad.start(speed=2.0)
    await pad.set_speed(3.5)
    await pad.stop()
    await pad.disconnect()
"""

from __future__ import annotations

import asyncio
from typing import Callable

from bleak import BleakClient, BleakScanner

from .protocol import (
    CHAR_FFF1_NOTIFY,
    CHAR_FFF2_WRITE,
    CMD_GET_DATA,
    CMD_REQUEST_CONTROL,
    CMD_RUN_CTRL,
    CONNECT_NOTIFY,
    DEVICE_NAME,
    RESP_STATUS,
    SPEED_MAX,
    SPEED_MIN,
    STATUS_NAMES,
    build_frame,
    encode_speed,
)


class SperaxPad:
    """High-level async controller for a Sperax RM-01 walking pad."""

    def __init__(
        self,
        device_name: str = DEVICE_NAME,
        scan_timeout: float = 10.0,
    ) -> None:
        self._device_name = device_name
        self._scan_timeout = scan_timeout

        self._client: BleakClient | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

        # Public state
        self._speed: float = 0.0
        self._running: bool = False

        # Optional user callback for raw notifications
        self.on_notification: Callable[[bytes], None] | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def speed(self) -> float:
        """Current speed in km/h (0.0 when stopped)."""
        return self._speed

    @property
    def running(self) -> bool:
        """True if the belt is running."""
        return self._running

    @property
    def connected(self) -> bool:
        """True if BLE is connected."""
        return self._client is not None and self._client.is_connected

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        """Scan for the pad and establish a BLE connection."""
        if self.connected:
            return

        device = await BleakScanner.find_device_by_name(
            self._device_name, timeout=self._scan_timeout
        )
        if device is None:
            raise ConnectionError(
                f"Device '{self._device_name}' not found. "
                "Is the walking pad powered on?"
            )

        self._client = BleakClient(device)
        await self._client.connect()
        await self._client.start_notify(CHAR_FFF1_NOTIFY, self._handle_notify)
        # Give the pad a moment to send the connect handshake
        await asyncio.sleep(0.5)

        # Start background keepalive
        self._stop_event.clear()
        self._keepalive_task = asyncio.create_task(self._keepalive())

    async def disconnect(self) -> None:
        """Disconnect from the pad. Stops the belt first if running."""
        if self._running and self._client is not None and self._client.is_connected:
            try:
                await self._send_cmd(bytes([CMD_RUN_CTRL, 0x00, 0x00, 0x00]))
                await asyncio.sleep(0.5)
            except Exception:
                pass

        if self._keepalive_task is not None:
            self._stop_event.set()
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            self._keepalive_task = None

        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

        self._speed = 0.0
        self._running = False

    # ------------------------------------------------------------------
    # Belt control
    # ------------------------------------------------------------------
    async def start(self, speed: float = 2.0) -> None:
        """Request control and start the belt at *speed* km/h."""
        self._ensure_connected()
        await self._send_cmd(bytes([CMD_REQUEST_CONTROL]))
        await asyncio.sleep(0.3)
        await self.set_speed(speed)

    async def set_speed(self, speed: float) -> None:
        """Change the belt speed (0.5 -- 6.0 km/h)."""
        self._ensure_connected()
        speed = max(SPEED_MIN, min(SPEED_MAX, speed))
        speed_byte = encode_speed(speed)
        await self._send_cmd(
            bytes([CMD_RUN_CTRL, 0x01, speed_byte, 0x00])
        )
        self._speed = speed
        self._running = True

    async def stop(self) -> None:
        """Stop the belt."""
        self._ensure_connected()
        await self._send_cmd(bytes([CMD_RUN_CTRL, 0x00, 0x00, 0x00]))
        await asyncio.sleep(0.5)
        await self._send_cmd(bytes([CMD_RUN_CTRL, 0x00, 0x00, 0x00]))
        self._running = False
        self._speed = 0.0

    async def query_data(self) -> None:
        """Send a telemetry data query (response arrives via notification)."""
        self._ensure_connected()
        await self._send_cmd(bytes([CMD_GET_DATA]))

    async def request_control(self) -> None:
        """Send a request-control / keepalive packet."""
        self._ensure_connected()
        await self._send_cmd(bytes([CMD_REQUEST_CONTROL]))

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    async def __aenter__(self) -> SperaxPad:
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._running:
            await self.stop()
            await asyncio.sleep(1)
        await self.disconnect()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _ensure_connected(self) -> None:
        if not self.connected:
            raise ConnectionError("Not connected. Call connect() first.")

    async def _send_cmd(self, cmd_data: bytes) -> None:
        frame = build_frame(cmd_data)
        assert self._client is not None
        await self._client.write_gatt_char(CHAR_FFF2_WRITE, frame, response=False)

    def _handle_notify(self, _sender: int, data: bytearray) -> None:
        """Process incoming BLE notifications."""
        if self.on_notification is not None:
            self.on_notification(bytes(data))

        # Update internal state from status frames
        if len(data) >= 5 and data[0] == 0xF5 and data[-1] == 0xFA:
            cmd = data[3]
            if cmd == RESP_STATUS:
                state = data[4]
                if state == 0x01:  # running
                    self._running = True
                elif state in (0x02, 0x03):  # idle / paused
                    self._running = False
                    self._speed = 0.0
                # 0x00 = ready (control granted) — don't reset speed

    async def _keepalive(self) -> None:
        """Periodically send request-control to keep BLE alive."""
        while not self._stop_event.is_set():
            try:
                await self._send_cmd(bytes([CMD_REQUEST_CONTROL]))
                await asyncio.sleep(2)
            except Exception:
                break

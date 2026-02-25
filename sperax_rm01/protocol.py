"""
Sperax RM-01 BLE protocol: CRC, frame building, and command constants.

Protocol details: see PROTOCOL.md
"""

# ---------------------------------------------------------------------------
# BLE identifiers
# ---------------------------------------------------------------------------
DEVICE_NAME = "SPERAX_RM01"

CHAR_FFF1_NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
CHAR_FFF2_WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"

# ---------------------------------------------------------------------------
# Command bytes
# ---------------------------------------------------------------------------
CMD_REQUEST_CONTROL = 0x00
CMD_START_RUN = 0x07
CMD_STOP_RUN = 0x08
CMD_RESTART = 0x0C
CMD_RUN_CTRL = 0x15
CMD_SHAKE_CTRL = 0x16
CMD_CLEAN_DATA = 0x17
CMD_GET_DATA = 0x19
CMD_GET_ALL_DATA = 0x1A
CMD_READ_SN = 0x1D
CMD_DEVICE_ACK = 0xD0
CMD_SHAKE_START = 0xF0

# ---------------------------------------------------------------------------
# Response / status codes
# ---------------------------------------------------------------------------
RESP_STATUS = 0x0E

STATUS_READY = 0x00
STATUS_RUNNING = 0x01
STATUS_IDLE = 0x02
STATUS_PAUSED = 0x03

STATUS_NAMES = {
    STATUS_READY: "ready",
    STATUS_RUNNING: "running",
    STATUS_IDLE: "idle",
    STATUS_PAUSED: "paused",
}

# Connection handshake sent by the pad on BLE connect
CONNECT_NOTIFY = bytes([0x12, 0x13, 0x14])

# ---------------------------------------------------------------------------
# Speed limits (km/h)
# ---------------------------------------------------------------------------
SPEED_MIN = 0.5
SPEED_MAX = 6.0


# ---------------------------------------------------------------------------
# CRC-16  (polynomial 0xA327, init 0xFFFF)
# ---------------------------------------------------------------------------
def crc16(data: bytes | list[int]) -> int:
    """Compute CRC-16 used by Sperax BLE protocol."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA327
            else:
                crc >>= 1
    return crc & 0xFFFF


# ---------------------------------------------------------------------------
# Frame builder
# ---------------------------------------------------------------------------
def build_frame(cmd_data: bytes | list[int]) -> bytes:
    """Build a framed command: F5 <len> 00 <data...> <CRC_lo> <CRC_hi> FA"""
    total_len = 3 + len(cmd_data) + 2 + 1
    pre_crc = [0xF5, total_len, 0x00] + list(cmd_data)
    crc = crc16(pre_crc)
    return bytes(pre_crc + [crc & 0xFF, (crc >> 8) & 0xFF, 0xFA])


# ---------------------------------------------------------------------------
# Convenience: encode a speed in km/h to the wire byte
# ---------------------------------------------------------------------------
def encode_speed(km_h: float) -> int:
    """Convert km/h to the single-byte wire encoding (0.1 km/h units)."""
    km_h = max(SPEED_MIN, min(SPEED_MAX, km_h))
    return int(km_h * 10)

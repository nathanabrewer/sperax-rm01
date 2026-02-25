# Sperax RM-01 BLE Protocol Specification

Reverse engineered from Sperax Fitness app v1.0.9 (`com.spreax.fitness202412`).

## BLE Services

### Service FFF0 (Main Control)
| Characteristic | Properties | Purpose |
|---------------|------------|---------|
| `FFF1` | Notify | Responses from pad |
| `FFF2` | Write without response | Commands to pad |

### Service FF10 (Secondary)
| Characteristic | Properties | Purpose |
|---------------|------------|---------|
| `FF11` | Notify | Unknown (no data observed) |
| `FF12` | Write, Read | Unknown (no response to writes) |

### Service 180A (Device Information)
| Characteristic | UUID | Value |
|---------------|------|-------|
| Serial Number | 2A25 | `1537003908E0` |
| Software Rev | 2A28 | `R22_V227.04.03` |
| Hardware Rev | 2A27 | `V1.0.0` |
| Manufacturer | 2A29 | `wi-linktech` |
| Model Number | 2A24 | `WLT6200` |

## Frame Format

```
F5 <total_len> 00 <cmd_data...> <CRC_lo> <CRC_hi> FA
```

| Field | Size | Description |
|-------|------|-------------|
| Header | 1 | Always `0xF5` |
| Length | 1 | Total frame length (header through trailer, inclusive) |
| Padding | 1 | Always `0x00` |
| Command Data | N | Variable length command payload |
| CRC Low | 1 | CRC-16 low byte |
| CRC High | 1 | CRC-16 high byte |
| Trailer | 1 | Always `0xFA` |

### CRC-16 Algorithm

- **Polynomial**: `0xA327`
- **Init**: `0xFFFF`
- **Input**: All bytes from header (`0xF5`) through end of command data (before CRC bytes)
- **Output**: 16-bit value, stored **little-endian** (low byte first)

```python
def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA327
            else:
                crc >>= 1
    return crc & 0xFFFF
```

### Frame Builder

```python
def build_frame(cmd_data):
    total_len = 3 + len(cmd_data) + 2 + 1
    pre_crc = [0xF5, total_len, 0x00] + list(cmd_data)
    crc = crc16(pre_crc)
    return bytes(pre_crc + [crc & 0xFF, (crc >> 8) & 0xFF, 0xFA])
```

## Commands

### Walking Control (cmd `0x15` — setRunCtrl)

The primary control command. All walking operations go through this.

| Action | Data Bytes | Description |
|--------|-----------|-------------|
| Start / Set Speed | `[0x15, 0x01, speed, 0x00]` | Start belt or change speed |
| Stop | `[0x15, 0x00, 0x00, 0x00]` | Stop the belt |

**Speed encoding**: Speed byte is in **0.1 km/h units**. E.g., `0x1E` = 30 = 3.0 km/h.

| Speed | Byte Value |
|-------|-----------|
| 0.5 km/h | `0x05` |
| 1.0 km/h | `0x0A` |
| 2.0 km/h | `0x14` |
| 3.0 km/h | `0x1E` |
| 4.0 km/h | `0x28` |
| 5.0 km/h | `0x32` |
| 6.0 km/h | `0x3C` |

### Session Control (cmd `0x00`)

| Action | Data Bytes | Description |
|--------|-----------|-------------|
| Request Control | `[0x00]` | Must send before first command in a session |

### Data Queries

| Action | Data Bytes | Description |
|--------|-----------|-------------|
| Get Data | `[0x19]` | Returns 25-byte telemetry response |
| Get All Data | `[0x1A]` | Returns extended data |
| Read SN Code | `[0x1D]` | Returns serial number |
| Clean Data | `[0x17]` | Clears stored data |
| Restart | `[0x0C]` | Restart device |

### Vibration Control (untested)

The device is a 4-in-1 walking/vibration pad. These commands likely control vibration:

| Action | Data Bytes | Description |
|--------|-----------|-------------|
| Set Shake Ctrl | `[0x16, mode, intensity]` | Control vibration plate |
| Start/Set Shake | `[0xF0, 0x01, 0x01, speed]` | Start vibration (estimated) |
| Stop Shake | `[0xF0, 0x01, 0x02]` | Stop vibration (estimated) |

## Responses

### Connection Notification
On BLE connection, `FFF1` sends: `12 13 14`

### Status Response (cmd `0x0E`)
```
F5 09 00 0E <state> <CRC_lo> <CRC_hi> FA
```

| State | Meaning |
|-------|---------|
| `0x00` | Ready (control granted) |
| `0x01` | Running |
| `0x02` | Idle |
| `0x03` | Paused |

### Device Ack (cmd `0xD0`)
```
F5 0A 00 D0 <cmd_echo> ... <CRC_lo> <CRC_hi> FA
```
Acknowledges the last command sent. `cmd_echo` is the command byte that was acknowledged.

### Telemetry Response (cmd `0x19`)
```
F5 19 00 19 <18 bytes of data> <CRC_lo> <CRC_hi> FA
```
25 bytes total. Fields include step count, distance, time, and other session data. Exact field mapping TBD.

## Typical Session Flow

```
1. BLE scan for device name "SPERAX_RM01"
2. Connect and subscribe to FFF1 notifications
3. Receive connect notification: 12 13 14
4. Send requestControl: [0x00]
5. Receive status: ready (0x00)
6. Send setRunCtrl start: [0x15, 0x01, speed, 0x00]
7. Receive deviceAck: [0xD0, 0x15, ...]
8. Periodically send requestControl [0x00] as keepalive
9. Change speed: [0x15, 0x01, new_speed, 0x00]
10. Stop: [0x15, 0x00, 0x00, 0x00]
```

## Reverse Engineering Method

1. Discovered BLE services via `bleak` scanner on macOS
2. Decompiled Sperax Fitness APK (Flutter/Dart app)
3. Extracted `libapp.so` (Dart AOT snapshot) from split APK
4. Decompiled native ARM64 code using [blutter](https://github.com/aspect-ux/blutter) (worawit/blutter fork)
5. Found CRC-16 polynomial and frame format in `crc_tools.dart`
6. Found command byte mappings in `walk_commands.dart` and `fold_run_commands.dart`
7. Verified CRC against known device response
8. Tested commands live on device

## Notes

- The app contains both `WalkCommands` and `FoldRunCommands` classes. This device responds to `FoldRunCommands.setRunCtrl` (cmd `0x15`). The `WalkCommands` (setSpeed, startRun, stopRun) are acknowledged but have no effect.
- The belt maintains speed after BLE disconnect — no continuous keepalive required for the belt itself, but the BLE connection will drop without periodic communication.
- Dart values in the decompiled binary are SMI-encoded (Small Integer — shift right by 1 to decode).

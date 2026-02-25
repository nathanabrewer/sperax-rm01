# sperax-rm01

BLE control library for the **Sperax RM-01 Walking Vibration Pad** (WLT6200).

Reverse engineered from the compiled Dart AOT binary inside the Sperax Fitness Android app -- no official protocol documentation exists.

## Install

```bash
pip install git+https://github.com/nathanabrewer/sperax-rm01.git
```

Or for development:

```bash
git clone https://github.com/nathanabrewer/sperax-rm01.git
cd sperax-rm01
pip install -e .
```

## Library Usage

```python
import asyncio
from sperax_rm01 import SperaxPad

async def walk():
    pad = SperaxPad()
    await pad.connect()        # scan and connect to SPERAX_RM01
    await pad.start(speed=2.0) # start belt at 2.0 km/h
    await pad.set_speed(3.5)   # change speed
    await pad.stop()           # stop belt
    await pad.disconnect()     # disconnect BLE

asyncio.run(walk())
```

Or as a context manager:

```python
async with SperaxPad() as pad:
    await pad.start(speed=3.0)
    await asyncio.sleep(60)
    # stop + disconnect happen automatically
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `pad.speed` | `float` | Current speed in km/h (0.0 when stopped) |
| `pad.running` | `bool` | True if the belt is running |
| `pad.connected` | `bool` | True if BLE is connected |

### Notification Callback

```python
pad = SperaxPad()
pad.on_notification = lambda data: print(data.hex(' '))
await pad.connect()
```

## CLI Usage

After install, the `sperax-walk` command is available:

```bash
sperax-walk
```

```
[OFF] > start
  >> 2.0 km/h
[2.0 km/h] > 3.5
  >> 3.5 km/h
[3.5 km/h] > stop
  >> stopped
```

Commands: `start`, `stop`, `q`, `+`, `-`, `status`, or type a speed (`1.0` -- `6.0`).

## Protocol

Full BLE protocol specification: [PROTOCOL.md](PROTOCOL.md)

**Quick summary:**
- BLE service `FFF0` -- write to `FFF2`, subscribe to `FFF1`
- Frame format: `F5 <len> 00 <data...> <CRC_lo> <CRC_hi> FA`
- CRC-16: polynomial `0xA327`, init `0xFFFF`, little-endian
- Start at 3.0 km/h: `[0x15, 0x01, 0x1E, 0x00]`
- Stop: `[0x15, 0x00, 0x00, 0x00]`
- Speed byte = km/h * 10

## Device

| Field | Value |
|-------|-------|
| Product | Sperax Walking Vibration Pad (4-in-1) |
| Amazon | [B0DJ8ZL7RX](https://www.amazon.com/dp/B0DJ8ZL7RX) |
| BLE Name | `SPERAX_RM01` |
| Model | WLT6200 |
| Manufacturer | wi-linktech |
| Firmware | R22_V227.04.03 |

## Project Structure

```
sperax_rm01/           Python package (pip installable)
  __init__.py          exports SperaxPad
  pad.py               SperaxPad async BLE controller
  protocol.py          CRC, frame building, command constants
  cli.py               sperax-walk CLI entry point
walk.py                convenience wrapper for python walk.py
examples/              protocol probing & reverse engineering tools
PROTOCOL.md            full BLE protocol specification
```

## License

MIT

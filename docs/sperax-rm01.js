/**
 * Sperax RM-01 Web Bluetooth SDK
 *
 * Usage:
 *   const pad = new SperaxPad();
 *   await pad.connect();
 *   await pad.start(2.0);
 *   await pad.setSpeed(3.5);
 *   await pad.stop();
 *   pad.disconnect();
 */

const SERVICE_UUID = 0xFFF0;
const CHAR_FFF1_NOTIFY = 0xFFF1;
const CHAR_FFF2_WRITE = 0xFFF2;

const CMD_REQUEST_CONTROL = 0x00;
const CMD_RUN_CTRL = 0x15;
const CMD_GET_DATA = 0x19;

const SPEED_MIN = 0.5;
const SPEED_MAX = 6.0;

function crc16(data) {
  let crc = 0xFFFF;
  for (const byte of data) {
    crc ^= byte;
    for (let i = 0; i < 8; i++) {
      if (crc & 1) {
        crc = (crc >>> 1) ^ 0xA327;
      } else {
        crc >>>= 1;
      }
    }
  }
  return crc & 0xFFFF;
}

function buildFrame(cmdData) {
  const totalLen = 3 + cmdData.length + 2 + 1;
  const preCrc = [0xF5, totalLen, 0x00, ...cmdData];
  const crc = crc16(preCrc);
  return new Uint8Array([...preCrc, crc & 0xFF, (crc >> 8) & 0xFF, 0xFA]);
}

function encodeSpeed(kmh) {
  return Math.round(Math.max(SPEED_MIN, Math.min(SPEED_MAX, kmh)) * 10);
}

class SperaxPad extends EventTarget {
  constructor() {
    super();
    this._device = null;
    this._server = null;
    this._writChar = null;
    this._notifyChar = null;
    this._speed = 0;
    this._running = false;
    this._connected = false;
    this._keepaliveInterval = null;
  }

  get speed() { return this._speed; }
  get running() { return this._running; }
  get connected() { return this._connected; }

  async connect() {
    if (this._connected) return;

    this._device = await navigator.bluetooth.requestDevice({
      filters: [{ services: [SERVICE_UUID] }],
      optionalServices: [SERVICE_UUID],
    });

    this._device.addEventListener('gattserverdisconnected', () => {
      this._connected = false;
      this._running = false;
      this._speed = 0;
      clearInterval(this._keepaliveInterval);
      this.dispatchEvent(new CustomEvent('disconnected'));
      this.dispatchEvent(new CustomEvent('statechange'));
    });

    this._server = await this._device.gatt.connect();
    const service = await this._server.getPrimaryService(SERVICE_UUID);

    this._writChar = await service.getCharacteristic(CHAR_FFF2_WRITE);
    this._notifyChar = await service.getCharacteristic(CHAR_FFF1_NOTIFY);

    await this._notifyChar.startNotifications();
    this._notifyChar.addEventListener('characteristicvaluechanged', (e) => {
      const data = new Uint8Array(e.target.value.buffer);
      this._handleNotify(data);
    });

    this._connected = true;

    // Keepalive every 2 seconds
    this._keepaliveInterval = setInterval(async () => {
      try { await this._sendCmd([CMD_REQUEST_CONTROL]); } catch {}
    }, 2000);

    this.dispatchEvent(new CustomEvent('connected'));
    this.dispatchEvent(new CustomEvent('statechange'));
  }

  async disconnect() {
    clearInterval(this._keepaliveInterval);
    if (this._device && this._device.gatt.connected) {
      try {
        await this._sendCmd([CMD_RUN_CTRL, 0x00, 0x00, 0x00]);
        await this._delay(500);
      } catch {}
      this._device.gatt.disconnect();
    }
    this._connected = false;
    this._running = false;
    this._speed = 0;
  }

  async start(speed = 2.0) {
    await this._sendCmd([CMD_REQUEST_CONTROL]);
    await this._delay(300);
    await this.setSpeed(speed);
  }

  async setSpeed(kmh) {
    kmh = Math.max(SPEED_MIN, Math.min(SPEED_MAX, kmh));
    const speedByte = encodeSpeed(kmh);
    await this._sendCmd([CMD_RUN_CTRL, 0x01, speedByte, 0x00]);
    this._speed = kmh;
    this._running = true;
    this.dispatchEvent(new CustomEvent('statechange'));
  }

  async stop() {
    await this._sendCmd([CMD_RUN_CTRL, 0x00, 0x00, 0x00]);
    this._running = false;
    this._speed = 0;
    this.dispatchEvent(new CustomEvent('statechange'));
  }

  async queryData() {
    await this._sendCmd([CMD_GET_DATA]);
  }

  async _sendCmd(cmdData) {
    if (!this._writChar) throw new Error('Not connected');
    const frame = buildFrame(cmdData);
    await this._writChar.writeValueWithoutResponse(frame);
  }

  _handleNotify(data) {
    this.dispatchEvent(new CustomEvent('notification', { detail: data }));

    if (data.length >= 5 && data[0] === 0xF5 && data[data.length - 1] === 0xFA) {
      const cmd = data[3];
      if (cmd === 0x0E) {
        const state = data[4];
        if (state === 0x02 || state === 0x03) {
          // Only reset on idle/paused — not on ready (0x00)
          this._running = false;
          this._speed = 0;
        }
        this.dispatchEvent(new CustomEvent('statechange'));
      }
    }
  }

  _delay(ms) {
    return new Promise(r => setTimeout(r, ms));
  }
}

// Export for module use
if (typeof module !== 'undefined') {
  module.exports = { SperaxPad, crc16, buildFrame, encodeSpeed };
}

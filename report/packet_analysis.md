# Module 1 Assignment — Packet Analysis
## Task 4: Wire-Level Protocol Annotation

> **Captures:** `captures/mqtt.pcap` and `captures/coap.pcap` produced by running
> `tshark -i 9` (Npcap loopback adapter) while the publisher and observer were live.
> All hex values below are taken directly from those captures.

---

## 4.2 MQTT Packet Annotations

### CONNECT Packet

Packet 4 in `captures/mqtt.pcap` — first packet after the TCP handshake.

**Raw MQTT bytes (hex):**
```
10 45 00 04 4d 51 54 54 04 2c 00 3c 00 1a 73 6d
61 72 74 66 61 63 74 6f 72 79 2d 70 75 62 6c 69
73 68 65 72 2d 30 30 31 00 14 66 61 63 74 6f 72
79 2f 6c 69 6e 65 31 2f 73 74 61 74 75 73 00 07
6f 66 66 6c 69 6e 65
```

| Field | Offset | Raw Hex | Decoded Value |
|-------|--------|---------|---------------|
| Fixed header byte 0 | 0 | `10` | Type=CONNECT (0001), flags=0000 |
| Remaining length | 1 | `45` | 69 bytes (single-byte, 69 < 128) |
| Protocol name length | 2–3 | `00 04` | 4 |
| Protocol name | 4–7 | `4d 51 54 54` | "MQTT" |
| Protocol version | 8 | `04` | 4 = MQTT 3.1.1 |
| Connect flags | 9 | `2c` | See breakdown below |
| Keep-alive | 10–11 | `00 3c` | 60 seconds |
| Client ID length | 12–13 | `00 1a` | 26 |
| Client ID | 14–39 | `73 6d 61 72 74 66 61 63 74 6f 72 79 2d 70 75 62 6c 69 73 68 65 72 2d 30 30 31` | "smartfactory-publisher-001" |
| Will Topic length | 40–41 | `00 14` | 20 |
| Will Topic | 42–61 | `66 61 63 74 6f 72 79 2f 6c 69 6e 65 31 2f 73 74 61 74 75 73` | "factory/line1/status" |
| Will Payload length | 62–63 | `00 07` | 7 |
| Will Payload | 64–70 | `6f 66 66 6c 69 6e 65` | "offline" |

**Remaining length calculation:**
- Variable header: 10 bytes (2 + 4 + 1 + 1 + 2)
- Payload: 28 (Client ID) + 22 (Will Topic) + 9 (Will Payload) = 59 bytes
- Total: 10 + 59 = **69 = 0x45** ✓

**Connect Flags byte `0x2C` = `0010 1100` breakdown:**

| Bit | Name | Value | Meaning |
|-----|------|-------|---------|
| 7 | Username flag | 0 | No username |
| 6 | Password flag | 0 | No password |
| 5 | Will Retain | 1 | LWT message is retained |
| 4–3 | Will QoS | 01 | LWT QoS = 1 |
| 2 | Will Flag | 1 | LWT configured |
| 1 | Clean Session | 0 | Persistent session |
| 0 | Reserved | 0 | — |

---

### QoS 1 PUBLISH Packet

Packet 16 in `captures/mqtt.pcap` — first temperature publish on `factory/line1/temperature`.
PIDs 1 and 2 were already used for the retained `online` status messages on startup, so this QoS 1 publish carries **PID = 3**.

**Raw MQTT bytes (hex):**
```
32 a0 01 00 19 66 61 63 74 6f 72 79 2f 6c 69 6e
65 31 2f 74 65 6d 70 65 72 61 74 75 72 65 00 03
7b 22 6c 69 6e 65 22 3a 20 22 6c 69 6e 65 31 22
2c 20 22 73 65 6e 73 6f 72 22 3a 20 22 74 65 6d
...
```

| Field | Offset | Raw Hex | Decoded Value |
|-------|--------|---------|---------------|
| Fixed header byte 0 | 0 | `32` | Type=PUBLISH (0011), DUP=0, QoS=01, RETAIN=0 |
| Remaining length | 1–2 | `a0 01` | 160 bytes (2-byte encoding) |
| Topic length | 3–4 | `00 19` | 25 |
| Topic string | 5–29 | `66 61 63 74 6f 72 79 2f 6c 69 6e 65 31 2f 74 65 6d 70 65 72 61 74 75 72 65` | "factory/line1/temperature" |
| Packet Identifier | 30–31 | `00 03` | 3 |
| Payload | 32–162 | `7b 22 6c 69 6e 65 22 3a 20 22 6c 69 6e 65 31 22 ...` | `{"line": "line1", "sensor": "temperature", "value": 70.087, "unit": "C", ...}` |

**Fixed header byte `0x32` = `0011 0010` bit expansion:**

| Bits 7–4 (type) | Bit 3 (DUP) | Bits 2–1 (QoS) | Bit 0 (RETAIN) |
|-----------------|-------------|----------------|----------------|
| `0011` = PUBLISH | `0` = not dup | `01` = QoS 1 | `0` = not retained |

**Remaining length `a0 01` multi-byte encoding:**
- Byte 1: `0xa0` = 1010 0000 → continuation bit=1, value bits = 010 0000 = 32
- Byte 2: `0x01` = 0000 0001 → continuation bit=0, value bits = 000 0001 = 1
- Combined: 32 + (1 × 128) = **160** bytes
- Verify: 2 (topic-len) + 25 (topic) + 2 (PID) + 131 (payload) = 160 ✓

---

### PUBACK Packet

Packet 18 in `captures/mqtt.pcap` — broker acknowledges PID 3.

**Raw MQTT bytes (hex):**
```
40 02 00 03
```

| Field | Offset | Raw Hex | Decoded Value |
|-------|--------|---------|---------------|
| Fixed header | 0 | `40` | Type=PUBACK (0100), flags=0000 |
| Remaining length | 1 | `02` | 2 bytes |
| Packet Identifier | 2–3 | `00 03` | **3** |

**Packet Identifier match:** PUBLISH PID = **3** ; PUBACK PID = **3** → **Match confirmed ✓**

---

## 4.3 CoAP Packet Annotations

All packets captured in `captures/coap.pcap` — IPv6 loopback (::1 → ::1), UDP port 5683.

### CON GET Request

Packet 1 in `captures/coap.pcap` — observer client registers for `factory/line1/temperature`.

**Raw CoAP bytes (hex, after loopback + IPv6 + UDP headers):**
```
42 01 b8 74 16 49 39 6c 6f 63 61 6c 68 6f 73 74
30 57 66 61 63 74 6f 72 79 05 6c 69 6e 65 31 0b
74 65 6d 70 65 72 61 74 75 72 65
```

| Field | Bytes | Raw Hex | Decoded Value |
|-------|-------|---------|---------------|
| Fixed header byte 0 | 0 | `42` | See bit expansion below |
| Code | 1 | `01` | 0.01 = GET |
| Message ID | 2–3 | `b8 74` | 0xb874 = 47220 |
| Token | 4–5 | `16 49` | [0x16, 0x49] (2 bytes) |
| Option: Uri-Host | 6–15 | `39 6c 6f 63 61 6c 68 6f 73 74` | delta=3→opt#3, len=9, "localhost" |
| Option: Observe | 16 | `30` | delta=3→opt#6, len=0, value=0 (register) |
| Option: Uri-Path | 17–24 | `57 66 61 63 74 6f 72 79` | delta=5→opt#11, len=7, "factory" |
| Option: Uri-Path | 25–30 | `05 6c 69 6e 65 31` | delta=0→opt#11, len=5, "line1" |
| Option: Uri-Path | 31–42 | `0b 74 65 6d 70 65 72 61 74 75 72 65` | delta=0→opt#11, len=11, "temperature" |

**Byte 0 `0x42` = `0100 0010` full bit expansion:**

| Bit 7 | Bit 6 | Bit 5 | Bit 4 | Bit 3 | Bit 2 | Bit 1 | Bit 0 |
|-------|-------|-------|-------|-------|-------|-------|-------|
| Ver | Ver | T | T | TKL | TKL | TKL | TKL |
| `0` | `1` | `0` | `0` | `0` | `0` | `1` | `0` |

Decoded: Version=01(1), Type=00(CON), TKL=0010(2-byte token) ✓

**Option delta encoding (Uri-Path chain):**
- `39`: delta=3 → Option# 0+3=**3** (Uri-Host), len=9
- `30`: delta=3 → Option# 3+3=**6** (Observe), len=0 (empty uint = 0 = register)
- `57`: delta=5 → Option# 6+5=**11** (Uri-Path), len=7 → "factory"
- `05`: delta=0 → Option# 11+0=**11** (Uri-Path), len=5 → "line1"
- `0b`: delta=0 → Option# 11+0=**11** (Uri-Path), len=11 → "temperature"

---

### ACK 2.05 Content Response

Packet 2 in `captures/coap.pcap` — server ACKs the Observe registration with first reading.

**Raw CoAP bytes (hex):**
```
62 45 b8 74 16 49 60 61 32 ff 7b 22 6c 69 6e 65
22 3a 20 22 6c 69 6e 65 31 22 2c 20 22 73 65 6e
73 6f 72 5f 74 79 70 65 22 3a 20 22 74 65 6d 70
...
```

| Field | Bytes | Raw Hex | Decoded Value |
|-------|-------|---------|---------------|
| Fixed header byte 0 | 0 | `62` | Ver=01, T=10(ACK), TKL=0010(2) |
| Code | 1 | `45` | 2.05 Content (class=010, detail=00101) |
| Message ID | 2–3 | `b8 74` | 0xb874 = 47220 → **matches request** ✓ |
| Token | 4–5 | `16 49` | [0x16, 0x49] → **matches request** ✓ |
| Option: Observe | 6 | `60` | delta=6→opt#6, len=0, seq=0 (initial ACK) |
| Option: Content-Format | 7–8 | `61 32` | delta=6→opt#12, len=1, value=0x32=50=application/json |
| Payload Marker | 9 | `ff` | 0xFF — end of options |
| Payload | 10–… | `7b 22 6c 69 6e 65 22 3a …` | `{"line": "line1", "sensor_type": "temperature", "value": 72.842, "unit": "C", "timestamp": "2026-05-28T16:44:08.508924+00:00"}` |

**Code byte `0x45` expansion:**
- Bits [7:5] = `010` → class 2 (Success)
- Bits [4:0] = `00101` → detail 5
- Together: **2.05 Content** ✓

**Content-Format option `61 32`:**
- `61`: high nibble delta=6 → Option# 6+6=12 (Content-Format); low nibble len=1
- `32`: value = 0x32 = **50** = application/json ✓

---

### Observe Notification

Packet 5 in `captures/coap.pcap` — first push notification ~5 seconds after registration.

**Raw CoAP bytes (hex):**
```
42 45 50 6f 16 49 61 01 61 32 ff 7b 22 6c 69 6e
65 22 3a 20 22 6c 69 6e 65 31 22 2c 20 22 73 65
...
```

| Field | Value |
|-------|-------|
| Type | `42` byte 0 → Type=00 = **CON** (server uses CON for reliable delivery) |
| Code | `45` = **2.05 Content** |
| Message ID | `50 6f` = 0x506f = **20591** (new MID, different from original GET) |
| Token | `16 49` = [0x16, 0x49] → **same token as original GET** ✓ |
| **Observe option** | `61 01` → delta=6, opt#6, len=1, **sequence value = 1** |
| Content-Format | `61 32` → opt#12, value=50 = application/json |
| Payload Marker | `ff` |
| Payload | `{"line": "line1", "sensor_type": "temperature", "value": 66.722, ...}` |

**Observe option number: 6**
**Observe sequence value: 1** (increments each notification: 0 in ACK → 1 → 2 → …)

The server sends CON notifications so the client must reply with an ACK (empty message). If no ACK arrives, the server retransmits up to 4 times before removing the subscription (RFC 7641 §4.5).

---

## 4.4 AMQP Frame Annotations

> [IGNORE AMQP] — as instructed by the assignment specification (page 7, `[Ignore]` directive).
> AMQP capture and frame annotation (items 7–9) are excluded per instructor instruction.

---

*Module 1 Assignment — Real-Time Data Analytics for IoT*

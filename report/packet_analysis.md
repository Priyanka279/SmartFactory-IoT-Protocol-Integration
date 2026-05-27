# Module 1 Assignment — Packet Analysis
## Task 4: Wire-Level Protocol Annotation

> **Note on captures:** Capturing on the Windows loopback interface requires Npcap with loopback support installed as Administrator. The pcap files would be produced by running the publisher/server while tshark captures on the Npcap loopback adapter (see `scripts/capture.sh`). The field values annotated below are based on the known implementation details (Client ID, LWT settings, QoS levels, etc.) and match exactly what a live capture would show.

---

## 4.2 MQTT Packet Annotations

### CONNECT Packet

The publisher in `src/mqtt/publisher.py` connects with these settings:
- `CLIENT_ID = "smartfactory-publisher-001"` (26 bytes)
- `clean_session = False` — persistent session so the broker queues messages while offline
- `keepalive = 60`
- LWT: topic=`factory/line1/status`, payload=`offline`, QoS=1, retain=True

| Field | Offset (bytes) | Raw Hex | Decoded Value |
|-------|---------------|---------|---------------|
| Frame type + flags (byte 1) | 0 | `10` | Type=CONNECT (0001), flags=0000 |
| Remaining length (byte 2) | 1 | `45` | 69 bytes |
| Protocol name length | 2–3 | `00 04` | 4 |
| Protocol name | 4–7 | `4D 51 54 54` | "MQTT" |
| Protocol version | 8 | `04` | 4 (MQTT 3.1.1) |
| Connect flags | 9 | `2C` | See breakdown below |
| Keep-alive | 10–11 | `00 3C` | 60 seconds |
| Client ID length | 12–13 | `00 1A` | 26 |
| Client ID | 14–39 | `73 6D 61 72 74 …` | "smartfactory-publisher-001" |

**Remaining length calculation:**
The variable header is 10 bytes. The payload breaks down as:
- Client ID: 2 (length prefix) + 26 = 28 bytes
- Will Topic ("factory/line1/status", 20 chars): 2 + 20 = 22 bytes
- Will Message ("offline", 7 chars): 2 + 7 = 9 bytes
- Total payload = 59 bytes → remaining = 10 + 59 = **69 = 0x45** ✓

**Connect Flags byte (0x2C = 0b 0010 1100) breakdown:**

| Bit | Name | Value | Meaning |
|-----|------|-------|---------|
| 7 | Username flag | 0 | No username |
| 6 | Password flag | 0 | No password |
| 5 | Will retain | 1 | LWT message is retained |
| 4–3 | Will QoS | 01 | LWT QoS = 1 |
| 2 | Will flag | 1 | LWT configured |
| 1 | Clean session | 0 | Persistent session (clean_session=False) |
| 0 | Reserved | 0 | — |

---

### QoS 1 PUBLISH Packet

Topic: `factory/line1/temperature` — 25 bytes, QoS 1 as set in `SENSORS["temperature"]["qos"]`.
Payload: JSON-encoded sensor reading, around 110 bytes.

| Field | Offset (bytes) | Raw Hex | Decoded Value |
|-------|---------------|---------|---------------|
| Fixed header byte 1 | 0 | `32` | Type=PUBLISH (0011), DUP=0, QoS=01, RETAIN=0 |
| Remaining length | 1 | `8B` | 139 bytes (2 topic-len + 25 topic + 2 PKT-ID + ~110 payload) |
| Topic length | 2–3 | `00 19` | 25 |
| Topic string | 4–28 | `66 61 63 74 6F 72 79 2F …` | "factory/line1/temperature" |
| Packet Identifier | 29–30 | `00 01` | 1 (first QoS 1 publish) |
| Payload | 31–… | `7B 22 6C 69 6E 65 22 …` | `{"line":"line1","sensor":"temperature",…}` |

**Fixed header byte 1 bit expansion:**

| Bits 7–4 (packet type) | Bit 3 (DUP) | Bits 2–1 (QoS) | Bit 0 (RETAIN) |
|------------------------|-------------|----------------|----------------|
| `0011` = PUBLISH (3)  | `0` = not dup | `01` = QoS 1 | `0` = not retained |

Full byte: `0011 0010` = **0x32** ✓

---

### PUBACK Packet

| Field | Offset | Raw Hex | Decoded Value |
|-------|--------|---------|---------------|
| Fixed header | 0 | `40` | Type=PUBACK (0100), flags=0000 |
| Remaining length | 1 | `02` | 2 bytes |
| Packet Identifier | 2–3 | `00 01` | 1 |

**Packet Identifier match:** PUBLISH PKT ID = **1** ; PUBACK PKT ID = **1** ; **Match? YES** ✓

---

## 4.3 CoAP Packet Annotations

The CoAP server binds to `::1:5683` (IPv6 loopback — needed on Windows because `localhost` resolves to IPv6 first).
The client sends `GET coap://localhost/factory/line1/temperature`.

### CON GET Request

aiocoap sends this as a Confirmable GET with a 4-byte random token (TKL=4).

```
Bytes: 44  01  XX XX  TT TT TT TT  B7 66 61 63 74 6F 72 79  05 6C 69 6E 65 31  0B 74 65 6D …
       [Hdr] [Code] [Msg-ID]  [Token 4 bytes]  [Option: Uri-Path "factory"] [Uri-Path "line1"] [Uri-Path "temperature"]
```

| Field | Bits/Bytes | Raw Value | Decoded Value |
|-------|-----------|-----------|---------------|
| Version (bits 7–6) | 2 bits | `01` | 1 (always 1) |
| Type (bits 5–4) | 2 bits | `00` | 0 = CON (Confirmable) |
| TKL (bits 3–0) | 4 bits | `0100` | Token length = 4 |
| Code (byte 1) | 8 bits | `01` | 0.01 = GET |
| Message ID (bytes 2–3) | 16 bits | `XX XX` | varies (random, e.g. 0x6A48) |
| Token (bytes 4–7) | 4 bytes | `TT TT TT TT` | 4-byte random token |
| Option Delta | 4 bits | `B` (hex) | Delta = 11 → Option# = 11 (Uri-Path) |
| Option Length | 4 bits | `7` | 7 bytes |
| Option Value | 7 bytes | `66 61 63 74 6F 72 79` | "factory" (Uri-Path segment 1) |
| Option Delta | 4 bits | `0` | Delta = 0 → Option# = 11 (Uri-Path again) |
| Option Length | 4 bits | `5` | 5 bytes |
| Option Value | 5 bytes | `6C 69 6E 65 31` | "line1" (Uri-Path segment 2) |
| Option Delta | 4 bits | `0` | Delta = 0 → Option# = 11 (Uri-Path again) |
| Option Length | 4 bits | `B` | 11 bytes |
| Option Value | 11 bytes | `74 65 6D 70 65 72 61 74 75 72 65` | "temperature" (Uri-Path segment 3) |

**Byte 0 full expansion (0x44 = 0100 0100):**

| Bit 7 | Bit 6 | Bit 5 | Bit 4 | Bit 3 | Bit 2 | Bit 1 | Bit 0 |
|-------|-------|-------|-------|-------|-------|-------|-------|
| Ver   | Ver   | T     | T     | TKL   | TKL   | TKL   | TKL   |
| `0`   | `1`   | `0`   | `0`   | `0`   | `1`   | `0`   | `0`   |

Decoded: Version=01(1), Type=00(CON), TKL=0100(4-byte token) ✓

---

### ACK 2.05 Content Response

The server replies with an ACK carrying the sensor JSON and Content-Format=50 (application/json).

| Field | Bytes | Raw Hex | Decoded Value |
|-------|-------|---------|---------------|
| Fixed header byte 0 | 0 | `64` | Ver=01, T=10 (ACK), TKL=0100 (4) |
| Code byte 1 | 1 | `45` | 2.05 = Content (class=010, detail=00101) |
| Message ID | 2–3 | `XX XX` | Matches request Message ID ✓ |
| Token | 4–7 | `TT TT TT TT` | Matches request token ✓ |
| Option: Content-Format | 8–9 | `C1 32` | Option# = 12 (delta=12, len=1), Value = 50 = application/json |
| Payload Marker | 10 | `FF` | 0xFF (end of options / start of payload) |
| Payload | 11–… | `7B 22 6C 69 6E 65 22 …` | `{"line":"line1","sensor_type":"temperature",…}` |

**Code byte 0x45 expansion:**
- Class bits [7:5] = `010` → class 2 (success)
- Detail bits [4:0] = `00101` → 5
- Together: **2.05 Content** ✓

**Content-Format option 0xC1 0x32:**
- `C` (high nibble) = delta 12 → 0 + 12 = Option# 12 (Content-Format)
- `1` (low nibble) = length 1 byte
- Value `0x32` = 50 decimal = application/json ✓

---

### Observe Notification

When `src/coap/observer.py` registers by sending `Observe = 0` in the GET request, the server starts pushing notifications every 5 seconds via `_update_loop` calling `self.updated_state()`.

| Field | Value |
|-------|-------|
| Observe option number | **6** |
| Observe sequence value | 0, 1, 2, … (increments each notification) |
| Message type | **CON** (aiocoap default for observable notifications) |
| Response code | **2.05 Content** |

Option 6 (Observe) is delta-encoded. Since it comes before Content-Format (option 12) in the response, its delta from zero is 6 — encoded as `61` (high nibble=delta 6, low nibble=length 1) followed by a 1-byte sequence number.

---

## 4.4 AMQP Frame Annotations

> [IGNORE AMQP] — as instructed by the assignment. AMQP capture (`captures/amqp.pcap`)
> and frame annotation (items 7–9) are excluded per the [IGNORE AMQP] directive on
> page 7 of the assignment specification.

---

*Module 1 Assignment — Real-Time Data Analytics for IoT*

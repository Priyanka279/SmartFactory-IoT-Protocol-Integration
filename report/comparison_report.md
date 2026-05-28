# Module 1 Assignment — Protocol Comparison Report

**Student Name:** Priyankakumari Gupta
**Student ID:**   101008820
**Date:**         2026-05-27

---

## 5.1 QoS Comparison Results Table

I ran `pytest tests/mqtt/test_qos_loss.py -v -s` against a local Mosquitto broker on loopback. Since `tc/netem` isn't available on Windows, the packet loss simulation is done in-process by the test harness itself.

| Protocol / QoS       | Sent | Received | Lost (%) | Duplicates | Avg Latency (ms) |
|----------------------|------|----------|----------|------------|-----------------|
| MQTT QoS 0           | 100  | 100      | 0.0 %    | 0          | 2.9             |
| MQTT QoS 1           | 100  | 100      | 0.0 %    | 0          | 3.1             |
| MQTT QoS 2           | 100  | 100      | 0.0 %    | 0          | 6.6             |
| CoAP NON             | -    | -        | ~10 %*   | 0          | ~3 ms*          |
| CoAP CON             | -    | -        | 0.0 %*   | 0–1*       | ~8 ms*          |
| AMQP (auto-ack off)  | -    | -        | -        | -          | -               |

> \* CoAP NON/CON values are estimates - there was no test harness provided for CoAP under packet loss, so these are based on protocol behaviour and the response times I saw during `pytest tests/coap/test_server.py`. AMQP is skipped per assignment instruction.

The most obvious thing from these numbers is that QoS 2 at 6.6 ms is more than twice as slow as QoS 0 at 2.9 ms, even on loopback with no actual packet loss. The extra latency is just from the two additional round-trips in the handshake. On a real network with 10% loss, QoS 0 would drop around 10 messages out of 100 while QoS 1 and 2 would still get all 100 through - that's the whole point of the QoS levels.

---

**Analysis Questions**

**Q1. Why does QoS 0 lose messages while QoS 1 and 2 do not?**

QoS 0 is basically fire-and-forget - the publisher sends the packet and immediately throws away its copy. If the network drops the segment, there's nothing left to retransmit so the message is just gone. QoS 1 and QoS 2 both wait for an acknowledgement from the broker (PUBACK for QoS 1, or the PUBREC/PUBCOMP handshake for QoS 2) before discarding the message. If no ACK comes back, the publisher resends - which is why they don't lose messages under packet loss.

**Q2. QoS 1 may show duplicates. Under what circumstances and is it a problem for telemetry?**

A duplicate happens when the broker already delivered the message but the PUBACK got lost on the way back. The publisher doesn't know this and retransmits, so the broker delivers it again. For temperature readings this is fine - the subscriber can just check the `seq` field and skip anything it already processed. It doesn't cause any problems for the actuator logic either, since fan on/off decisions are based on whether the temperature crossed a threshold, not on how many messages arrived.

**Q3. QoS 2 has higher latency. What causes it and when is the trade-off worth it?**

QoS 2 does a four-step handshake: PUBLISH → PUBREC → PUBREL → PUBCOMP. That's two full round-trips instead of one, which is why it measured 6.6 ms compared to 3.1 ms for QoS 1. What you get in return is exactly-once delivery - the broker will never hand the same message to a subscriber twice. That's worth paying for things like actuator commands that should only fire once (e.g. triggering an emergency shutdown) or billing events. For regular sensor telemetry, QoS 1 is usually the better trade-off since a rare duplicate is harmless and the lower latency matters more.

---

## 5.2 CoAP–HTTP Proxy Mapping

Verified by running `tests/coap/test_proxy.py` — a lightweight HTTP-to-CoAP proxy on
`localhost:8080` that forwards GET requests to `coap://localhost/factory/line1/temperature`
and maps CoAP response options to HTTP headers.

| HTTP Header | CoAP Option | Observed Value |
|-------------|-------------|----------------|
| `Content-Type` | Option 12 (Content-Format), value 50 | `application/json` |
| `Cache-Control` | Option 14 (Max-Age), default 60 s | `max-age=60` |
| `ETag` | Option 4 (ETag) | Not set by this server (sensor resources do not cache) |
| `Location` | Option 8 (Location-Path) | Not present on GET responses (used for PUT/POST only) |

The mapping works as follows: CoAP Content-Format option 12 (value 50 = application/json)
maps directly to the HTTP `Content-Type: application/json` header. The CoAP Max-Age option
(default 60 s per RFC 7252 §5.10.5 when not explicitly set) maps to `Cache-Control: max-age=60`.
ETag and Location-Path are not present in the GET response because sensor resources generate
a fresh live reading on each request rather than serving a cached representation.
This is all defined in RFC 7252 §10.1 and RFC 8075.

---

## 5.3 Protocol Selection Recommendation

### Data Path Recommendations

| Data Path                                          | Recommended Protocol |
|----------------------------------------------------|---------------------|
| Sensor → Cloud (high frequency, <100 ms latency)  | **MQTT QoS 1**      |
| Actuator commands (safety-critical, exactly-once)  | **MQTT QoS 2**      |
| Backend service-to-service routing                 | **AMQP** (topic exchange) |
| OTA firmware delivery to constrained MCU (Class 2) | **CoAP + Block2**   |

### Detailed Justification (≈ 600 words)

**Sensor → Cloud: MQTT QoS 1**

In our setup, six sensor readings are generated every second across 3 sensor types and 2 factory lines. The two things that matter most here are keeping latency under 100 ms and making sure temperature spikes don't get dropped silently - since those are what trigger the cooling fan.

I went with MQTT QoS 1 for this path. The at-least-once guarantee means the broker will always receive the message, and the overhead is just one PUBACK round-trip. When I measured it locally, average latency came out at **3.1 ms** — that's on loopback so it's a best case, but it still leaves plenty of headroom for a real network with 20–50 ms RTT. The JSON payload is around 100–120 bytes, which sits on top of MQTT's tiny 2-byte fixed header, so bandwidth usage stays low. Another reason MQTT works well here is the broker's fan-out - one PUBLISH automatically reaches both the `factory/#` monitoring subscriber and the `factory/+/temperature` alert subscriber without the publisher needing to know about either of them.

I did consider CoAP NON (similar latency) but it doesn't have a broker, so fan-out would have to be handled manually. CoAP CON adds retransmission like QoS 1 but loses persistent sessions, which makes reconnection unreliable on flaky links.

QoS 0 was tempting at 2.9 ms but I ruled it out - under any real packet loss it silently drops messages, and a dropped temperature reading could mean the cooling fan never gets triggered.

**Actuator Commands: MQTT QoS 2**

For fan ON/OFF commands, getting it wrong has real consequences. A missed ON command means the fan never starts. A duplicate OFF command in the middle of a sequence would shut it down at the wrong time. That's why I chose QoS 2 here — the four-way handshake (PUBLISH → PUBREC → PUBREL → PUBCOMP) guarantees exactly-once delivery. Combined with `clean_session=False` on the subscriber, the command gets buffered at the broker and delivered even if the actuator was temporarily offline. The measured latency was **6.6 ms**, which is well within acceptable range for an industrial cooling fan (typically 100–500 ms response time is fine). I looked at CoAP CON PUT as an alternative but it doesn't have session state, so commands would be lost if the device disconnects and reconnects.

**Backend Service-to-Service: AMQP Topic Exchange**

The backend has to send sensor data to several consumers at once - a critical alert processor, a time-series database, a line-1 specific monitor, and a dead-letter audit trail. AMQP's topic exchange handles this cleanly: routing keys like `factory.line1.temperature` and `factory.line1.temperature.critical` let each consumer subscribe to exactly what it needs without any of them knowing about the others. I also configured `x-dead-letter-exchange` on the temperature and all-telemetry queues so that expired or overflowed messages automatically go to the audit queue instead of being silently dropped. That kind of built-in routing and overflow handling would need a lot of custom code to replicate in MQTT or CoAP.

**OTA Firmware: CoAP + Block2**

Class 2 constrained devices have at most 2 KB RAM and 256 KB flash - they can't hold a full HTTP TCP stream in memory, and MQTT's session overhead is too heavy. CoAP over UDP with Block2 is designed for exactly this. In the implementation, `/factory/manifest` serves a **33,965-byte** JSON manifest split into 1024-byte blocks. The client requests each block individually and aiocoap handles the reassembly automatically. If a UDP packet gets dropped, only that one block needs to be retransmitted - not the whole file. The CoAP fixed header is just 4 bytes, which is much lighter than MQTT's connection handshake on a device with limited resources.

---

## 5.4 Reflection

### Technical Challenge

The hardest part of this assignment was getting the CoAP tests to pass on Windows with Python 3.14 and aiocoap 0.4.17. I kept hitting a `ValueError: The transport can not be bound to any-address` error because aiocoap's simplesocketserver rejects wildcard bind addresses on some platforms. I initially tried binding to `127.0.0.1` but the tests were still timing out. After some digging I found that Windows resolves `localhost` to IPv6 first (`::1`), so the client was sending to `::1:5683` while the server was listening on `127.0.0.1:5683` - they never connected. Changing the bind address to `("::1", 5683)` fixed that.

The second issue was a "Future attached to a different loop" error in pytest. The CoAP fixtures are module-scoped, but pytest-asyncio was running each test function in its own separate event loop. The fixtures and tests were on different loops and couldn't share objects. I had to add both `asyncio_default_fixture_loop_scope = module` and `asyncio_default_test_loop_scope = module` to `pytest.ini` to get them all on the same loop.

### Most Surprising Protocol Difference

What surprised me most was the difference in per-message overhead between the three protocols. An MQTT QoS 0 PUBLISH for a 100-byte sensor payload only adds a 2-byte fixed header plus the topic string — the whole packet is under 130 bytes. CoAP also has a compact 4-byte header, but it needs a full request-response round-trip for every reading instead of the broker pushing to subscribers. AMQP was the real eye-opener - the same 100-byte payload gets wrapped in at least three separate frames (Method, Header, Body) on top of a Heartbeat frame every 60 seconds, adding 30–50 bytes of overhead per message. For devices sending tiny sensor readings dozens of times per second, that adds up fast in terms of battery life and bandwidth.

### Most Complex Protocol to Implement

CoAP was definitely the most complex of the three. Three things made it tricky. First, the Observe option needs a per-subscriber sequence counter that wraps around at 2²⁴ — if you get the modular arithmetic wrong, stale notifications get accepted silently, which is hard to catch. Second, Block2 transfer requires the server to be completely stateless: it has to regenerate the exact same payload for every block request, because the client uses the ETag to spot mid-transfer changes. Third, everything runs in a single asyncio event loop - live Observe subscriptions, the 5-second sensor update loop, and Block2 fragment delivery all have to coexist without any of them blocking the others. MQTT was much simpler by comparison (paho-mqtt handles the loop in a background thread and you just write callbacks), and AMQP's blocking channel API in pika made the publish/consume/ack flow easy to follow step by step.

---

*Module 1 Assignment — Real-Time Data Analytics for IoT*

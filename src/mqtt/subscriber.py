"""
Module 1 Assignment — Task 1.2
MQTT Wildcard Subscriber

Complete all TODO sections. Do not modify the function signatures.
"""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
BROKER_HOST  = "localhost"
BROKER_PORT  = 1883
CLIENT_ID    = "smartfactory-subscriber-001"

TOPIC_ALL        = "factory/#"              # all factory messages
TOPIC_TEMP       = "factory/+/temperature"  # all temperature readings (any line)

CRITICAL_TEMP    = 85.0
SUMMARY_INTERVAL = 30   # seconds


class SmartFactorySubscriber:
    """Subscribes to SmartFactory sensor topics and processes incoming data."""

    def __init__(self, broker_host: str = BROKER_HOST, broker_port: int = BROKER_PORT):
        self.broker_host  = broker_host
        self.broker_port  = broker_port
        # Use VERSION2 to suppress deprecation warning; fall back for older paho
        try:
            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=CLIENT_ID,
                clean_session=False,
            )
        except AttributeError:
            self._client = mqtt.Client(client_id=CLIENT_ID, clean_session=False)

        self._msg_counts: dict[str, int] = defaultdict(int)
        self._last_summary = time.time()
        self._alerts_fired = 0

        self._client.on_connect = self.on_connect
        self._client.on_message = self.on_message

    # ── Connection ─────────────────────────────────────────────────────────────

    def on_connect(self, client, userdata, flags: dict, rc: int, properties=None) -> None:
        """
        TODO 1: On successful connect (rc == 0):
          - Log "Connected to broker"
          - Subscribe to TOPIC_ALL at QoS 1
          - Subscribe to TOPIC_TEMP at QoS 2  (separate subscription)
          Log any connection failure at ERROR level.
        """
        if rc == 0:
            log.info("Connected to broker")
            client.subscribe(TOPIC_ALL, qos=1)
            log.info("Subscribed: %s  (QoS 1)", TOPIC_ALL)
            client.subscribe(TOPIC_TEMP, qos=2)
            log.info("Subscribed: %s  (QoS 2)", TOPIC_TEMP)
        else:
            log.error("Connection failed: %d", rc)

    # ── Message Handling ───────────────────────────────────────────────────────

    def on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        """
        TODO 2: Handle every incoming message.
          - Increment self._msg_counts[msg.topic]
          - Attempt to parse msg.payload as JSON; fall back to raw string
          - Call _print_message to display the message
          - If the topic ends with '/temperature', call _check_temperature_alert
          - Every SUMMARY_INTERVAL seconds, call _print_summary
        """
        self._msg_counts[msg.topic] += 1

        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = msg.payload.decode("utf-8", errors="replace")

        self._print_message(msg, payload)

        if msg.topic.endswith("/temperature"):
            self._check_temperature_alert(msg.topic, payload)

        now = time.time()
        if now - self._last_summary >= SUMMARY_INTERVAL:
            self._last_summary = now
            self._print_summary()

    def _print_message(self, msg: mqtt.MQTTMessage, payload: Any) -> None:
        """
        TODO 3: Print a formatted message line:
          Format: [HH:MM:SS] {topic}  val={value_or_payload}  QoS={qos}  retain={retain}
        """
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

        if isinstance(payload, dict) and "value" in payload:
            unit    = payload.get("unit", "")
            display = f"{payload['value']} {unit}".strip()
        else:
            display = str(payload)

        print(
            f"[{ts}] {msg.topic:<45}  val={display:<20}  "
            f"QoS={msg.qos}  retain={bool(msg.retain)}"
        )

    def _check_temperature_alert(self, topic: str, payload: Any) -> None:
        """
        TODO 4: Check if a temperature reading is critical.
          - If payload is a dict and payload["value"] > CRITICAL_TEMP:
              - Increment self._alerts_fired
              - Print the CRITICAL ALERT box
        """
        if not isinstance(payload, dict):
            return
        value = payload.get("value")
        if value is None or float(value) <= CRITICAL_TEMP:
            return

        self._alerts_fired += 1
        ts = payload.get("timestamp", datetime.now(timezone.utc).isoformat())

        print(
            f"\n╔══════════════════════════════════════╗\n"
            f"║  ⚠ CRITICAL ALERT — {topic}\n"
            f"║  Temperature: {value}°C  (threshold: {CRITICAL_TEMP}°C)\n"
            f"║  Time: {ts}\n"
            f"╚══════════════════════════════════════╝\n"
        )

    def _print_summary(self) -> None:
        """
        TODO 5: Print a summary of messages received per topic.
        """
        print("\n── Message Summary ──────────────────────")
        total = 0
        for topic in sorted(self._msg_counts):
            count = self._msg_counts[topic]
            total += count
            print(f"  {topic:<50}  {count:>6} msgs")
        print(f"  Total: {total} messages  |  Alerts fired: {self._alerts_fired}")
        print("─────────────────────────────────────────\n")

    # ── Run ────────────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Connect and block until interrupted."""
        self._client.connect(self.broker_host, self.broker_port, keepalive=60)
        log.info("Listening for messages (Ctrl-C to stop)")
        try:
            self._client.loop_forever()
        except KeyboardInterrupt:
            log.info("Subscriber stopped")
        finally:
            self._client.disconnect()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sub = SmartFactorySubscriber()
    sub.run()

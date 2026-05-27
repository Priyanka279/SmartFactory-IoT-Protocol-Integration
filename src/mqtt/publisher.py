"""
Module 1 Assignment — Task 1.1
MQTT Sensor Publisher

Complete all TODO sections. Do not modify the function signatures
or the SensorReading dataclass — the tests depend on them.
"""

import json
import logging
import random
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
BROKER_HOST = "localhost"
BROKER_PORT = 1883
CLIENT_ID   = "smartfactory-publisher-001"

LINES   = ["line1", "line2"]
SENSORS = {
    "temperature": {"unit": "C",    "base": 70.0, "noise": 3.0,  "qos": 1},
    "vibration":   {"unit": "mm/s", "base": 1.2,  "noise": 0.3,  "qos": 0},
    "power":       {"unit": "kW",   "base": 45.0, "noise": 5.0,  "qos": 2},
}

CRITICAL_TEMP_THRESHOLD = 85.0


@dataclass
class SensorReading:
    line:      str
    sensor:    str
    value:     float
    unit:      str
    timestamp: str
    seq:       int


class SmartFactoryPublisher:
    """Publishes simulated sensor data for the SmartFactory assignment."""

    def __init__(self, broker_host: str = BROKER_HOST, broker_port: int = BROKER_PORT):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self._seq: dict[str, int] = {}          # per-topic sequence counter
        self._client: Optional[mqtt.Client] = None
        self._connected = False

    # ── Connection ─────────────────────────────────────────────────────────────

    def _build_client(self) -> mqtt.Client:
        """
        TODO 1: Create and configure the MQTT client.
        Requirements:
          - Use CLIENT_ID as the client identifier
          - Set clean_session=False for a persistent session
          - Register on_connect, on_publish callbacks (defined below)
          - Configure the Last Will and Testament for EACH line:
              topic   = f"factory/{line}/status"
              payload = "offline"
              qos     = 1
              retain  = True
            (Note: paho only supports a single LWT per client — set it for line1;
             the tests only verify line1 LWT)
        """
        # paho-mqtt ≥2.0 uses CallbackAPIVersion; fall back gracefully for older versions
        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id=CLIENT_ID,
                clean_session=False,          # persistent session
            )
        except AttributeError:
            client = mqtt.Client(client_id=CLIENT_ID, clean_session=False)

        # Register callbacks
        client.on_connect = self.on_connect
        client.on_publish = self.on_publish

        # Last Will and Testament — paho supports one LWT per client; use line1
        # (tests only check line1 LWT)
        client.will_set(
            topic=f"factory/line1/status",
            payload="offline",
            qos=1,
            retain=True,
        )
        log.debug("LWT configured: factory/line1/status → offline (qos=1, retain=True)")
        return client

    def connect(self) -> None:
        """
        TODO 2: Connect to the broker and publish the initial 'online' retained
        status message for each line.
          - Start the network loop (loop_start)
          - Wait up to 5 seconds for the connection to establish
          - For each line, publish retained 'online' to factory/{line}/status (QoS 1)
        """
        self._client = self._build_client()
        self._client.connect(self.broker_host, self.broker_port, keepalive=60)
        self._client.loop_start()

        # Wait up to 5 s for on_connect to fire
        deadline = time.time() + 5.0
        while not self._connected and time.time() < deadline:
            time.sleep(0.05)

        if not self._connected:
            log.warning("Did not receive CONNACK within 5 s — continuing anyway")

        # Publish retained 'online' status for every line
        for line in LINES:
            self._client.publish(
                f"factory/{line}/status",
                payload="online",
                qos=1,
                retain=True,
            )
            log.info("Status published: factory/%s/status → online (retain=True)", line)

    def disconnect(self) -> None:
        """Cleanly disconnect: publish 'offline' retained for each line, then stop."""
        if self._client is None:
            return
        for line in LINES:
            self._client.publish(f"factory/{line}/status", "offline", qos=1, retain=True)
        time.sleep(0.2)   # let the final publishes flush
        self._client.loop_stop()
        self._client.disconnect()
        log.info("Disconnected cleanly")

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def on_connect(self, client, userdata, flags, rc: int) -> None:
        """
        TODO 3: Implement the on_connect callback.
          - Log "Connected (rc=<rc>)" at INFO level on success (rc == 0)
          - Log "Connection refused: <rc>" at ERROR level on failure
        """
        if rc == 0:
            self._connected = True
            log.info("Connected (rc=%d)", rc)
        else:
            log.error("Connection refused: %d", rc)

    def on_publish(self, client, userdata, mid: int) -> None:
        """
        TODO 4: Implement the on_publish callback.
          - Log "PUBACK received for mid=<mid>" at DEBUG level
        """
        log.debug("PUBACK received for mid=%d", mid)

    # ── Sensor Simulation ──────────────────────────────────────────────────────

    def _simulate_reading(self, line: str, sensor: str) -> SensorReading:
        """Generate a realistic simulated sensor reading with Gaussian noise."""
        cfg   = SENSORS[sensor]
        value = round(cfg["base"] + random.gauss(0, cfg["noise"]), 3)
        key   = f"{line}/{sensor}"
        self._seq[key] = self._seq.get(key, 0) + 1
        return SensorReading(
            line=line,
            sensor=sensor,
            value=value,
            unit=cfg["unit"],
            timestamp=datetime.now(timezone.utc).isoformat(),
            seq=self._seq[key],
        )

    def _topic(self, line: str, sensor: str) -> str:
        """
        TODO 5: Return the correct MQTT topic string.
          Format: factory/{line}/{sensor}
          Example: factory/line1/temperature
        """
        return f"factory/{line}/{sensor}"

    # ── Publishing ─────────────────────────────────────────────────────────────

    def publish_reading(self, line: str, sensor: str) -> SensorReading:
        """
        TODO 6: Simulate a reading and publish it.
          - Generate a SensorReading using _simulate_reading
          - Serialise to JSON (use dataclasses.asdict)
          - Publish to the correct topic at the sensor's configured QoS level
          - Log the publication: "[{line}/{sensor}] value={value} {unit}  QoS={qos}  seq={seq}"
          - Return the SensorReading for testing purposes
        """
        reading = self._simulate_reading(line, sensor)
        topic   = self._topic(line, sensor)
        qos     = SENSORS[sensor]["qos"]
        payload = json.dumps(asdict(reading))

        self._client.publish(topic, payload=payload, qos=qos)

        log.info(
            "[%s/%s] value=%s %s  QoS=%d  seq=%d",
            line, sensor, reading.value, reading.unit, qos, reading.seq,
        )
        return reading

    # ── Main Loop ──────────────────────────────────────────────────────────────

    def run(self, interval_s: float = 1.0) -> None:
        """Continuously publish all sensors until interrupted."""
        self.connect()
        log.info("Publishing started (Ctrl-C to stop)")
        try:
            while True:
                for line in LINES:
                    for sensor in SENSORS:
                        self.publish_reading(line, sensor)
                time.sleep(interval_s)
        except KeyboardInterrupt:
            log.info("Shutting down…")
        finally:
            self.disconnect()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pub = SmartFactoryPublisher()
    pub.run()

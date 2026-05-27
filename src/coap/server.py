"""
Module 1 Assignment — Task 2.1
CoAP Sensor Resource Server

Complete all TODO sections. The resource classes must match the
URIs and behaviours listed in the assignment spec.

Run with:  python -m src.coap.server
"""

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone

import aiocoap
import aiocoap.resource as resource
from aiocoap import Code, Message

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)

# ── Sensor simulation helpers ─────────────────────────────────────────────────

SENSOR_CONFIG = {
    "temperature": {"unit": "C",    "base": 70.0, "noise": 3.0},
    "vibration":   {"unit": "mm/s", "base": 1.2,  "noise": 0.3},
    "power":       {"unit": "kW",   "base": 45.0, "noise": 5.0},
}

def _sim(sensor: str) -> dict:
    cfg = SENSOR_CONFIG[sensor]
    return {
        "value": round(cfg["base"] + random.gauss(0, cfg["noise"]), 3),
        "unit":  cfg["unit"],
        "ts":    datetime.now(timezone.utc).isoformat(),
    }

def _json(data: dict) -> bytes:
    return json.dumps(data).encode()


# ── Observable Sensor Resource ────────────────────────────────────────────────

class SensorResource(resource.ObservableResource):
    """
    An observable CoAP resource that represents a single sensor on a line.

    TODO 1: Implement this class.
    Requirements:
      - Accept line and sensor_type in __init__
      - Store the current reading (initially simulated)
      - Start an asyncio background task (_update_loop) that:
          * Simulates a new reading every 5 seconds
          * Calls self.updated_state() to notify observers
      - Implement render_get:
          * Return a 2.05 Content response
          * Content-Format: 50 (application/json)
          * Payload: JSON-encoded current reading including line and sensor_type
    """

    def __init__(self, line: str, sensor_type: str):
        super().__init__()
        self.line        = line
        self.sensor_type = sensor_type
        self._reading    = _sim(sensor_type)
        # Start the background update task
        asyncio.ensure_future(self._update_loop())

    async def _update_loop(self) -> None:
        """
        TODO 2: Every 5 seconds, simulate a new reading and notify observers.
        """
        while True:
            await asyncio.sleep(5)
            self._reading = _sim(self.sensor_type)
            log.info(
                "Sensor updated: /factory/%s/%s → %s %s",
                self.line, self.sensor_type,
                self._reading["value"], self._reading["unit"],
            )
            # Notify all registered observers
            self.updated_state()

    async def render_get(self, request: Message) -> Message:
        """
        TODO 3: Return the current sensor reading as a JSON response.
        Content-Format 50 = application/json
        """
        payload = _json({
            "line":        self.line,
            "sensor_type": self.sensor_type,
            "value":       self._reading["value"],
            "unit":        self._reading["unit"],
            "timestamp":   self._reading["ts"],
        })
        response = Message(code=Code.CONTENT, payload=payload)
        response.opt.content_format = 50   # application/json
        return response


# ── Actuator Resource ─────────────────────────────────────────────────────────

class ActuatorResource(resource.Resource):
    """
    A CoAP resource representing a controllable fan actuator.

    TODO 4: Implement this class.
    Requirements:
      - Track state: "OFF" initially
      - render_get: return current state as JSON {"state": "ON"|"OFF"}
      - render_put: accept {"state": "ON"} or {"state": "OFF"}
          * Update internal state
          * Return 2.04 Changed on success
          * Return 4.00 Bad Request if payload is malformed or state is invalid
    """

    def __init__(self):
        super().__init__()
        self._state = "OFF"

    async def render_get(self, request: Message) -> Message:
        """TODO 5: Return current fan state as JSON."""
        payload = _json({"actuator": "fan", "state": self._state})
        response = Message(code=Code.CONTENT, payload=payload)
        response.opt.content_format = 50
        return response

    async def render_put(self, request: Message) -> Message:
        """TODO 6: Accept ON/OFF command and update state."""
        try:
            data  = json.loads(request.payload.decode("utf-8"))
            state = data.get("state", "").upper()
            if state not in ("ON", "OFF"):
                return Message(
                    code=Code.BAD_REQUEST,
                    payload=b'{"error": "state must be ON or OFF"}',
                )
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            return Message(
                code=Code.BAD_REQUEST,
                payload=b'{"error": "invalid JSON payload"}',
            )

        self._state = state
        log.info("Fan actuator set to %s", self._state)
        response = Message(
            code=Code.CHANGED,
            payload=_json({"actuator": "fan", "state": self._state}),
        )
        response.opt.content_format = 50
        return response


# ── Block-wise Manifest Resource ──────────────────────────────────────────────

class ManifestResource(resource.Resource):
    """
    A large resource that triggers CoAP Block2 transfer.

    TODO 7: Implement this class.
    Requirements:
      - render_get must return a payload of AT LEAST 3072 bytes (3 KB)
      - Content-Format: 50 (application/json)
      - The payload should be a realistic-looking firmware manifest
      - aiocoap handles Block2 fragmentation automatically
    """

    def __init__(self):
        super().__init__()
        self._payload = self._build_manifest()

    def _build_manifest(self) -> bytes:
        """Build a JSON firmware manifest that is guaranteed >= 3072 bytes."""
        entries = []
        sensors = ["temperature", "vibration", "power"]
        lines   = ["line1", "line2"]

        for i in range(1, 51):          # 50 entries — comfortably over 3 KB
            sensor = sensors[i % len(sensors)]
            line   = lines[i % len(lines)]
            entries.append({
                "id":           i,
                "line":         line,
                "sensor_type":  sensor,
                "firmware_ver": f"v2.{i // 10}.{i % 10}",
                "build":        f"build-{1000 + i}",
                "checksum":     f"sha256:{os.urandom(16).hex()}",
                "size_bytes":   random.randint(32768, 131072),
                "target_mcu":   "STM32L4",
                "class":        "Class-2",
                "release_date": datetime.now(timezone.utc).date().isoformat(),
                "release_notes": (
                    f"Firmware update {i} for {sensor} sensor on {line}. "
                    f"Includes improved ADC calibration, reduced idle power draw, "
                    f"enhanced CoAP observe stability, and RTOS v3.2 compatibility. "
                    f"Apply using the OTA update procedure in the maintenance guide."
                ),
                "download_url": f"coap://ota.smartfactory.io/firmware/{line}/{sensor}/v2.{i}.bin",
            })

        manifest = {
            "schema_version": "1.0",
            "generated_at":   datetime.now(timezone.utc).isoformat(),
            "factory":        "SmartFactory Inc.",
            "total_entries":  len(entries),
            "description": (
                "OTA firmware manifest for all SmartFactory production-line sensors. "
                "Delivered via CoAP Block2 transfer due to payload size. "
                "Verify checksums before flashing."
            ),
            "entries": entries,
        }

        data = json.dumps(manifest, indent=2).encode("utf-8")

        # Safety check — pad if somehow still under 3 KB
        if len(data) < 3072:
            extra = {"_pad": "x" * (3072 - len(data) + 100)}
            manifest.update(extra)
            data = json.dumps(manifest, indent=2).encode("utf-8")

        log.info("ManifestResource built: %d bytes", len(data))
        return data

    async def render_get(self, request: Message) -> Message:
        """TODO 8: Return a >= 3 KB JSON firmware manifest."""
        response = Message(code=Code.CONTENT, payload=self._payload)
        response.opt.content_format = 50   # application/json
        return response


# ── Resource Tree & Server Setup ──────────────────────────────────────────────

async def build_server() -> aiocoap.Context:
    """
    TODO 9: Build the CoAP resource tree and create the server context.
    """
    root = resource.Site()

    # Sensor resources
    root.add_resource(["factory", "line1", "temperature"],
                      SensorResource("line1", "temperature"))
    root.add_resource(["factory", "line1", "vibration"],
                      SensorResource("line1", "vibration"))
    root.add_resource(["factory", "line1", "power"],
                      SensorResource("line1", "power"))
    root.add_resource(["factory", "line2", "temperature"],
                      SensorResource("line2", "temperature"))

    # Actuator resource
    root.add_resource(["actuator", "line1", "fan"],
                      ActuatorResource())

    # Manifest (Block2) resource
    root.add_resource(["factory", "manifest"],
                      ManifestResource())

    # Well-known core (resource discovery)
    root.add_resource([".well-known", "core"],
                      resource.WKCResource(root.get_resources_as_linkheader))

    context = await aiocoap.Context.create_server_context(root, bind=("::1", 5683))
    return context


async def main() -> None:
    context = await build_server()
    log.info("CoAP server running on coap://localhost:5683")
    log.info("Resources: /factory/line{1,2}/{temperature,vibration,power}, "
             "/actuator/line1/fan, /factory/manifest")
    await asyncio.get_event_loop().create_future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())

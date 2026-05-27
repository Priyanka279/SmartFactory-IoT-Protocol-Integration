"""
Module 1 Assignment — Task 2.2
CoAP Observer Client

Complete all TODO sections.

Run with:  python -m src.coap.observer
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import aiocoap
from aiocoap import Message, Code

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)

SERVER_BASE      = "coap://localhost"
OBSERVE_DURATION = 60   # seconds before clean deregister


class FactoryObserver:
    """Observes CoAP sensor resources and reassembles Block2 transfers."""

    def __init__(self):
        self._ctx = None
        self._last_seq: dict[str, int] = {}     # uri -> last observe sequence number
        self._stale_count: dict[str, int] = {}  # uri -> stale notification count

    # ── Setup ──────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Create the aiocoap client context."""
        self._ctx = await aiocoap.Context.create_client_context()

    async def stop(self) -> None:
        """Clean up the context."""
        if self._ctx:
            await self._ctx.shutdown()

    # ── Observation ────────────────────────────────────────────────────────────

    async def observe_resource(self, uri: str) -> None:
        """
        TODO 1: Subscribe to a single observable CoAP resource.
        Requirements:
          - Build a GET request with observe=0 (register)
          - Use self._ctx.request(request_obj) to get a RequestObservation
          - Iterate over the observation using `async for response in pr.observation:`
          - For each notification, call _handle_notification(uri, response)
          - After OBSERVE_DURATION seconds, cancel the observation
          - Log "Deregistered from {uri}" after cancellation
        """
        request = Message(code=Code.GET)
        request.set_request_uri(uri)
        request.opt.observe = 0   # Register observation

        pr = self._ctx.request(request)

        # Initialise stale tracking for this URI
        self._stale_count.setdefault(uri, 0)

        # Collect notifications for OBSERVE_DURATION seconds
        async def _collect():
            async for response in pr.observation:
                self._handle_notification(uri, response)

        try:
            await asyncio.wait_for(_collect(), timeout=OBSERVE_DURATION)
        except asyncio.TimeoutError:
            pass   # normal — duration elapsed
        except Exception as exc:
            log.error("Observation error on %s: %s", uri, exc)
        finally:
            # Cancel / deregister
            pr.observation.cancel()
            log.info("Deregistered from %s", uri)

    def _handle_notification(self, uri: str, response: Message) -> None:
        """
        TODO 2: Process a single Observe notification.
        Requirements:
          - Extract the Observe option sequence number from response.opt.observe
          - Check for stale notification:
              * If the sequence number <= last seen (mod 2^24 wrap-around check):
                  - Increment self._stale_count[uri]
                  - Log "STALE notification on {uri}: seq={seq} <= last={last}"
                  - RETURN (do not process the stale value)
          - Update self._last_seq[uri]
          - Parse response.payload as JSON
          - Log:
              [OBSERVE] {uri}  seq={seq}  val={value} {unit}  @ {timestamp}
        """
        seq = response.opt.observe

        if seq is None:
            # Non-observe response (e.g. initial ACK) — still process
            seq = 0

        # Stale check — RFC 7641 §4.4 mod-2^24 comparison
        last = self._last_seq.get(uri)
        if last is not None:
            # Stale if new seq is not strictly greater (accounting for wrap at 2^24)
            diff = (seq - last) % (2 ** 24)
            if diff == 0 or diff >= (2 ** 23):
                self._stale_count[uri] = self._stale_count.get(uri, 0) + 1
                log.warning("STALE notification on %s: seq=%d <= last=%d", uri, seq, last)
                return

        self._last_seq[uri] = seq

        # Parse payload
        try:
            data  = json.loads(response.payload.decode("utf-8"))
            value = data.get("value", "?")
            unit  = data.get("unit", "")
            ts    = data.get("timestamp", data.get("ts", datetime.now(timezone.utc).isoformat()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            value = response.payload.decode("utf-8", errors="replace")
            unit  = ""
            ts    = datetime.now(timezone.utc).isoformat()

        log.info("[OBSERVE] %s  seq=%d  val=%s %s  @ %s", uri, seq, value, unit, ts)

    # ── Block2 Transfer ────────────────────────────────────────────────────────

    async def fetch_manifest(self) -> None:
        """
        TODO 3: Perform a GET on /factory/manifest and reassemble Block2.
        Requirements:
          - aiocoap handles Block2 reassembly automatically
          - Log: "Manifest received: {len(payload)} bytes"
          - Parse as JSON and count the number of top-level items
          - Log: "Firmware entries in manifest: {count}"
          - Log: "Block2 transfer complete"
        """
        uri = f"{SERVER_BASE}/factory/manifest"
        log.info("Fetching firmware manifest from %s …", uri)

        request = Message(code=Code.GET)
        request.set_request_uri(uri)

        response = await self._ctx.request(request).response

        payload_bytes = response.payload
        log.info("Manifest received: %d bytes", len(payload_bytes))

        try:
            manifest = json.loads(payload_bytes.decode("utf-8"))
            # Count firmware entries (they live under the "entries" key)
            entries = manifest.get("entries", manifest if isinstance(manifest, list) else [])
            count   = len(entries) if isinstance(entries, list) else len(manifest)
            log.info("Firmware entries in manifest: %d", count)
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.warning("Could not parse manifest as JSON")

        log.info("Block2 transfer complete")

    # ── Run ────────────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        TODO 4: Run all observations concurrently, then fetch the manifest.
        Requirements:
          - Start observe_resource for both:
              coap://localhost/factory/line1/temperature
              coap://localhost/factory/line2/temperature
          - Run them concurrently using asyncio.gather
          - After both complete, call fetch_manifest
          - Print a final summary: stale notification counts per URI
        """
        await self.start()
        try:
            uri_line1 = f"{SERVER_BASE}/factory/line1/temperature"
            uri_line2 = f"{SERVER_BASE}/factory/line2/temperature"

            log.info("Starting concurrent observations for %d seconds…", OBSERVE_DURATION)

            # Run both observations concurrently
            await asyncio.gather(
                self.observe_resource(uri_line1),
                self.observe_resource(uri_line2),
            )

            # After observations complete, fetch the large manifest via Block2
            await self.fetch_manifest()

            # Final summary
            print("\n── Observation Summary ──────────────────────────────────────")
            for uri in [uri_line1, uri_line2]:
                stale = self._stale_count.get(uri, 0)
                last  = self._last_seq.get(uri, "N/A")
                print(f"  {uri}")
                print(f"    Last sequence : {last}")
                print(f"    Stale count   : {stale}")
            print("─────────────────────────────────────────────────────────────\n")

        finally:
            await self.stop()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    observer = FactoryObserver()
    asyncio.run(observer.run())

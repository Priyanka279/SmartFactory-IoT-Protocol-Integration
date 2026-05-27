"""
Module 1 Assignment — Task 3.1
AMQP Broker Topology

Declares exchanges, queues, and bindings for the SmartFactory backend.
Run once before starting producer/consumer:
    python -m src.amqp.topology
"""

import logging
import pika
import pika.exceptions

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)

# ── Constants (imported by tests — do not rename) ─────────────────────────────
EXCHANGE_TELEMETRY = "iot.telemetry"
EXCHANGE_DLX       = "iot.dlx"

QUEUE_ALERTS      = "alerts-queue"
QUEUE_TEMPERATURE = "temperature-queue"
QUEUE_ALL         = "all-telemetry-queue"
QUEUE_DLX         = "dead-letter-queue"
QUEUE_LINE1       = "line1-queue"

BROKER_HOST = "localhost"
BROKER_PORT = 5672


def get_connection_params() -> pika.ConnectionParameters:
    """Return connection parameters for RabbitMQ."""
    return pika.ConnectionParameters(
        host=BROKER_HOST,
        port=BROKER_PORT,
        credentials=pika.PlainCredentials("guest", "guest"),
        heartbeat=60,
        blocked_connection_timeout=30,
    )


def declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    """
    Declare all exchanges, queues, and bindings for the SmartFactory topology.

    Exchanges:
      iot.telemetry  — topic exchange  (main sensor data)
      iot.dlx        — direct exchange (dead letters)

    Queues:
      alerts-queue        → binding: #.critical
      temperature-queue   → binding: *.*.temperature   TTL=60s  DLX→iot.dlx
      all-telemetry-queue → binding: factory.#         max-length=10000  DLX→iot.dlx
      dead-letter-queue   → bound to iot.dlx  key=dead
      line1-queue         → binding: factory.line1.#
    """
    # ── Exchanges ─────────────────────────────────────────────────────────────
    channel.exchange_declare(
        exchange=EXCHANGE_TELEMETRY,
        exchange_type="topic",
        durable=True,
    )
    log.info("Exchange declared: %s (topic, durable)", EXCHANGE_TELEMETRY)

    channel.exchange_declare(
        exchange=EXCHANGE_DLX,
        exchange_type="direct",
        durable=True,
    )
    log.info("Exchange declared: %s (direct, durable)", EXCHANGE_DLX)

    # ── Dead-letter queue (no DLX on this one — it IS the dead-letter sink) ──
    channel.queue_declare(
        queue=QUEUE_DLX,
        durable=True,
    )
    channel.queue_bind(
        queue=QUEUE_DLX,
        exchange=EXCHANGE_DLX,
        routing_key="dead",
    )
    log.info("Queue declared and bound: %s → %s (key=dead)", QUEUE_DLX, EXCHANGE_DLX)

    # ── alerts-queue — critical readings ─────────────────────────────────────
    channel.queue_declare(
        queue=QUEUE_ALERTS,
        durable=True,
    )
    channel.queue_bind(
        queue=QUEUE_ALERTS,
        exchange=EXCHANGE_TELEMETRY,
        routing_key="#.critical",
    )
    log.info("Queue declared and bound: %s → #.critical", QUEUE_ALERTS)

    # ── temperature-queue — with TTL and DLX ─────────────────────────────────
    channel.queue_declare(
        queue=QUEUE_TEMPERATURE,
        durable=True,
        arguments={
            "x-message-ttl":          60000,      # 60 seconds in ms
            "x-dead-letter-exchange":  EXCHANGE_DLX,
            "x-dead-letter-routing-key": "dead",
        },
    )
    channel.queue_bind(
        queue=QUEUE_TEMPERATURE,
        exchange=EXCHANGE_TELEMETRY,
        routing_key="*.*.temperature",
    )
    log.info("Queue declared and bound: %s → *.*.temperature (TTL=60s, DLX)", QUEUE_TEMPERATURE)

    # ── all-telemetry-queue — all factory data with max-length and DLX ───────
    channel.queue_declare(
        queue=QUEUE_ALL,
        durable=True,
        arguments={
            "x-max-length":            10000,
            "x-overflow":              "dead-letter",
            "x-dead-letter-exchange":  EXCHANGE_DLX,
            "x-dead-letter-routing-key": "dead",
        },
    )
    channel.queue_bind(
        queue=QUEUE_ALL,
        exchange=EXCHANGE_TELEMETRY,
        routing_key="factory.#",
    )
    log.info("Queue declared and bound: %s → factory.# (max-length=10000, DLX)", QUEUE_ALL)

    # ── line1-queue — only line1 data ─────────────────────────────────────────
    channel.queue_declare(
        queue=QUEUE_LINE1,
        durable=True,
    )
    channel.queue_bind(
        queue=QUEUE_LINE1,
        exchange=EXCHANGE_TELEMETRY,
        routing_key="factory.line1.#",
    )
    log.info("Queue declared and bound: %s → factory.line1.#", QUEUE_LINE1)

    log.info("Topology declaration complete.")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    params = get_connection_params()
    try:
        connection = pika.BlockingConnection(params)
        channel    = connection.channel()
        declare_topology(channel)
        connection.close()
        log.info("RabbitMQ topology set up successfully.")
    except pika.exceptions.AMQPConnectionError as e:
        log.error("Could not connect to RabbitMQ: %s", e)
        log.error("Start RabbitMQ with: docker compose up -d rabbitmq")

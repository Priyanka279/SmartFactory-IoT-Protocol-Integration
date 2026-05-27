"""
tests/mqtt/test_subscriber.py
SmartFactory IoT Assignment — Task 1.2 tests

Do not modify.
"""

import io
import json
import sys
import unittest
from unittest.mock import MagicMock


def make_sub():
    from src.mqtt.subscriber import SmartFactorySubscriber
    return SmartFactorySubscriber()


class TestSubscriberConnect(unittest.TestCase):

    def test_subscribes_to_all_topics(self):
        """on_connect must subscribe to factory/#."""
        from src.mqtt.subscriber import TOPIC_ALL
        sub    = make_sub()
        client = MagicMock()
        sub.on_connect(client, None, {}, 0)
        topics = [c[0][0] for c in client.subscribe.call_args_list]
        self.assertIn(TOPIC_ALL, topics)

    def test_subscribes_to_temperature(self):
        """on_connect must subscribe to factory/+/temperature."""
        from src.mqtt.subscriber import TOPIC_TEMP
        sub    = make_sub()
        client = MagicMock()
        sub.on_connect(client, None, {}, 0)
        topics = [c[0][0] for c in client.subscribe.call_args_list]
        self.assertIn(TOPIC_TEMP, topics)

    def test_temperature_subscription_qos2(self):
        """factory/+/temperature must be subscribed at QoS 2."""
        from src.mqtt.subscriber import TOPIC_TEMP
        sub    = make_sub()
        client = MagicMock()
        sub.on_connect(client, None, {}, 0)
        for c in client.subscribe.call_args_list:
            args, kwargs = c
            topic = args[0]
            qos   = args[1] if len(args) > 1 else kwargs.get("qos", -1)
            if topic == TOPIC_TEMP:
                self.assertEqual(qos, 2)
                return
        self.fail(f"{TOPIC_TEMP} not found in subscribe calls")

    def test_no_connect_on_failure(self):
        """on_connect with rc != 0 must not subscribe."""
        sub    = make_sub()
        client = MagicMock()
        sub.on_connect(client, None, {}, 5)
        client.subscribe.assert_not_called()


class TestCriticalAlert(unittest.TestCase):

    def _fire(self, value):
        sub = make_sub()
        payload = {"value": value, "unit": "C", "timestamp": "2026-01-01T00:00:00Z"}
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        sub._check_temperature_alert("factory/line1/temperature", payload)
        sys.stdout = old
        return buf.getvalue(), sub._alerts_fired

    def test_alert_fires_above_threshold(self):
        out, count = self._fire(90.0)
        self.assertIn("CRITICAL ALERT", out)
        self.assertEqual(count, 1)

    def test_alert_not_fired_below_threshold(self):
        out, count = self._fire(80.0)
        self.assertNotIn("CRITICAL", out)
        self.assertEqual(count, 0)

    def test_alert_not_fired_at_threshold(self):
        out, count = self._fire(85.0)
        self.assertNotIn("CRITICAL", out)
        self.assertEqual(count, 0)

    def test_alert_not_fired_for_non_dict(self):
        sub = make_sub()
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        sub._check_temperature_alert("factory/line1/temperature", "online")
        sys.stdout = old
        self.assertNotIn("CRITICAL", buf.getvalue())
        self.assertEqual(sub._alerts_fired, 0)


class TestMessageCounting(unittest.TestCase):

    def _send_msg(self, sub, topic, value):
        msg = MagicMock()
        msg.topic   = topic
        msg.payload = json.dumps({"value": value, "unit": "C",
                                  "timestamp": "2026-01-01T00:00:00Z"}).encode()
        msg.qos     = 1
        msg.retain  = False
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        sub.on_message(None, None, msg)
        sys.stdout = old

    def test_message_count_increments(self):
        sub = make_sub()
        self._send_msg(sub, "factory/line1/temperature", 70.0)
        self._send_msg(sub, "factory/line1/temperature", 71.0)
        self.assertEqual(sub._msg_counts["factory/line1/temperature"], 2)

    def test_separate_counts_per_topic(self):
        sub = make_sub()
        self._send_msg(sub, "factory/line1/temperature", 70.0)
        self._send_msg(sub, "factory/line2/temperature", 72.0)
        self.assertEqual(sub._msg_counts["factory/line1/temperature"], 1)
        self.assertEqual(sub._msg_counts["factory/line2/temperature"], 1)


if __name__ == "__main__":
    unittest.main()

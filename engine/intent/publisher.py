"""Redpanda/Kafka publisher for tenant-scoped intent signals."""

from __future__ import annotations

from aiokafka import AIOKafkaProducer

from engine.intent.models import IntentSignal


class RedpandaPublisher:
    """Publish intent signals to the shared ingestion topic."""

    def __init__(self, *, brokers: str, topic: str = "intent-signals") -> None:
        self.brokers = brokers
        self.topic = topic

    async def publish(self, signal: IntentSignal) -> None:
        """Publish one signal and always close the producer."""

        producer = AIOKafkaProducer(bootstrap_servers=self.brokers)
        await producer.start()
        try:
            await producer.send_and_wait(topic=self.topic, value=signal.to_json_bytes())
        finally:
            await producer.stop()

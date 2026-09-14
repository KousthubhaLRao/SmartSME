"""Inbound order channels: email and Telegram.

`collector.collect(db)` is the one entry point; everything else is an adapter
that turns a channel's payload into `pipeline.IncomingMessage`.
"""

from .collector import collect
from .pipeline import IncomingMessage, ingest, route

__all__ = ["IncomingMessage", "collect", "ingest", "route"]

"""Applies a service toggle in every worker, not just the one that served the PUT.

Staff flip a background service from the control panel, but gunicorn runs three
workers and each holds its own service registry. Starting or stopping the
service in place therefore reached one worker of three, leaving the others
running the opposite of what the panel showed - and whichever worker answered
the next request decided what "enabled" meant.

The endpoint persists the toggle and publishes here instead; this subscriber
runs in every worker and applies the change to that worker's registry. It is
deliberately not itself a toggleable service: nothing should be able to switch
off the thing that applies the switches.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from loguru import logger
from valkey.asyncio import Valkey

TOGGLE_CHANNEL = "foundry:service_toggles"

_RECONNECT_SECONDS = 5


class ToggleDispatchService:
    """Subscribes to toggle changes and applies them to this worker's services."""

    def __init__(self, valkey_uri: str, registry: dict[str, Any]) -> None:
        self._valkey_uri = valkey_uri
        self._registry = registry
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="toggle-dispatch-subscriber")
        logger.info("ToggleDispatchService started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("ToggleDispatchService stopped")

    async def _run(self) -> None:
        while True:
            # A blocking listen needs its own connection with no socket timeout,
            # or the shared client's timeout kills the subscriber silently.
            sub = Valkey.from_url(self._valkey_uri, socket_timeout=None)
            try:
                async with sub.pubsub() as ps:
                    await ps.subscribe(TOGGLE_CHANNEL)
                    logger.info(
                        "ToggleDispatchService: subscribed to {}", TOGGLE_CHANNEL
                    )
                    async for raw in ps.listen():
                        if raw["type"] != "message":
                            continue
                        try:
                            await apply_toggle(json.loads(raw["data"]), self._registry)
                        except Exception as exc:
                            logger.warning("ToggleDispatchService error: {}", exc)
            except asyncio.CancelledError:
                logger.info("ToggleDispatchService: shutting down")
                await sub.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "ToggleDispatchService: connection lost ({}), reconnecting in {}s",
                    exc,
                    _RECONNECT_SECONDS,
                )
                await sub.aclose()
                await asyncio.sleep(_RECONNECT_SECONDS)


async def apply_toggle(data: dict[str, Any], registry: dict[str, Any]) -> None:
    """Start or stop one service in this worker, if it holds one at all.

    Idempotent on purpose: every worker receives every publish, including the
    one that served the request, and a toggle may be re-sent.
    """
    service_key = str(data["service_key"])
    enabled = bool(data["enabled"])
    service = registry.get(service_key)
    if service is None:
        logger.warning(
            "Service {} not in registry (may require WOM_GROUP_ID)", service_key
        )
        return
    if enabled and not service.is_running:
        await service.start()
    elif not enabled and service.is_running:
        await service.stop()

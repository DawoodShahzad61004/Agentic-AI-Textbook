"""Python logging handler that mirrors records to Langfuse events."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Callable


_emitting: ContextVar[bool] = ContextVar("langfuse_log_handler_emitting", default=False)


def _langfuse_level(levelno: int) -> str:
    if levelno >= logging.ERROR:
        return "ERROR"
    if levelno >= logging.WARNING:
        return "WARNING"
    if levelno <= logging.DEBUG:
        return "DEBUG"
    return "DEFAULT"


class LangfuseHandler(logging.Handler):
    """Create a Langfuse event for each ordinary :class:`LogRecord`.

    Langfuse is imported lazily so logging continues to work when its SDK is
    absent or disabled. Events automatically attach to the current Langfuse
    observation/trace when one exists.
    """

    def __init__(
        self,
        level: int = logging.NOTSET,
        *,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(level)
        self._client_factory = client_factory

    def emit(self, record: logging.LogRecord) -> None:
        if _emitting.get():
            return

        token = _emitting.set(True)
        try:
            message = self.format(record)
            client_factory = self._client_factory
            if client_factory is None:
                from langfuse import get_client

                client_factory = get_client

            client_factory().create_event(
                name=f"log.{record.levelname.lower()}",
                input=message,
                level=_langfuse_level(record.levelno),
                status_message=record.getMessage(),
                metadata={
                    "logger": record.name,
                    "level": record.levelname,
                    "request_id": getattr(record, "request_id", "-"),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                    "pathname": record.pathname,
                    "process": record.process,
                    "thread": record.thread,
                },
            )
        except Exception:
            # A telemetry backend must never break application logging.
            self.handleError(record)
        finally:
            _emitting.reset(token)

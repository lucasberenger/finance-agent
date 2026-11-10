"""Operational logs with an explicit field allowlist; never serialize payloads/errors."""
import json
import logging
import os
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from time import perf_counter

_context = ContextVar('log_context', default={})
_FIELDS = frozenset({'update_id', 'action', 'stage', 'duration_ms', 'error_type',
                     'status_code', 'reason', 'model', 'source'})
log = logging.getLogger('app.events')
log.addHandler(logging.NullHandler())


class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Deliberately omit getMessage(), exc_info and stack_info: they may contain secrets.
        data = {'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                'level': record.levelname, 'event': getattr(record, 'event', 'log')}
        data.update({key: value for key, value in getattr(record, 'event_fields', {}).items()
                     if key in _FIELDS})
        return json.dumps(data, ensure_ascii=False, allow_nan=False)


def configure_logging():
    level = os.getenv('LOG_LEVEL', 'INFO').upper()
    if level not in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
        raise ValueError('LOG_LEVEL deve ser DEBUG, INFO, WARNING, ERROR ou CRITICAL')
    logger = logging.getLogger('app')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    # HTTP request URLs include the Telegram token. SDK debug logs may include payloads.
    for name in ('httpx', 'httpcore', 'groq', 'google', 'urllib3', 'gspread'):
        dependency = logging.getLogger(name)
        dependency.handlers = [logging.NullHandler()]
        dependency.propagate = False
        dependency.setLevel(logging.CRITICAL + 1)


def event(name, level=logging.INFO, **fields):
    data = {**_context.get(), **fields}
    log.log(level, '', extra={'event': name, 'event_fields': {k: v for k, v in data.items() if k in _FIELDS}})


@contextmanager
def context(**fields):
    token = _context.set({**_context.get(), **{k: v for k, v in fields.items() if k in _FIELDS}})
    try:
        yield
    finally:
        _context.reset(token)


@contextmanager
def stage(name, **fields):
    start = perf_counter()
    with context(stage=name, **fields):
        try:
            yield
        except Exception as exc:
            details = {'error_type': type(exc).__name__}
            status = getattr(exc, 'status_code', None)
            if not isinstance(status, int):
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
            if isinstance(status, int):
                details['status_code'] = status
            event('stage_failed', logging.ERROR, duration_ms=round((perf_counter() - start) * 1000, 2), **details)
            raise
        else:
            event('stage_completed', duration_ms=round((perf_counter() - start) * 1000, 2))


def timed(name):
    def decorate(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            with stage(name):
                return fn(*args, **kwargs)
        return wrapper
    return decorate

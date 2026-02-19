"""Request-scoped credential overrides via ContextVar.

Middleware in main.py sets the ContextVar per request.
get_es() and converse_stream() check this before falling back to env vars.
Credentials are never persisted — they live only for the duration of one request.
"""
from contextvars import ContextVar

_request_creds: ContextVar[dict] = ContextVar("request_creds", default={})


def get_creds() -> dict:
    return _request_creds.get()


def set_creds(creds: dict):
    return _request_creds.set(creds)

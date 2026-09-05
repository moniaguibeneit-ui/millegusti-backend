"""Shared utility helpers."""
import uuid
import secrets


def gen_id() -> str:
    """Generate a short unique ID (8 chars)."""
    return secrets.token_hex(4)


def gen_uuid() -> str:
    return str(uuid.uuid4())

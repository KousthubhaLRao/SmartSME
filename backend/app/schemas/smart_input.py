"""Smart Input request payloads."""

from __future__ import annotations

from pydantic import BaseModel


class ParseTextInput(BaseModel):
    """Free-text to turn into a draft transaction."""

    text: str

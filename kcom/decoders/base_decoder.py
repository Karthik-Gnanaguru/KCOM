"""Abstract base class for protocol decoders."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseDecoder(ABC):
    """Base class for all frame/protocol decoders.

    Subclasses implement stateful frame parsing over a continuous byte stream.
    """

    #: Human-readable name shown in decoder selection UI
    name: str = "Base"

    @abstractmethod
    def decode(self, data: bytes) -> dict | None:
        """Feed bytes to the decoder.

        Returns a dict of decoded fields when a complete frame is detected,
        or None if no complete frame is available yet.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset internal parser state (e.g., discard partial frames)."""
        ...

"""
modes/__init__.py
-----------------
Public API for the ScholarOS plugin system.
"""

from modes.base_mode import BaseMode
from modes.flashcard_mode import FlashcardMode
from modes.qa_mode import QAMode

__all__ = [
    "BaseMode",
    "QAMode",
    "FlashcardMode",
]
"""
modes/__init__.py
-----------------
Public API for the ScholarOS plugin system.

Every study mode lives in this package and inherits from BaseMode.
To add a new mode, create modes/your_mode.py and import it here.
"""

from modes.base_mode import BaseMode
from modes.qa_mode import QAMode
from modes.flashcard_mode import FlashcardMode

__all__ = [
    "BaseMode",
    "QAMode",
    "FlashcardMode",
]
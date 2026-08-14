"""Conservative, auditable OCR confusion corrections.

Corrections only apply when a caller supplies the allowed answer labels. The
module never silently rewrites a full stem or official answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ChoiceCorrection:
    raw: str
    corrected: str
    changed: bool
    reason: str | None = None


class OcrDictionary:
    def __init__(self, replacements: dict[str, str] | None = None) -> None:
        self.replacements = {"8": "B", "G": "C", "0": "D", "I": "A", **(replacements or {})}

    def correct_choice(self, raw: str, allowed: Iterable[str] = ("A", "B", "C", "D")) -> ChoiceCorrection:
        value = str(raw).strip().upper()
        labels = {str(item).strip().upper() for item in allowed}
        if value in labels:
            return ChoiceCorrection(value, value, False)
        corrected = "".join(self.replacements.get(char, char) for char in value)
        if corrected in labels:
            return ChoiceCorrection(value, corrected, True, "known OCR confusion")
        return ChoiceCorrection(value, value, False, "unresolved choice; needs review")

    def correct_choices(self, values: Iterable[str], allowed: Iterable[str] = ("A", "B", "C", "D")) -> list[ChoiceCorrection]:
        return [self.correct_choice(value, allowed) for value in values]


"""Markers as a decorator would set them, and the record it leaves on a method."""

from dataclasses import dataclass
from typing import Final

CLASS_MARKER: Final = "__sample_class_marker__"
METHOD_MARKER: Final = "__sample_method_marker__"


@dataclass(frozen=True, slots=True)
class SampleMapping:
    """Stands in for what a method decorator records, like a route or a schedule."""

    label: str

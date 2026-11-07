"""Classes with and without markers."""

from tests.component_scan.sample_marked.markers import SampleMapping


class Unmarked:
    """Stands in for a plain component."""

    def work(self) -> None:
        """Carries no marker."""


class Marked:
    """Stands in for a class a class decorator marked."""

    __sample_class_marker__ = True

    def second(self) -> None:
        """Marked."""

    def first(self) -> None:
        """Marked."""

    def plain(self) -> None:
        """Not marked."""

    def foreign(self) -> None:
        """Carries the marker attribute, but not a SampleMapping."""


Marked.second.__sample_method_marker__ = SampleMapping("second")  # type: ignore[attr-defined]
Marked.first.__sample_method_marker__ = SampleMapping("first")  # type: ignore[attr-defined]
Marked.foreign.__sample_method_marker__ = "not a mapping"  # type: ignore[attr-defined]


class InheritsTheMarker(Marked):
    """Inherits the class marker without carrying it itself."""

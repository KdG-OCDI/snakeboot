"""Once Django has started, the component scan finds the classes and methods that decorators marked."""

from snakeboot.component_scan import ComponentScan
from tests.component_scan.sample_marked.marked import Marked
from tests.component_scan.sample_marked.markers import CLASS_MARKER, METHOD_MARKER, SampleMapping

SCAN = ComponentScan(("tests.component_scan.sample_marked",), auto_configuration=())


def test_finds_the_classes_that_carry_a_marker_themselves_once_where_they_are_defined() -> None:
    assert SCAN.classes_marked(CLASS_MARKER) == [Marked]


def test_finds_no_classes_for_a_marker_nobody_set() -> None:
    assert SCAN.classes_marked("__nobody_sets_this__") == []


def test_finds_the_marked_methods_with_their_record_sorted_by_name() -> None:
    found = SCAN.methods_marked(METHOD_MARKER, SampleMapping)

    assert [(marked.name, marked.mapping.label) for marked in found] == [
        ("tests.component_scan.sample_marked.marked.InheritsTheMarker.first", "first"),
        ("tests.component_scan.sample_marked.marked.InheritsTheMarker.second", "second"),
        ("tests.component_scan.sample_marked.marked.Marked.first", "first"),
        ("tests.component_scan.sample_marked.marked.Marked.second", "second"),
    ]


def test_a_marked_method_knows_its_class_and_function() -> None:
    first = next(marked for marked in SCAN.methods_marked(METHOD_MARKER, SampleMapping) if marked.owner is Marked)

    assert first.method is Marked.first

"""`@application_root` declares a component scan that starts in the package of the marked class."""

import pytest

from snakeboot.component_scan import DJANGO_ENTRY_POINTS, ComponentScan, InvalidApplicationRootError, application_root

THIS_PACKAGE = "tests.component_scan"


@application_root
class BareApplication:
    pass


@application_root(exclude=("*.test_component_scan",))
class ApplicationWithOwnExclusions:
    pass


class NotAnApplication:
    pass


def test_the_scan_starts_in_the_package_of_the_marked_class() -> None:
    assert ComponentScan.of(BareApplication) == ComponentScan((THIS_PACKAGE,))


def test_a_bare_application_root_skips_the_django_entry_points() -> None:
    assert ComponentScan.of(BareApplication).default_exclude == DJANGO_ENTRY_POINTS


def test_own_exclusions_come_on_top_of_the_defaults() -> None:
    scan = ComponentScan.of(ApplicationWithOwnExclusions)

    assert scan.exclude == ("*.test_component_scan",)
    assert f"{THIS_PACKAGE}.test_component_scan" not in scan.module_names()
    assert f"{THIS_PACKAGE}.test_application_root" in scan.module_names()


def test_the_decorator_leaves_the_class_itself_unchanged() -> None:
    assert BareApplication.__name__ == "BareApplication"
    assert isinstance(BareApplication(), BareApplication)


def test_a_class_without_the_annotation_is_refused() -> None:
    with pytest.raises(InvalidApplicationRootError, match="NotAnApplication is not an @application_root"):
        ComponentScan.of(NotAnApplication)


def test_a_subclass_does_not_inherit_the_root() -> None:
    class Subclass(BareApplication):
        pass

    with pytest.raises(InvalidApplicationRootError):
        ComponentScan.of(Subclass)


def test_a_class_outside_any_package_cannot_be_a_root() -> None:
    script_class = type("ScriptApplication", (), {"__module__": "standalone_script"})

    with pytest.raises(InvalidApplicationRootError, match="outside any package"):
        application_root(script_class)


def test_a_class_in_a_package_init_scans_that_package() -> None:
    package_class = type("PackageApplication", (), {"__module__": "tests"})

    assert ComponentScan.of(application_root(package_class)).base_packages == ("tests",)

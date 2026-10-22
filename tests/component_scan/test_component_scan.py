"""The component scan names the modules under some packages, minus the excluded ones, without importing them."""

import sys

import pytest

from snakeboot.component_scan import DJANGO_ENTRY_POINTS, SNAKEBOOT_AUTO_CONFIGURATION, ComponentScan

PROJECT = "tests.component_scan.sample_project"
PUBLISHER = "snakeboot.events.application_event_publisher_injectable"


def own_modules(scan: ComponentScan) -> list[str]:
    """The scanned modules without snakeboot's auto-configuration."""
    return [name for name in scan.module_names() if not name.startswith("snakeboot.")]


def test_lists_every_plain_module_below_a_package_sorted_and_without_packages() -> None:
    assert own_modules(ComponentScan((PROJECT,))) == [
        f"{PROJECT}.adapters.console_adapter",
        f"{PROJECT}.components",
        f"{PROJECT}.settings",
    ]


def test_by_default_the_scan_skips_the_entry_points_of_django() -> None:
    names = ComponentScan((PROJECT,)).module_names()

    assert f"{PROJECT}.wsgi" not in names
    assert f"{PROJECT}.asgi" not in names
    assert [name for name in names if ".migrations" in name] == []


def test_the_defaults_are_the_django_entry_points() -> None:
    assert ComponentScan((PROJECT,)).default_exclude == DJANGO_ENTRY_POINTS == ("*.wsgi", "*.asgi", "*.migrations")


def test_the_defaults_can_be_turned_off() -> None:
    names = ComponentScan((PROJECT,), default_exclude=()).module_names()

    assert {f"{PROJECT}.wsgi", f"{PROJECT}.asgi", f"{PROJECT}.migrations.0001_initial"} <= set(names)


def test_finding_the_names_imports_nothing() -> None:
    """The sample wsgi.py raises when imported, as a real one would start Django."""
    names = ComponentScan((PROJECT,), default_exclude=()).module_names()

    assert f"{PROJECT}.wsgi" in names
    assert f"{PROJECT}.wsgi" not in sys.modules


def test_own_exclusions_come_on_top_of_the_defaults() -> None:
    scan = ComponentScan((PROJECT,), exclude=(f"{PROJECT}.adapters",))

    assert own_modules(scan) == [f"{PROJECT}.components", f"{PROJECT}.settings"]
    assert scan.is_excluded(f"{PROJECT}.wsgi")


def test_an_exclusion_may_use_wildcards() -> None:
    assert own_modules(ComponentScan((PROJECT,), exclude=("*.settings", "*.adapters"))) == [f"{PROJECT}.components"]


def test_a_plain_module_is_its_own_scan() -> None:
    module = f"{PROJECT}.components"

    assert own_modules(ComponentScan((module,))) == [module]


def test_an_unknown_package_stops_the_start_up() -> None:
    with pytest.raises(ModuleNotFoundError, match=r"cannot find the package 'tests\.component_scan\.nonexistent'"):
        ComponentScan(("tests.component_scan.nonexistent",)).module_names()


def test_an_unknown_parent_package_stops_the_start_up_too() -> None:
    with pytest.raises(ModuleNotFoundError, match="myapp"):
        ComponentScan(("myapp.nonexistent",)).module_names()


def test_the_scan_adds_the_publisher_snakeboot_provides_like_spring_boot_auto_configuration() -> None:
    assert ComponentScan((PROJECT,)).auto_configuration == SNAKEBOOT_AUTO_CONFIGURATION == (PUBLISHER,)
    assert PUBLISHER in ComponentScan((PROJECT,)).module_names()


def test_an_exclusion_removes_an_auto_configured_module() -> None:
    assert PUBLISHER not in ComponentScan((PROJECT,), exclude=(PUBLISHER,)).module_names()


def test_the_auto_configuration_can_be_turned_off() -> None:
    assert ComponentScan((PROJECT,), auto_configuration=()).module_names() == own_modules(ComponentScan((PROJECT,)))


def test_an_auto_configured_module_is_listed_once_even_when_scanned_as_well() -> None:
    assert ComponentScan(("snakeboot.events",)).module_names().count(PUBLISHER) == 1

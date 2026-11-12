"""`narrowed_application` leaves modules out of an application, and what they define stays out, imported or not."""

import pytest
from wireup.errors import WireupError

from snakeboot.application import ApplicationContext
from snakeboot.boot import CONDITIONAL_MODULES
from snakeboot.component_scan import ComponentScan, application_package, narrowed_application
from snakeboot.openapi import openapi_definition_of
from tests.pytest_testing.library.library_application import LibraryApplication

LEND_BOOK = "tests.pytest_testing.library.loans.lend_book"


def test_the_narrowed_application_keeps_its_package_and_its_declarations() -> None:
    narrowed = narrowed_application(LibraryApplication, [LEND_BOOK])

    assert application_package(narrowed) == application_package(LibraryApplication)
    assert openapi_definition_of(narrowed) == openapi_definition_of(LibraryApplication)
    assert LEND_BOOK in ComponentScan.of(LibraryApplication).module_names()
    assert LEND_BOOK not in ComponentScan.of(narrowed).module_names()


def test_a_component_of_an_excluded_module_stays_out_though_a_kept_module_imports_it() -> None:
    # loan_rest_controller.py imports LendBook; wireup would register it from there.
    narrowed = narrowed_application(LibraryApplication, [LEND_BOOK])

    with pytest.raises(WireupError, match=r"unknown dependency on .*LendBook"):
        ApplicationContext.start(narrowed, CONDITIONAL_MODULES)

"""A slice starts part of an application: `@web_test` its REST layer, `@application_module_test` some of its contexts.

The library has two contexts, one module per role: what a slice leaves out, a test gives as a `MockComponent`.
"""

from unittest.mock import create_autospec

import pytest

from snakeboot.application import ApplicationContext
from snakeboot.boot.testing import RestClient, TestApplication
from snakeboot.rest import BearerAuthentication
from snakeboot.testing import (
    Autowired,
    MockComponent,
    ModuleSlice,
    WebSlice,
    application_module_test,
    signed_in_as,
    verify,
    web_test,
    when,
)
from tests.pytest_testing.library.catalogue.catalogue import Catalogue
from tests.pytest_testing.library.library_application import LibraryApplication
from tests.pytest_testing.library.loans.lend_book import LendBook, LoanDTO, TooManyLoansError

BOOK = "978-0-00-000001-1"

A_MEMBER = signed_in_as("ann", roles={"member"})

library_web_test = web_test(application=LibraryApplication)

loans_test = application_module_test("tests.pytest_testing.library.loans", application=LibraryApplication)


@library_web_test
class TestTheRestLayerAlone:
    client: Autowired[RestClient]
    lend_book: MockComponent[LendBook]
    catalogue: MockComponent[Catalogue]

    def test_a_controller_calls_the_mock_of_its_use_case(self) -> None:
        when(self.lend_book.execute).then_return(LoanDTO(isbn=BOOK, member="ann"))

        response = self.client.post("/api/loans", json={"isbn": BOOK}, headers=A_MEMBER)

        assert (response.status_code, response.json()) == (201, {"isbn": BOOK, "member": "ann"})
        verify(self.lend_book.execute).called_once_with(BOOK, "ann")

    def test_an_advice_answers_what_the_use_case_raises(self) -> None:
        when(self.lend_book.execute).then_raise(TooManyLoansError("ann has two books already."))

        response = self.client.post("/api/loans", json={"isbn": BOOK}, headers=A_MEMBER)

        assert (response.status_code, response.json()["code"]) == (409, "too_many_loans")

    def test_the_roles_of_the_controller_decide(self) -> None:
        a_reader = signed_in_as("rob", roles={"reader"})

        assert self.client.post("/api/loans", json={"isbn": BOOK}, headers=a_reader).status_code == 403
        assert self.client.post("/api/loans", json={"isbn": BOOK}).status_code == 401

    def test_the_tokens_of_the_application_still_count(self) -> None:
        when(self.lend_book.execute).then_return(LoanDTO(isbn=BOOK, member="mia"))

        response = self.client.post("/api/loans", json={"isbn": BOOK}, headers={"Authorization": "Bearer mia-token"})

        assert response.status_code == 201
        verify(self.lend_book.execute).called_once_with(BOOK, "mia")

    def test_every_controller_of_the_application_is_there(self) -> None:
        when(self.catalogue.is_on_the_shelf).then_return(value=True)

        assert self.client.get(f"/api/books/{BOOK}").json() == {"isbn": BOOK, "on_the_shelf": True}

    def test_the_openapi_document_is_the_applications(self) -> None:
        assert self.client.get("/api/openapi.json").json()["info"]["title"] == "Library"


@library_web_test
def test_the_mocks_join_the_slice_in_place_of_what_it_leaves_out(
    context: Autowired[ApplicationContext], lend_book: MockComponent[LendBook], catalogue: MockComponent[Catalogue]
) -> None:
    assert (context.get(LendBook), context.get(Catalogue)) == (lend_book, catalogue)


def test_a_dependency_nobody_gave_stops_the_start_with_its_name() -> None:
    mocks = {Catalogue: create_autospec(Catalogue, instance=True)}

    with pytest.raises(LookupError, match=r"(?s)unknown dependency on .*LendBook.*MockComponent"):
        TestApplication.start(LibraryApplication, mocks, only=WebSlice())


def test_a_mock_cannot_stand_in_for_what_the_slice_holds() -> None:
    mocks: dict[type, object] = {
        LendBook: create_autospec(LendBook, instance=True),
        Catalogue: create_autospec(Catalogue, instance=True),
        BearerAuthentication: create_autospec(BearerAuthentication, instance=True),
    }

    with pytest.raises(LookupError, match=r"(?s)BearerAuthentication.*already exists.*cannot stand in for"):
        TestApplication.start(LibraryApplication, mocks, only=WebSlice())


@loans_test
class TestTheLoansContextAlone:
    client: Autowired[RestClient]
    catalogue: MockComponent[Catalogue]

    def test_its_use_case_runs_with_the_other_context_mocked(self) -> None:
        when(self.catalogue.is_on_the_shelf).then_return(value=True)

        response = self.client.post("/api/loans", json={"isbn": BOOK}, headers=A_MEMBER)

        assert response.status_code == 201
        verify(self.catalogue.is_on_the_shelf).called_once_with(BOOK)

    def test_its_configuration_is_read(self) -> None:
        when(self.catalogue.is_on_the_shelf).then_return(value=True)
        for _ in range(2):  # [loans] max_loans = 2
            self.client.post("/api/loans", json={"isbn": BOOK}, headers=A_MEMBER)

        response = self.client.post("/api/loans", json={"isbn": BOOK}, headers=A_MEMBER)

        assert (response.status_code, response.json()["code"]) == (409, "too_many_loans")

    def test_the_other_context_is_left_out(self) -> None:
        assert self.client.get(f"/api/books/{BOOK}").status_code == 404


def test_a_context_that_needs_another_one_names_what_to_mock() -> None:
    with pytest.raises(LookupError, match=r"(?s)unknown dependency on .*Catalogue.*MockComponent"):
        TestApplication.start(LibraryApplication, only=ModuleSlice(("tests.pytest_testing.library.loans",)))


def test_a_module_test_names_its_packages() -> None:
    with pytest.raises(TypeError, match="names the packages"):
        application_module_test()

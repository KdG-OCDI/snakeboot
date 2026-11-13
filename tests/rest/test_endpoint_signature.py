"""An endpoint's signature says what the call fills in and what the answer holds, in no web framework's terms."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel

from snakeboot.rest import UNDECLARED, EndpointSignature, InvalidRestControllerError, Principal, UploadedFile

if TYPE_CHECKING:
    from decimal import Decimal


class WorkshopDTO(BaseModel):
    title: str


class SummaryDTO(BaseModel):
    seats: int


class WorkshopController:
    """Its annotations are strings (`from __future__ import annotations`), as in many applications."""

    def get(self, workshop_id: str, participant: Principal, verbose: bool = False) -> WorkshopDTO:
        return WorkshopDTO(title=f"{workshop_id} for {participant.name}, {verbose}")

    def remove(self, workshop_id: str) -> None: ...

    def anything(self, workshop_id: str):  # type: ignore[no-untyped-def]  # reason: no annotation under test
        return workshop_id

    def price(self) -> Decimal:
        raise NotImplementedError

    def with_request(self, request: object, workshop_id: str) -> None: ...

    async def asynchronous(self) -> None: ...

    @staticmethod
    def static(workshop_id: str) -> None: ...

    def add_handout(self, workshop_id: str, handout: UploadedFile, title: str) -> None: ...

    def add_handouts(self, workshop_id: str, handouts: list[UploadedFile]) -> None: ...

    def add_optional_handout(self, workshop_id: str, handout: UploadedFile | None = None) -> None: ...


def test_the_call_fills_the_parameters_after_self_and_the_principal_separately() -> None:
    signature = EndpointSignature.of(WorkshopController, WorkshopController.get)

    assert [parameter.name for parameter in signature.parameters] == ["workshop_id", "verbose"]
    assert signature.principal_parameters == ("participant",)


def test_annotations_are_evaluated_where_the_method_is_written() -> None:
    signature = EndpointSignature.of(WorkshopController, WorkshopController.get)

    assert [parameter.annotation for parameter in signature.parameters] == [str, bool]


def test_the_response_is_the_return_annotation() -> None:
    assert EndpointSignature.of(WorkshopController, WorkshopController.get).response is WorkshopDTO


def test_the_response_of_the_route_wins_over_the_return_annotation() -> None:
    assert EndpointSignature.of(WorkshopController, WorkshopController.get, SummaryDTO).response is SummaryDTO


def test_a_method_that_returns_none_answers_with_an_empty_body() -> None:
    assert EndpointSignature.of(WorkshopController, WorkshopController.remove).response is None


def test_without_annotation_and_without_response_the_body_is_undeclared() -> None:
    assert EndpointSignature.of(WorkshopController, WorkshopController.anything).response is UNDECLARED


def test_an_annotation_that_names_nothing_at_run_time_stops_the_start() -> None:
    with pytest.raises(InvalidRestControllerError, match=r"WorkshopController\.price names nothing at run time"):
        EndpointSignature.of(WorkshopController, WorkshopController.price)


def test_an_uploaded_file_is_a_parameter_the_call_carries_and_is_named_apart() -> None:
    signature = EndpointSignature.of(WorkshopController, WorkshopController.add_handout)

    assert [parameter.name for parameter in signature.parameters] == ["workshop_id", "handout", "title"]
    assert signature.upload_parameters == ("handout",)


def test_an_endpoint_without_an_uploaded_file_names_none() -> None:
    assert EndpointSignature.of(WorkshopController, WorkshopController.get).upload_parameters == ()


@pytest.mark.parametrize(
    "method", [WorkshopController.add_handouts, WorkshopController.add_optional_handout], ids=["list", "optional"]
)
def test_an_uploaded_file_other_than_one_plain_parameter_stops_the_start(method) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(InvalidRestControllerError, match="each uploaded file as a parameter of type UploadedFile"):
        EndpointSignature.of(WorkshopController, method)


def test_a_method_that_takes_the_request_stops_the_start() -> None:
    with pytest.raises(InvalidRestControllerError, match="takes `request`, which belongs to the web framework"):
        EndpointSignature.of(WorkshopController, WorkshopController.with_request)


@pytest.mark.parametrize(
    "method", [WorkshopController.asynchronous, WorkshopController.static], ids=["async", "static"]
)
def test_a_method_that_is_no_synchronous_method_stops_the_start(method) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(InvalidRestControllerError):
        EndpointSignature.of(WorkshopController, method)

"""With `[rabbitmq]`, the application of a test sends without a broker: to its own `@rabbit_listener` methods.

Like Spring AMQP's `TestRabbitTemplate`: the message is written as the same JSON, kept in `sent`, and routed as a
topic exchange routes it, through each listener's own conversion.
"""

from uuid import uuid4

import pytest

from snakeboot.rabbitmq import InProcessRabbitTemplate, MessageConversionError, RejectAndDontRequeueError
from snakeboot.rabbitmq.in_process_rabbit_template import _routes
from snakeboot.testing import Autowired, application_test
from snakeboot.transaction import transactional
from tests.pytest_testing.parcels.parcels import (
    CarrierListener,
    ParcelDeliveredMessage,
    ParcelRecords,
    ParcelsApplication,
    SendParcel,
)

parcels_test = application_test(application=ParcelsApplication)


@parcels_test
def test_a_sent_message_is_kept_as_its_json(
    send_parcel: Autowired[SendParcel], rabbit: Autowired[InProcessRabbitTemplate]
) -> None:
    parcel_id = send_parcel.execute("ann")

    [message] = rabbit.sent
    assert (message.exchange, message.routing_key) == ("parcels", f"parcel.{parcel_id}.sent")
    assert message.json() == {"parcel_id": str(parcel_id), "recipient": "ann"}


@parcels_test
def test_every_queue_the_routing_key_reaches_gets_the_message(
    send_parcel: Autowired[SendParcel], carrier: Autowired[CarrierListener]
) -> None:
    send_parcel.execute("ann")

    assert carrier.heard == ["ann"]  # bound with parcel.#; the queue parcels.delivered is not reached


@parcels_test
def test_a_listener_of_the_application_handles_its_message(
    send_parcel: Autowired[SendParcel], rabbit: Autowired[InProcessRabbitTemplate], parcels: Autowired[ParcelRecords]
) -> None:
    parcel_id = send_parcel.execute("ann")

    rabbit.convert_and_send("parcels", f"parcel.{parcel_id}.delivered", ParcelDeliveredMessage(parcel_id=parcel_id))

    parcel = parcels.find_by_id(parcel_id)
    assert parcel is not None
    assert parcel.status == "DELIVERED"
    assert rabbit.refused == []


@parcels_test
def test_a_message_the_listener_refuses_is_kept_with_the_error_and_never_fails_the_sender(
    rabbit: Autowired[InProcessRabbitTemplate],
) -> None:
    unknown = uuid4()

    rabbit.convert_and_send("parcels", f"parcel.{unknown}.delivered", ParcelDeliveredMessage(parcel_id=unknown))

    [refused] = rabbit.refused
    assert refused.listener.endswith("ParcelDeliveredListener.on_parcel_delivered")
    assert isinstance(refused.error, RejectAndDontRequeueError)


@parcels_test
def test_a_body_the_listener_cannot_read_is_refused(rabbit: Autowired[InProcessRabbitTemplate]) -> None:
    rabbit.convert_and_send("parcels", "parcel.42.delivered", {"no": "parcel id"})

    assert isinstance(rabbit.refused[0].error, MessageConversionError)


@parcels_test
def test_the_message_of_a_transaction_that_rolls_back_reaches_no_listener(
    rabbit: Autowired[InProcessRabbitTemplate], carrier: Autowired[CarrierListener]
) -> None:
    @transactional
    def send_and_fail() -> None:
        rabbit.convert_and_send("parcels", "parcel.42.sent", {"recipient": "ann"})
        raise RuntimeError("The transaction rolls back.")

    with pytest.raises(RuntimeError):
        send_and_fail()

    assert (len(rabbit.sent), carrier.heard) == (1, [])


@pytest.mark.parametrize(
    ("binding_key", "routing_key", "routed"),
    [
        ("parcel.*.sent", "parcel.42.sent", True),
        ("parcel.*.sent", "parcel.42.delivered", False),
        ("parcel.*", "parcel.42.sent", False),
        ("parcel.#", "parcel", True),
        ("parcel.#", "parcel.42.sent", True),
        ("#.sent", "parcel.42.sent", True),
        ("#", "any.key.at.all", True),
        ("parcel.42", "parcel.42", True),
        ("parcel.42", "parcel.43", False),
    ],
)
def test_the_routing_of_a_topic_exchange(binding_key: str, routing_key: str, *, routed: bool) -> None:
    assert _routes(binding_key, routing_key) is routed

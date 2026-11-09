"""The application is UP when every part is; a part whose check raises is DOWN."""

from typing import override

import pytest

from snakeboot.actuator import ApplicationHealth, HealthIndicator, InvalidHealthIndicatorError, Status


class PaymentGatewayHealthIndicator(HealthIndicator, component=False):
    def __init__(self, *, up: bool = True) -> None:
        self.up = up

    @override
    def check(self) -> None:
        if not self.up:
            raise ConnectionError("the gateway does not answer")


class MailServerHealthIndicator(HealthIndicator, component=False):
    @override
    def check(self) -> None:
        pass


def test_without_indicators_the_application_is_up() -> None:
    report = ApplicationHealth(()).report()

    assert (report.status, report.components) == (Status.UP, {})


def test_the_application_is_up_when_every_part_is() -> None:
    report = ApplicationHealth([PaymentGatewayHealthIndicator(), MailServerHealthIndicator()]).report()

    assert report.status is Status.UP
    assert report.components == {"mail_server": Status.UP, "payment_gateway": Status.UP}


def test_a_part_whose_check_raises_is_down_and_so_is_the_application(caplog: pytest.LogCaptureFixture) -> None:
    report = ApplicationHealth([PaymentGatewayHealthIndicator(up=False), MailServerHealthIndicator()]).report()

    assert report.status is Status.DOWN
    assert report.components == {"mail_server": Status.UP, "payment_gateway": Status.DOWN}
    assert "the gateway does not answer" in caplog.text


def test_the_name_of_a_part_comes_from_its_class() -> None:
    assert PaymentGatewayHealthIndicator().name == "payment_gateway"


def test_two_indicators_of_one_name_stop_the_start() -> None:
    with pytest.raises(InvalidHealthIndicatorError, match="Two health indicators are named payment_gateway"):
        ApplicationHealth([PaymentGatewayHealthIndicator(), PaymentGatewayHealthIndicator()])


def test_a_subclass_is_a_component_and_one_kept_out_is_not() -> None:
    class DiskHealthIndicator(HealthIndicator):
        @override
        def check(self) -> None:
            pass

    assert "__wireup_registration__" in vars(DiskHealthIndicator)
    assert "__wireup_registration__" not in vars(MailServerHealthIndicator)

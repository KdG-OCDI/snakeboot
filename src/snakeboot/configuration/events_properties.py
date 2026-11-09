from datetime import timedelta
from typing import Self

from pydantic import model_validator

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("events")
class EventsProperties(Section):
    """The optional section `[events]`: when the event publication registry delivers again, like Spring Modulith's
    `spring.modulith.events.*`.

    Without the section, snakeboot's own timing holds: every 30 seconds a look for what is due, 5 minutes for a
    delivery before it counts as lost, 30 seconds times the tries so far after a failure, and 10 tries. A time is a
    number of seconds or an ISO 8601 duration ("PT5M"):

        [events]
        resubmit_every = 30             # how often the registry is asked what is due
        in_flight = "PT5M"              # longer than the slowest @application_module_listener takes
        retry_after = 30                # after a failure, times the tries so far: 30 s, 1 min, 1.5 min, ...
        max_attempts = 10               # then the publication waits in the table for a person
    """

    resubmit_every: timedelta
    in_flight: timedelta
    retry_after: timedelta
    max_attempts: int

    @model_validator(mode="after")
    def _refuse_times_that_are_not_positive(self) -> Self:
        if min(self.resubmit_every, self.in_flight, self.retry_after) <= timedelta(0) or self.max_attempts < 1:
            raise ValueError("[events] needs positive times and one attempt at least.")
        return self

from dataclasses import dataclass
from datetime import timedelta

from snakeboot.rest import ServerSentEvent, ServerSentEvents, rest_controller, route


@dataclass(frozen=True)
class ScoreDTO:
    points: int
    final: bool


class Scoreboard:
    """Stands in for a use case: the score goes up by one every read, and is final at 3."""

    def __init__(self) -> None:
        self._points = 0

    def read(self) -> ScoreDTO:
        self._points += 1
        return ScoreDTO(self._points, final=self._points == 3)


@rest_controller("/scores")
class ScoreboardRestController:
    """Sample controller that streams the score until it is final."""

    @route.get("/events")
    def watch_score(self) -> ServerSentEvents:
        return ServerSentEvents.watching(
            Scoreboard().read,
            every=timedelta(0),
            until=lambda score: score.final,
            as_event=lambda score: ServerSentEvent(score, event="score", id=str(score.points)),
        )

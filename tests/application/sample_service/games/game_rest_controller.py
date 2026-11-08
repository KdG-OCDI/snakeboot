import logging
from functools import partial
from uuid import UUID, uuid4

from pydantic import BaseModel
from wireup import injectable

from snakeboot.rest import error_answer, exception_handler, rest_controller, rest_controller_advice, route
from snakeboot.transaction import after_commit, transactional
from tests.application.sample_service.games.game_record import GameRecord, GameRecords

logger = logging.getLogger(__name__)


class NewGameDTO(BaseModel):
    status: str


class GameDTO(BaseModel):
    game_id: UUID
    status: str
    board: list[str]


class UnknownGameError(LookupError):
    """No game has the id."""


@injectable
class Announcer:
    """Stands in for a port that tells the world about a new game, once its transaction committed."""

    def announce(self, game_id: UUID) -> None:
        logger.info("Game %s started", game_id)


@rest_controller("/games")
class GameRestController:
    def __init__(self, games: GameRecords, announcer: Announcer) -> None:
        self._games = games
        self._announcer = announcer

    @route.post("", status=201)
    @transactional
    def start(self, body: NewGameDTO) -> GameDTO:
        game = self._games.save(GameRecord(uuid4(), body.status, [""] * 9))
        after_commit(partial(self._announcer.announce, game.game_id))
        return GameDTO(game_id=game.game_id, status=game.status, board=game.board)

    @route.get("/{game_id}")
    def game(self, game_id: UUID) -> GameDTO:
        game = self._games.find_by_id(game_id)
        if game is None:
            raise UnknownGameError(f"No game has the id {game_id}.")
        return GameDTO(game_id=game.game_id, status=game.status, board=game.board)


@rest_controller_advice
class GameErrorAdvice:
    @exception_handler(UnknownGameError, status=404)
    def answer_unknown_game(self, error: Exception) -> dict[str, str]:
        return error_answer(error)

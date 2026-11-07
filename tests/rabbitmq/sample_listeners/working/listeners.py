"""A listener that takes a pydantic model, refuses some messages and fails on others."""

import threading

from pydantic import BaseModel

from snakeboot.rabbitmq import RejectAndDontRequeueError, rabbit_listener


class GameStarted(BaseModel):
    """Stands in for the message a platform sends."""

    session_id: str
    player_ids: list[str]


class GameStartedListener:
    """Stands in for an inbound adapter: remembers every game it was told to start."""

    def __init__(self) -> None:
        self.started: list[GameStarted] = []
        self.attempts: dict[str, int] = {}
        self.received = threading.Event()

    @rabbit_listener(queue="tictactoe.game-started", exchange="games", routing_key="game.tictactoe.started")
    def on_game_started(self, message: GameStarted) -> None:
        """Starts a game. A session `refuse` breaks the rules, `crash` always meets a database that is down,
        `flaky` only the first time."""
        attempt = self.attempts[message.session_id] = self.attempts.get(message.session_id, 0) + 1
        if message.session_id == "flaky" and attempt == 1:
            raise RuntimeError("the database was down for a moment")
        if message.session_id == "refuse":
            raise RejectAndDontRequeueError("this game breaks the rules")
        if message.session_id == "crash":
            raise RuntimeError("the database is down")
        self.started.append(message)
        self.received.set()

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """Whoever the bearer token of a call belongs to, like a parameter with Spring's `@AuthenticationPrincipal`.

    An endpoint asks for it with a parameter of this type; `name` is the id that the API's `BearerAuthentication`
    returned for the token. The web framework fills the parameter, so the method stays a plain method that a test
    calls with a principal of its own.

        @route.post("/games/{game_id}/players")
        def join_game(self, game_id: str, player: Principal) -> GameDTO:
            return self._join_game.execute(JoinGameRequestDTO(game_id=game_id, player_id=player.name))
    """

    name: str

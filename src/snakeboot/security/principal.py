from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Principal:
    """Whoever the bearer token of a call belongs to, and the roles granted to them, like Spring's `Authentication`.

    An endpoint asks for it with a parameter of this type, like `@AuthenticationPrincipal`; `name` is the id that the
    API's `BearerAuthentication` found for the token, `roles` what it may do (`@roles_allowed` checks them). The web
    framework fills the parameter, so the method stays a plain method that a test calls with a principal of its own.

        @route.post("/games/{game_id}/players")
        def join_game(self, game_id: str, player: Principal) -> GameDTO:
            return self._join_game.execute(JoinGameRequestDTO(game_id=game_id, player_id=player.name))
    """

    name: str
    roles: frozenset[str] = field(default=frozenset())

    def has_role(self, role: str) -> bool:
        """Tells whether the principal was granted `role`, like Spring's `hasRole`."""
        return role in self.roles

    def has_any_role(self, roles: Iterable[str]) -> bool:
        """Tells whether the principal was granted one of `roles`, like Spring's `hasAnyRole`."""
        return not self.roles.isdisjoint(roles)

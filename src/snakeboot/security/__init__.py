"""Technical library: who the work in hand is done for, like Spring Security's `Authentication` and its holder.

    @route.delete("/{game_id}")
    @roles_allowed("admin")                              # snakeboot.rest, like @RolesAllowed
    def delete_game(self, game_id: str, admin: Principal) -> None: ...

    SecurityContext.current()                            # the Principal of the running call, or None

A `Principal` is a name and the roles granted to it; the `BearerAuthentication` of the API finds both in the token.
`SecurityContext` holds the principal of the call in hand, so the auditing of the entities knows who changed them.
It uses the standard library only: the REST library, the web binding and the data library all ask it.
"""

from snakeboot.security.principal import Principal
from snakeboot.security.security_context import SecurityContext

__all__ = ["Principal", "SecurityContext"]

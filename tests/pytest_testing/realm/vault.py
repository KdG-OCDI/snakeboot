"""A vault that only keepers open, with the tokens of a Keycloak realm: its own `JwtBearerAuthentication` reads them."""

from snakeboot.component_scan import application_root
from snakeboot.oauth2 import JwtBearerAuthentication
from snakeboot.rest import rest_controller, roles_allowed, route
from snakeboot.security import Principal


@application_root
class RealmApplication:
    """Keycloak's tokens, checked and mapped to roles by the application's own authentication."""


class VaultTokens(JwtBearerAuthentication):
    """The realm's access tokens: Keycloak's realm roles and client roles become the caller's roles."""


@rest_controller("/vault")
@roles_allowed("keeper")
class VaultRestController:
    @route.get("")
    def open_the_vault(self, caller: Principal) -> dict[str, object]:
        return {"name": caller.name, "roles": sorted(caller.roles)}

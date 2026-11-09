from snakeboot.rest import rest_controller, roles_allowed, route
from snakeboot.security import Principal, SecurityContext


@rest_controller("/admin/workshops")
@roles_allowed("organizer")
class WorkshopAdminRestController:
    """Sample controller whose endpoints only organizers call, unless an endpoint says otherwise."""

    @route.get("")
    def list_workshops(self, caller: Principal) -> dict[str, object]:
        return {"name": caller.name, "roles": sorted(caller.roles)}

    @route.delete("/{workshop_id}", status=204)
    @roles_allowed("organizer", "moderator")
    def cancel_workshop(self, workshop_id: str) -> None:
        return None

    @route.get("/signed-in")
    def signed_in(self) -> dict[str, str | None]:
        principal = SecurityContext.current()
        return {"signed_in": principal.name if principal is not None else None}

    @route.get("/catalogue", public=True)
    def catalogue(self) -> dict[str, str | None]:
        principal = SecurityContext.current()
        return {"signed_in": principal.name if principal is not None else None}

class InvalidRestControllerError(TypeError):
    """Raised at start-up when a class or method cannot become a REST controller or endpoint.

    Failing while mounting, not at the first request, is the point: a broken controller
    must stop the application from starting, like a missing bean in Spring.
    """


class NoAuthenticatedPrincipalError(TypeError):
    """Raised when an endpoint asks who is signed in, but no authentication answered with an id.

    It is a programming error, not a client error: the endpoint opted out of
    authentication (`auth=None`) or the installed authentication returns something else.
    """

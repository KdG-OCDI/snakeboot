class InvalidRestControllerError(TypeError):
    """Raised at start-up when the REST API cannot be served as declared.

    A class or method that cannot become a controller, endpoint or error answer, two endpoints for one URL, two
    answers for one error, two authentications, or a `Principal` nobody can supply. Failing while the API is built,
    not at the first request, is the point: a broken controller must stop the application from starting, like a
    missing bean in Spring.
    """


class NoAuthenticatedPrincipalError(TypeError):
    """Raised when an endpoint asks who called, but the authentication answered with something other than an id.

    It is a programming error, not a client error: the installed `BearerAuthentication` returned something else
    than a string.
    """

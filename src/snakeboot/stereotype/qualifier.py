from wireup import Inject


def Qualifier(name: str) -> object:  # noqa: N802  # reads as Spring's @Qualifier inside Annotated[...], like Id()
    """Asks for the component of a type that was declared with the qualifier `name`, like Spring's `@Qualifier`.

    Several components of one type are told apart by the `qualifier` of their `@component` or `@bean`; a parameter
    names the one it wants beside its type:

        def __init__(self, opener: Annotated[OpenerDirector, Qualifier("templates")]) -> None: ...
    """
    return Inject(qualifier=name)

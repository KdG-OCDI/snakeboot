"""Technical library: the names under which a class joins the container, like `org.springframework.stereotype`.

    @service                                  # @Service: a use case, built once, its dependencies by type
    class PlaceBidUseCase:
        def __init__(self, auctions: AuctionRepositoryPort) -> None: ...

    @repository(as_type=AuctionRepositoryPort)   # @Repository: the adapter others ask for by its port
    class AuctionPersistenceAdapter(AuctionRepositoryPort): ...

    @component(as_type=ClockPort)             # @Component: any other component
    class SystemClock(ClockPort): ...

    @bean                                     # @Bean: a function that builds a component
    def http_opener(properties: DownloadProperties) -> OpenerDirector: ...

The three class decorators do the same; the name says what the class is, to the reader and to an architecture test
(`stereotype_of`, or `ComponentScan.classes_marked(STEREOTYPE_ATTRIBUTE)`). With them an application names no
container: wireup stays underneath, as FastAPI and SQLAlchemy do. The library knows wireup and nothing else.
"""

from snakeboot.stereotype.bean import bean
from snakeboot.stereotype.qualifier import Qualifier
from snakeboot.stereotype.stereotypes import (
    STEREOTYPE_ATTRIBUTE,
    InvalidComponentError,
    Stereotype,
    component,
    repository,
    service,
    stereotype_of,
)

__all__ = [
    "STEREOTYPE_ATTRIBUTE",
    "InvalidComponentError",
    "Qualifier",
    "Stereotype",
    "bean",
    "component",
    "repository",
    "service",
    "stereotype_of",
]

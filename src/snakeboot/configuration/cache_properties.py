from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("cache")
class CacheProperties(Section):
    """The section `[cache]`: the Redis that backs the application's cache, like Spring Boot's `spring.data.redis.*`.

    snakeboot hands it to the cache of the framework when the table is there.
    """

    redis_url: str

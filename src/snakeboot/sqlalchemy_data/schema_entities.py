"""Which entities make the schema: every one of the application's, a library's only when the application uses it."""

from snakeboot.data import ENTITY_ATTRIBUTE, description_of
from snakeboot.lifecycle.application_components import ApplicationComponents


def entities_of_the_schema(components: ApplicationComponents) -> list[type]:
    """Returns the entities whose tables the schema holds: every `@entity` of the component scan, but one that names
    the methods that need it (`needed_by`) only when a method of the scan carries that mark.

    So an application without `@application_module_listener` or `@scheduler_lock` methods needs no table of
    snakeboot's own: neither its migrations nor `make_migration` hold one, as a Spring Boot application has no
    `event_publication` or `shedlock` table before it has Spring Modulith's or ShedLock's starter.
    """
    return [
        entity_type
        for entity_type in components.classes_marked(ENTITY_ATTRIBUTE)
        if _needed(description_of(entity_type).needed_by, components)
    ]


def _needed(mark: str | None, components: ApplicationComponents) -> bool:
    return mark is None or any(marked.mapping is not None for marked in components.methods_marked(mark, object))

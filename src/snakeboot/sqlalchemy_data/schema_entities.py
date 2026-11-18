"""Which entities make the schema: every one of the application's, a library's only when the application uses it."""

from functools import cache

from snakeboot.data import ENTITY_ATTRIBUTE, description_of
from snakeboot.lifecycle.application_components import ApplicationComponents


def entities_of_the_schema(components: ApplicationComponents) -> list[type]:
    """Returns the entities whose tables the schema holds: every `@entity` of the component scan, but one that names
    the marks that need it (`needed_by`) only when a method or a class of the scan carries one of them.

    So an application without `@application_module_listener` methods, `@externalized` events, stream listeners or
    `@scheduler_lock` methods needs no table of snakeboot's own: neither its migrations nor `make_migration` hold one,
    as a Spring Boot application has no `event_publication` or `shedlock` table before it has Spring Modulith's or
    ShedLock's starter. Each mark is looked up once, however many entities name it.
    """

    @cache
    def carried(mark: str) -> bool:
        on_a_method = any(marked.mapping is not None for marked in components.methods_marked(mark, object))
        return on_a_method or bool(components.classes_marked(mark))

    def needed(marks: str | tuple[str, ...] | None) -> bool:
        return marks is None or any(carried(mark) for mark in ((marks,) if isinstance(marks, str) else marks))

    return [
        entity_type
        for entity_type in components.classes_marked(ENTITY_ATTRIBUTE)
        if needed(description_of(entity_type).needed_by)
    ]

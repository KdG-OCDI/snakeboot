from datetime import UTC, datetime

from snakeboot.data.entity import (
    ENTITY_ATTRIBUTE,
    CreatedBy,
    CreatedDate,
    EntityDescription,
    LastModifiedBy,
    LastModifiedDate,
)
from snakeboot.security import SecurityContext


def audit(entity: object) -> None:
    """Fills the audit fields of `entity`, which is about to be inserted or updated, like Spring Data's
    `AuditingHandler` called from JPA's `@PrePersist` and `@PreUpdate`.

    The binding of a persistence framework calls it for every entity it is about to write, whether `save` wrote it or
    the transaction found it changed: a `CreatedDate` or `CreatedBy` that is still empty once, every `LastModifiedDate`
    and `LastModifiedBy` each time. The date is the moment of the write (the flush), in UTC; the auditor is the
    principal the `SecurityContext` holds on the writing thread then, or None. A class that is no entity, or an entity
    without audit fields, is left alone.
    """
    description = vars(type(entity)).get(ENTITY_ATTRIBUTE)
    if not isinstance(description, EntityDescription):
        return
    now, principal = datetime.now(UTC), SecurityContext.current()
    auditor = principal.name if principal is not None else None
    for prop in description.properties:
        empty = getattr(entity, prop.name) is None
        if prop.marker(LastModifiedDate) is not None or (prop.marker(CreatedDate) is not None and empty):
            setattr(entity, prop.name, now)
        elif prop.marker(LastModifiedBy) is not None or (prop.marker(CreatedBy) is not None and empty):
            setattr(entity, prop.name, auditor)

from typing import override

from django.db import models


class LooseOrmEntity(models.Model):
    """A model in a package without an AppConfig: Django would not know its table."""

    text = models.TextField()

    @override
    def __str__(self) -> str:
        return str(self.text)

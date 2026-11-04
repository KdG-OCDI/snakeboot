from typing import override

from django.db import models

raise RuntimeError("The component scan reads this file; it must never import it.")


class NoteOrmEntity(models.Model):
    text = models.TextField()

    @override
    def __str__(self) -> str:
        return str(self.text)

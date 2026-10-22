from typing import override

from django.db import models


class NoteRecord(models.Model):
    """One row to write in a transaction; the tests check whether it was committed or rolled back."""

    text = models.CharField(max_length=100)

    @override
    def __str__(self) -> str:
        return self.text

from typing import override

from django.db import models


class GreetingOrmEntity(models.Model):
    text = models.TextField()

    @override
    def __str__(self) -> str:
        return str(self.text)

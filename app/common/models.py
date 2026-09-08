import uuid
from django.db import models


class BaseModel(models.Model):
    """
    Abstract base model that provides:
      - UUID primary key (`id`)
      - Creation timestamp (`created_at`)
      - Last update timestamp (`updated_at`)
    All application models can inherit from this class.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier (UUID v4)",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the record was created",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the record was last updated",
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]

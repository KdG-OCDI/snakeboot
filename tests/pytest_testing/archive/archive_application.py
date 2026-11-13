"""An archive that moved in from another framework with its data: its V1 is pg_dump's, which SQLite refuses."""

from snakeboot.component_scan import application_root


@application_root
class ArchiveApplication:
    """Clerks file documents; a clerk calls the API with a key of their own, which the database keeps."""

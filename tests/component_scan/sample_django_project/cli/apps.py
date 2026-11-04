from django import apps


class NotesCliConfig(apps.AppConfig):
    name = "tests.component_scan.sample_django_project.cli"
    label = "notes_cli"

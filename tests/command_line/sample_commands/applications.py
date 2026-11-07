"""Applications whose component scans hold commands."""

from snakeboot.component_scan import application_root


@application_root(base_packages=("tests.command_line.sample_commands.commands",))
class CommandsApplication:
    pass


@application_root(base_packages=("tests.command_line.ambiguous_commands",))
class AmbiguousCommandsApplication:
    pass


@application_root(base_packages=("tests.command_line.clashing_commands",))
class ClashingCommandsApplication:
    pass


@application_root(base_packages=("snakeboot.transaction",))
class ApplicationWithoutCommands:
    pass

class CommandLineError(Exception):
    """Raised by a command to stop with a message and exit status 1, like Spring Shell's `CommandExecutionException`.

    The message is for whoever typed the command: what was wrong with the arguments, or why the work cannot be done.
    Any other exception is a bug and stops the command with its traceback.
    """


class InvalidCommandLineRunnerError(TypeError):
    """Raised at start-up when a class cannot be a command: no name, a name that cannot be typed, two classes for one
    name, or no `run` method.

    Like a broken controller, a broken command stops the application while it starts.
    """

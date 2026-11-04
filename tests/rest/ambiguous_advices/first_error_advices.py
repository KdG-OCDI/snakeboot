from snakeboot.rest import error_answer, exception_handler, rest_controller_advice


class FirstError(Exception):
    pass


@rest_controller_advice
class FirstAdvice:
    @exception_handler(FirstError, status=409)
    def answer(self, error: Exception) -> dict[str, str]:
        return error_answer(error)


@rest_controller_advice
class SecondAdvice:
    @exception_handler(FirstError, status=422)
    def answer(self, error: Exception) -> dict[str, str]:
        return error_answer(error)

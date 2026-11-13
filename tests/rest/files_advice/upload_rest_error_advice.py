from snakeboot.rest import UploadTooLargeError, error_answer, exception_handler, rest_controller_advice


@rest_controller_advice
class UploadRestErrorAdvice:
    """Answers a file too large with snakeboot's body and the limit, so a client can tell its user."""

    @exception_handler(UploadTooLargeError, status=413)
    def answer_upload_too_large(self, error: UploadTooLargeError) -> dict[str, object]:
        return {**error_answer(error), "max_size": error.max_size}

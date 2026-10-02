class ChatstyleError(Exception):
    """Понятная пользователю ошибка chatstyle."""


class CodedError(ChatstyleError):
    """Ошибка с кодом и параметрами: русский текст остаётся для CLI, а окно переводит по коду."""

    def __init__(self, code: str, message: str, /, **params: object) -> None:
        super().__init__(message)
        self.code = code
        self.params = {key: str(value) for key, value in params.items()}

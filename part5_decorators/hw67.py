import json
from datetime import UTC, datetime
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar
from urllib.request import urlopen

INVALID_CRITICAL_COUNT = "Breaker count must be positive integer!"
INVALID_RECOVERY_TIME = "Breaker recovery time must be positive integer!"
VALIDATIONS_FAILED = "Invalid decorator args."
TOO_MUCH = "Too much requests, just wait."


P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)


class CallableWithMeta(Protocol[P, R_co]):
    __name__: str
    __module__: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R_co: ...


class BreakerError(Exception):
    def __init__(self, func_name: str, block_time: datetime) -> None:
        self.func_name = func_name
        self.block_time = block_time
        super().__init__(TOO_MUCH)


class CircuitBreaker:
    def __init__(
        self,
        critical_count: int = 5,
        time_to_recover: int = 30,
        triggers_on: type[Exception] = Exception,
    ) -> None:
        exceptions = []
        if critical_count <= 0 or not isinstance(critical_count, int):
            exceptions.append(ValueError(INVALID_CRITICAL_COUNT))

        if time_to_recover <= 0 or not isinstance(time_to_recover, int):
            exceptions.append(ValueError(INVALID_RECOVERY_TIME))

        if exceptions:
            raise ExceptionGroup(VALIDATIONS_FAILED, exceptions)

        self.critical_count = critical_count
        self.time_to_recover = time_to_recover
        self.triggers_on = triggers_on
        self.count = 0
        self.time_closed: datetime | None = None

    def __call__(self, func: CallableWithMeta[P, R_co]) -> CallableWithMeta[P, R_co]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R_co:
            block_time = self._active_block_time()
            if block_time is not None:
                raise BreakerError(self._full_name(func), block_time)
            try:
                return self._call_and_reset(func, *args, **kwargs)
            except self.triggers_on as error:
                self._handle_failure(func, error)
                raise

        return wrapper

    def _call_and_reset(self, func: CallableWithMeta[P, R_co], *args: P.args, **kwargs: P.kwargs) -> R_co:
        result = func(*args, **kwargs)
        self._reset()
        return result

    def _handle_failure(self, func: CallableWithMeta[P, R_co], error: Exception) -> None:
        if self.count + 1 >= self.critical_count:
            self.count = self.critical_count
            self.time_closed = datetime.now(UTC)
            raise BreakerError(self._full_name(func), self.time_closed) from error
        self.count += 1

    def _active_block_time(self) -> datetime | None:
        if self.time_closed is None or self.count < self.critical_count:
            return None
        elapsed = (datetime.now(UTC) - self.time_closed).total_seconds()
        if elapsed < self.time_to_recover:
            return self.time_closed
        self._reset()
        return None

    def _reset(self) -> None:
        self.count = 0
        self.time_closed = None

    def _full_name(self, func: CallableWithMeta[P, R_co]) -> str:
        return f"{func.__module__}.{func.__name__}"


circuit_breaker = CircuitBreaker(5, 30, Exception)


# @circuit_breaker
def get_comments(post_id: int) -> Any:
    """
    Получает комментарии к посту

    Args:
        post_id (int): Идентификатор поста

    Returns:
        list[dict[int | str]]: Список комментариев
    """
    response = urlopen(f"https://jsonplaceholder.typicode.com/comments?postId={post_id}")
    return json.loads(response.read())


if __name__ == "__main__":
    comments = get_comments(1)

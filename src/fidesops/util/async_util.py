import asyncio
from typing import TypeVar, Callable, Any, Awaitable, Optional
import logging

logger = logging.getLogger(__name__)
T = TypeVar("T")

def _loop():
    asyncio.set_event_loop(asyncio.SelectorEventLoop())
    return asyncio.get_event_loop()
def run_async(task: Callable[[Any], T], *args: Any) -> Awaitable[T]:
    """Run a callable async"""
    if not callable(task):
        raise TypeError("Task must be a callable")

    return _loop().run_in_executor(None, task, *args)


def wait_for(t: Awaitable[T]) -> Optional[T]:
    """Wait for the return of a callable. This is mostly intended
    to be used for testing async tasks."""
    return asyncio.get_event_loop().run_until_complete(t)


def close():
    _loop().close()

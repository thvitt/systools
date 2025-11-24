import asyncio
from os import process_cpu_count
from typing import AsyncGenerator, AsyncIterable, Awaitable, Callable, Iterable


async def map_unordered[T, R](
    func: Callable[[T], Awaitable[R]],
    iterable: Iterable[T] | AsyncIterable[T],
    *,
    limit: int | None = None,
) -> AsyncGenerator[R, None]:
    """
    Executes the given async function `func` on each item from `iterable`, yielding results as they complete, while limiting the number of concurrent tasks to `limit`.
    This function will not consume more items from iterable than it can start while maintaining the concurrency limit.

    Args:
        func: a coroutine function to apply to each item of the given iterable
        iterable: an iterable or async iterable of items to process
        limit: Maximum number of concurrent tasks. If None, defaults to the number of CPU cores available to the process.

    Returns:
        The results of the function calls, in the order they complete.

    See also:
        https://death.andgravity.com/limit-concurrency
    """
    if isinstance(iterable, AsyncIterable):
        aws = (func(x) async for x in iterable)
    else:
        aws = map(func, iterable)

    async for task in limit_concurrency(aws, limit):
        yield await task


async def limit_concurrency[T](
    tasks: Iterable[Awaitable[T]] | AsyncIterable[Awaitable[T]],
    limit: int | None = None,
) -> AsyncGenerator[asyncio.Task[T], None]:
    """
    Run at most `limit` of the given awaitables concurrently, yielding completed tasks as they finish.
    """
    if limit is None:
        limit = process_cpu_count() or 4

    if isinstance(tasks, AsyncIterable):
        task_iterator = aiter(tasks)
    else:
        task_iterator = iter(tasks)

    pending: set[asyncio.Task[T]] = set()

    while pending:
        while len(pending) < limit:
            if isinstance(task_iterator, AsyncIterable):
                awaitable = await anext(task_iterator)
            else:
                awaitable = next(task_iterator)
            pending.add(asyncio.ensure_future(awaitable))

        if not pending:
            return

        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

        while done:
            yield done.pop()

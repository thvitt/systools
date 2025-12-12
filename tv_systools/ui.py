from rich.text import Text
from collections import Counter
from typing import Callable, Optional, Sequence, override

from pzp import pzp
from rich import get_console
from rich.console import RenderableType
from rich.progress import ProgressColumn, Task
from rich.table import Column, Table


def pzp_table[T](
    items: Sequence[T],
    columns: Sequence | None = None,
    row_factory: Callable[[T], Sequence] | None = None,
) -> T:
    items = list(items)[:10]
    if columns is None:
        if hasattr(items[0], "__columns__"):
            columns = items[0].__columns__()  # pyright: ignore[reportAttributeAccessIssue]
        else:
            columns = [""]
    assert columns is not None
    if row_factory is None:

        def _row_factory(item: T):
            if hasattr(item, "__row__"):
                return item.__row__()  # pyright: ignore[reportAttributeAccessIssue]
            else:
                return str(item)

        row_factory = _row_factory
    table = Table(*columns, box=None)
    for item in items:
        table.add_row(*row_factory(item))
    console = get_console()
    with console.capture() as capture:
        console.print(table)
    header, *lines = capture.get().splitlines()
    result_map = dict(zip(lines, items))
    result_line = pzp(lines, header_str="  " + header, fullscreen=False)
    return result_map[result_line]


class SubtasksColumn(ProgressColumn):
    """
    A column that shows a list of currently running tasks, like e.g. cargo build does.
    Add tasks using add, remove them using rm.
    """

    subtasks: Counter[str]

    def __init__(self, table_column: Optional[Column] = None) -> None:
        super().__init__(table_column)
        self.subtasks = Counter()

    def add(self, subtask: str) -> None:
        self.subtasks.update((subtask,))

    def rm(self, subtask: str) -> None:
        self.subtasks.pop(subtask)

    @override
    def render(self, task: Task) -> RenderableType:
        return Text(", ".join(self.subtasks.keys()), overflow="ellipsis")


class RenderableExtraColumn(ProgressColumn):
    def __init__(
        self, extra_key: str, default: str = "", table_column: Optional[Column] = None
    ):
        super().__init__(table_column=table_column)
        self.extra_key = extra_key
        self.default = default

    def render(self, task: Task) -> Text:
        return task.fields.get(self.extra_key, Text(self.default))

from typing import Callable, Sequence
from rich import get_console
from rich.table import Table
from pzp import pzp


def pzp_table[
    T
](
    items: Sequence[T],
    columns: Sequence | None = None,
    row_factory: Callable[[T], Sequence] | None = None,
) -> T:
    items = list(items)[:10]
    if columns is None:
        if hasattr(items[0], "__columns__"):
            columns = items[0].__columns__()
        else:
            columns = [""]
    if row_factory is None:

        def _row_factory(item: T):
            if hasattr(item, "__row__"):
                return item.__row__()
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

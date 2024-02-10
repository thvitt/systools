#!/usr/bin/python3
import argparse

import apt
import rich
from pathlib import Path
from dateutil.parser import parse as parse_date
from datetime import datetime
from typing import Optional, List, Union, Iterable, Tuple
from os.path import commonprefix
import re

from rich.console import Console, ConsoleOptions, RenderResult
from rich.measure import Measurement
from rich.text import Text

_cache = apt.Cache()

console = Console()


class LogRecord:
    operations = {
        'install': '+',
        'remove': '-',
        'upgrade': '↑',
        'downgrade': '↓',
        'purge': '✘',
        'reinstall': '↺'
    }

    commandline: str = ''
    requested_by: str = ''
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    error: Optional[str] = None
    install: List[apt.Package] = []
    reinstall: List[apt.Package] = []
    upgrade: List[apt.Package] = []
    downgrade: List[apt.Package] = []
    remove: List[apt.Package] = []
    purge: List[apt.Package] = []

    def __init__(self, logstring: str):
        self.raw = logstring
        lines = logstring.split('\n')
        ops = []
        for line in lines:
            if ': ' in line:
                key_, value = line.split(': ')
                key = key_.strip().lower().replace('-', '_')
                if key.endswith('date'):
                    setattr(self, key, parse_date(value))
                elif key in self.operations:
                    setattr(self, key, self._parse_pkg_list(value, key))
                    ops.append(key)
                else:
                    setattr(self, key, value)
                    if key not in {'requested_by', 'error', 'commandline'}:
                        console.log(f'Unknown entry: [italic]{key}: {value}')
        self.ops = ops

    def _parse_pkg_list(self, raw: str, op: str) -> List[apt.Package]:
        matches = re.finditer(r"(\S+)\s*\((\S+)?(?:, (\S+))?\)(?:,\s+)?", raw)
        result = [PackageDescriptor(match, op) for match in matches]
        if not result:
            console.print(f'Parsing package list {op}: {raw} ⇒ 0 results')
        return result

    def __getitem__(self, item):
        if item in self.operations:
            return getattr(self, item)
        else:
            raise KeyError(f'{item} is not one of the operations: {", ".join(self.operations)}')

    def __iter__(self):
        for key in self.operations:
            yield from self[key]

    def __str__(self):
        opstrs = [self.operations[op] + str(len(self[op])) for op in self.ops]
        result = f'{self.start_date:%Y-%m-%d %H:%M}: '
        if self.error:
            result += self.error + ' '
        result += f'{" ".join(opstrs)}, {self.commandline} by {self.requested_by}'
        return result

    def __repr__(self):
        return f'<{self.__class__.__name__}: {self}>'


class Version:
    """
    Represents either a version or a version number update.
    """

    def __init__(self, version, old_version=None):
        self.version = str(version)
        self.old_version = None if old_version is None else str(old_version)
        if old_version:
            self.common = len(commonprefix([self.version, self.old_version]))
            self.length = len(self.version) + len(self.old_version) + 1 - self.common
        else:
            self.common = self.length = len(self.version)

    def __str__(self):
        """
        Example:
            >>> str(Version('2.3'))
            '2.3'
            >>> str(Version('2.3', '2.4'))
            '2.3‣2.4'
        """
        if self.old_version:
            return f'{self.version}‣{self.old_version}'
        else:
            return str(self.version)

    def split_version(self) -> Tuple[str, str, str]:
        """
        Translates the version string into a triple of common prefix, old part, new part.

        This does not split inside sequences of alphanumeric characters.

        Examples:
            >>> Version('1.11', old_version='1.10').split_version()
            ('1.', '10', '11')
            >>> Version('42.0').split_version()
            ('42.0', '', '')
        """
        if self.old_version:
            old_parts = re.split(r'([\W\D]+)', self.old_version)
            new_parts = re.split(r'([\W\D]+)', self.version)
            common_parts = commonprefix([old_parts, new_parts])
            return tuple(''.join(s) for s in [common_parts, old_parts[len(common_parts):], new_parts[len(common_parts):]])
        else:
            return self.version, '', ''

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        if self.old_version:
            common,  old, new = self.split_version()
            yield f'{common}[red strike]{old}[/red strike]‣[green underline]{new}[/green underline]'
        else:
            yield str(self.version)

    def __len__(self):
        """
        Returns the visual length of the rich-rendered version string.

        Example:
            >>> len(Version('2.3'))
            3
            >>> len(Version('2.3', '2.4'))      # 2.3>4
            5
        """
        return self.length

    def __rich_measure__(self, console, options):
        return Measurement(self.length, self.length)

    def __repr__(self):
        result = f'{self.__class__.__name__}({self.version!r}'
        if self.old_version:
            result += f', old_version={self.old_version!r})'
        else:
            result += ')'
        return result


class PackageDescriptor:
    auto_installed: bool = False

    def __init__(self, match, operation=None):
        self.name = match.group(1)
        self.operation = operation
        if match.group(3):
            old_version = match.group(2)
            version = match.group(3)
        else:
            old_version = None
            version = match.group(2)

        if version == 'automatic':
            old_version, version = None, old_version
            self.auto_installed = True

        self.version = Version(version, old_version)

        try:
            self.pkg = _cache[self.name]
            self.shortname = self.pkg.shortname
            self.auto_installed |= self.pkg.is_auto_installed

            if version in self.pkg.versions:
                self.ver = self.pkg.versions[version]
            elif self.pkg.installed:
                self.ver = self.pkg.installed
            elif self.pkg.versions:
                self.ver = next(iter(self.pkg.versions))

            self.summary = self.ver.summary
        except KeyError:
            self.shortname = self.name
            self.summary = '[package not found]'

    @property
    def display_version(self):
        if hasattr(self, 'old_version'):
            return f'{self.old_version}‣{self.version}'
        else:
            return self.version


def read_log(file='/var/log/apt/history.log'):
    return [LogRecord(text) for text in Path(file).read_text().split('\n\n')]


def show_record(rec: LogRecord, show_auto=False, sort=False, prefix=''):
    table = rich.table.Table(title=f'{prefix}{rec}', box=rich.box.SIMPLE)
    table.add_column('')
    table.add_column('Package')
    table.add_column('Version')
    table.add_column('Summary')

    items = sorted(rec, key=lambda item: item.shortname) if sort else rec

    for item in items:
        if not item.auto_installed or show_auto:
            table.add_row(LogRecord.operations[item.operation], item.shortname, item.display_version, item.summary,
                          style='dim' if item.auto_installed else None)
    console.print(table)


def show_records(log: List[LogRecord], specs: List[str], **kwargs) -> int:
    indexes = get_indexes(specs, len(log))
    for index in indexes:
        show_record(log[index], prefix=f'{index}: ', **kwargs)
    return index


def parse_slice(source: str) -> Union[int, slice]:
    """
    Parses 1-dimensional slice strings.

    Examples:
        >>> parse_slice('42')
        42
        >>> parse_slice('5:')
        slice(5, None, None)
        >>> parse_slice('::-1')
        slice(None, None, -1)
    """
    parts = source.split(':')
    if len(parts) == 1:
        return int(parts[0])
    else:
        args = [int(part) if part else None for part in parts]
        return slice(*args)


def get_indexes(specs: Iterable[Union[str, int, slice]], length: int) -> list[int]:
    """
    Converts a list of slice specs into a sorted list of indexes into a list of specified length.

    Args:
        specs: A list of slice specs. A slice spec may either be a string that `parse_slice` understands
               or an int or a slice object – basically something you can write into a list’s subscription `[]`
               either in string form or directly.
        length: The length of the list for which to generate indexes.

    Returns: List of unique, non-negative integers < length.

    Example:
        >>> get_indexes([5, '1', '-3:'], 10)
        [1, 5, 7, 8, 9]

    """
    slices = [parse_slice(spec) if isinstance(spec, str) else spec for spec in specs]
    source = list(range(length))
    result_set = set()
    for slice_ in slices:
        idx = source[slice_]
        if isinstance(idx, int):
            result_set.add(idx)
        else:
            result_set.update(idx)
    return sorted(result_set)


def getargparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('records', nargs='*', default=['-1'])
    p.add_argument('-i', '--interactive', help='Interactive mode', action='store_true', default=False)
    p.add_argument('-a', '--auto', help='Include automatically installed items', action='store_true', default=False)
    p.add_argument('-u', '--unsorted', help='Show packages in the same order as in the log file for each operation',
                   action='store_true', default=False)
    p.add_argument('-l', '--list', help='List records (i.e. apt calls) instead of the packages of a single apt call',
                   action='store_true', default=False)
    return p


def show_log(records):
    for index, record in enumerate(records):
        console.print(f'{index:2d}. {record}')


def _option(name: str, flag: bool = False, shortcut_pos: int = 0):
    t = Text(name)
    if flag:
        t.stylize('bold')
    if shortcut_pos is not None:
        t.stylize('underline', shortcut_pos, shortcut_pos + 1)
    return t


def interactive_mode(records, auto_installed=False, sort=True):
    show_log(records)
    default = '-1'
    quit = False
    browse_reverse = False
    while not quit:
        show_list = False
        raw_input = console.input(Text('Record(s) | ')
                                  + _option('auto', auto_installed) + ' | '
                                  + _option('sort', sort) + ' | '
                                  + _option('quit')
                                  + Text(f'[{default}] ❯ ', style='green'))
        answers = raw_input.lower().split() if raw_input else [default]
        specs = []
        for answer in answers:
            if answer == 'a':
                auto_installed = not auto_installed
            elif answer == 's':
                sort = not sort
            elif answer == 'q':
                quit = True
            elif answer == 'l':
                show_list = True
            elif re.match('(-?\d+)?(:(-?\d+)?)*', answer):
                specs.append(answer)
            else:
                console.error(f'{answer} not understood')

        if specs == ['-1']:
            browse_reverse = True

        if not specs:
            specs = [default]

        with console.pager(styles=True):
            last_record = show_records(records, specs, show_auto=auto_installed, sort=sort)

            if browse_reverse and last_record > 0:
                default = str(last_record - 1)
            elif last_record < len(records) - 1:
                default = str(last_record + 1)
            else:
                default = 'q'

        if show_list:
            show_log(records)


def main():
    options = getargparser().parse_args()
    log = read_log()
    if options.interactive:
        interactive_mode(log, options.auto, not options.unsorted)
    elif options.list:
        show_log(log)
    else:
        show_records(log, options.records, show_auto=options.auto, sort=not options.unsorted)


if __name__ == '__main__':
    main()

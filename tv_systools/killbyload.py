import pickle
from pathlib import Path
from time import sleep
from typing import Annotated, Iterable
import psutil
from cyclopts import App, Parameter
from cyclopts.validators import Number
import xdg.BaseDirectory
from base64 import urlsafe_b64encode

app = App()


class ProcessCache:
    patterns: frozenset[str]
    processes: dict[tuple[int, float], int]  # (pid, created) -> count

    def __init__(self, patterns: Iterable[str]) -> None:
        self.patterns = frozenset(patterns)
        self.processes = {}

    def update(self, processes: list[psutil.Process], threshold: int = 1):
        current_procs = {(proc.pid, proc.create_time()): proc for proc in processes}
        for missing in set(self.processes) - set(current_procs):
            del self.processes[missing]
        for proc in current_procs:
            if proc in self.processes:
                self.processes[proc] += 1
            else:
                self.processes[proc] = 1
        return [
            current_procs[proc]
            for proc, count in self.processes.items()
            if count >= threshold
        ]

    @classmethod
    def _cache_file(cls, patterns: Iterable[str]) -> Path:
        return Path(
            xdg.BaseDirectory.save_cache_path(app.name[0]),
            urlsafe_b64encode(repr(sorted(patterns)).encode()).decode("ascii"),
        )

    @classmethod
    def load(cls, patterns: Iterable[str]):
        cache = cls._cache_file(patterns)
        if cache.exists():
            with cache.open("rb") as f:
                return pickle.load(f)
        else:
            return cls(patterns)

    def save(self):
        if self.processes:
            with self._cache_file(self.patterns).open("wb") as f:
                pickle.dump(self, f)
        else:
            self._cache_file(self.patterns).unlink(missing_ok=False)


def matching_processes(patterns: Iterable[str]) -> list[psutil.Process]:
    matching: list[psutil.Process] = []
    for process in psutil.process_iter():
        matches = any(pattern in process.name() for pattern in patterns)
        if matches:
            matching.append(process)
            process.cpu_percent()
    return matching


@app.default
def kill_by_load(
    patterns: set[str],
    /,
    *,
    sample_seconds: Annotated[
        float, Parameter(alias="-s", validator=Number(gt=0.0))
    ] = 2.5,
    threshold: Annotated[
        float, Parameter(alias="-t", validator=Number(gte=0, lte=100))
    ] = 70,
    count: Annotated[int, Parameter(alias="-c", validator=Number(gte=1))] = 1,
    kill: Annotated[bool, Parameter(alias="-k", negative=None)] = False,
    simulate: Annotated[
        bool, Parameter(alias=["-n", "--dry-run"], negative=None)
    ] = False,
):
    """
    Terminate or kill matching processes that exhibit a high CPU usage.

    Args:
        patterns: Only processes whose name contains at least one of the given patterns as substring are considered.
        sample_seconds: (minimum) number of seconds over which to calculate the cpu usage.
        threshold: if the process' CPU usage is >= threshold percent, it is considered having a high CPU usage.
        count: if this is > 1, the process must have a high cpu usage in this many subsequent calls of this command before it is killed.
        kill: if true, send a SIGKILL to processes not terminating after SIGTERM.
        simulate: Don't actually kill processes, just print what is done.
    """
    matching = matching_processes(patterns)

    if matching:
        print(
            f"Sampling {len(matching)} matching processes ({' '.join(p.name() for p in matching)}) for {sample_seconds} seconds …"
        )
        sleep(sample_seconds)
        high_load = [
            process for process in matching if process.cpu_percent() >= threshold
        ]
        if count > 1:
            cache = ProcessCache.load(patterns)
            to_terminate = cache.update(high_load)
            cache.save()
        else:
            to_terminate = high_load

        for process in to_terminate:
            process.terminate() if not simulate else print(
                "Simulating: Terminating", process
            )
        if kill:
            sleep(1)
            for process in to_terminate:
                if process.is_running():
                    process.kill() if not simulate else print(
                        "Simulating: Killing", process
                    )

from ast import Param
from pathlib import Path
from time import sleep
from typing import Annotated
import psutil
from cyclopts import App, Parameter
from cyclopts.validators import Number
import xdg.BaseDirectory

app = App()


@app.default
def kill_by_load(
    patterns: list[str],
    /,
    *,
    sample_seconds: Annotated[
        float, Parameter(alias="-s", validator=Number(gt=0.0))
    ] = 2.5,
    threshold: Annotated[
        float, Parameter(alias="-t", validator=Number(gte=0, lte=100))
    ] = 70,
    # count: Annotated[int, Parameter(alias="-c", validator=Number(gte=1))] = 1,
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
    matching: list[psutil.Process] = []
    for process in psutil.process_iter():
        matches = any(pattern in process.name() for pattern in patterns)
        if matches:
            matching.append(process)
            process.cpu_percent()

    if matching:
        print(
            f"Sampling {len(matching)} matching processes ({' '.join(p.name() for p in matching)}) for {sample_seconds} seconds …"
        )
        sleep(sample_seconds)
        high_load = [
            process for process in matching if process.cpu_percent() >= threshold
        ]
        for process in high_load:
            process.terminate() if not simulate else print(
                "Simulating: Terminating", process
            )
        if kill:
            sleep(1)
            for process in high_load:
                if process.is_running():
                    process.kill() if not simulate else print(
                        "Simulating: Killing", process
                    )

from sys import stdin, stdout
from cyclopts import App

app = App()


@app.default
def uniqall():
    """
    Print only those lines that have not been seen before.

    Unlike uniq(1), repeated lines do not have to be in a continuous sequence,
    i.e., you don't need to preprocess using sort to avoid duplicate outputs.

    Also unlike uniq(1), this tool has almost no features or options.
    """
    seen = set()
    for line in stdin:
        if line not in seen:
            seen.add(line)
            stdout.write(line)

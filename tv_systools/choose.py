#!/usr/bin/env python3
from random import sample
import sys


def usage(err="", retval=1):
    if err:
        print(err, file=sys.stderr)
    print(
        f"""Usage: {sys.argv[0]} k

    Randomly samples k lines from standard input.

    k may be:

         an integer, k ≥ 1:                   absolute number of samples
         a float, 0 < k ≤ 1 or 0% < k < 100%: fraction of input lines to choose
    """,
        file=sys.stderr,
    )
    sys.exit(retval)


def main():
    if len(sys.argv) > 2:
        usage()

    if len(sys.argv) < 2:
        arg = "100%"
    else:
        arg = sys.argv[1]
    source = sys.stdin.readlines()
    n = len(source)
    k = n
    try:
        if arg.endswith("%"):
            fraction = float(arg[:-1]) / 100
            if fraction > 1:
                usage(f"Fraction {fraction:4.4%} > 100% does not make sense.", 2)
        else:
            try:
                k = int(arg)
            except ValueError:
                fraction = float(arg)
                k = round(fraction * n)

        if k < 0:
            usage(f"Negative number of samples ({k}) does not make sense.", 3)
        sys.stdout.writelines(sample(source, k))
    except ValueError as e:
        usage(str(e), 4)


if __name__ == "__main__":
    main()

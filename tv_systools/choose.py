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

         k ≥ 1:                      absolute number of samples
         0 < k < 1 or 0% < k < 100%: fraction of input lines to choose.
    """,
        file=sys.stderr,
    )
    sys.exit(retval)


def main():
    if len(sys.argv) != 2:
        usage()

    arg = sys.argv[1]
    if arg.endswith("%"):
        fraction = float(arg[:-1]) / 100
        if fraction > 1:
            usage(f"Fraction {fraction:4.4%} > 100% does not make sense.", 2)
    else:
        fraction = float(arg)

    source = sys.stdin.readlines()
    n = len(source)
    if fraction < 1:
        k = round(fraction * n)
    else:
        k = int(fraction)
    if k < 0:
        usage(f"Negative number of samples ({k}) does not make sense.", 3)
    sys.stdout.writelines(sample(source, k))


if __name__ == "__main__":
    main()

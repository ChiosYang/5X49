"""Linux exec wrapper: the decoder dies with its owner, including SIGKILL.

Run prctl in a fresh interpreter, avoiding unsafe preexec_fn in a threaded API.
The Windows owner uses a kill-on-close Job Object instead.
"""
import ctypes
import os
import signal
import sys


def main():
    if not sys.platform.startswith("linux"):
        print("health process lifecycle unsupported", file=sys.stderr)
        return 78
    owner = int(sys.argv[1])
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        print("health process lifecycle unsupported", file=sys.stderr)
        return 78
    if os.getppid() != owner:
        return 78
    os.execv(sys.argv[2], sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())

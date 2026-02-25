#!/usr/bin/env python3
"""
Sperax RM-01 Walking Pad Controller
Interactive terminal control.

This is a convenience wrapper. The real implementation lives in
sperax_rm01.cli, which is also installed as the ``sperax-walk`` command.
"""

from sperax_rm01.cli import main

if __name__ == "__main__":
    main()

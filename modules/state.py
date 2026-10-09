"""Глобальные флаги, изменяемые в рантайме."""
import os
import sys

DEBUG_MODE = ("--debug" in sys.argv) or (os.environ.get("WI_DEBUG") == "1")
QUIET_MODE = False

# Счётчики для slow-mode в download.py
slow_mirror_count = 0
slow_mode_active = False

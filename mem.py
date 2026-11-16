#!/usr/bin/env python3
"""Compat shim — implementation lives in src/memengine (pip install -e /root/memengine)."""
import os
import sys

sys.path.insert(0, "/root/memengine/src")
from memengine.cli import main

main()

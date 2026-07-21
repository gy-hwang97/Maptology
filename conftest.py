import os
import sys

# Put the repo root on sys.path so tests can import the `api` and `build`
# packages regardless of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

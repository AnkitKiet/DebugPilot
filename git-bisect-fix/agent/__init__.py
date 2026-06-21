# agent package
import sys
import os
import bisect

# To avoid shadowing and import conflicts with Python's standard library 'bisect' module,
# we dynamically patch the standard library module to behave like a package when needed,
# pointing to our local 'bisect' package directory.
if not hasattr(bisect, "__path__"):
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _parent = _current_dir
    for _ in range(3):
        _candidate = os.path.join(_parent, "bisect")
        if os.path.isdir(_candidate):
            bisect.__path__ = [_candidate]
            break
        _parent = os.path.dirname(_parent)

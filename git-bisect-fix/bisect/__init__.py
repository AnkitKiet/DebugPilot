# bisect package
import sys
import os

# To avoid shadowing the standard library's bisect module (which is imported
# by random, urllib, etc. and causing infinite recursion or missing attributes),
# we dynamically load the standard library's bisect module.
_orig_path = list(sys.path)
_orig_bisect = sys.modules.pop('bisect', None)
try:
    sys.path = [p for p in sys.path if p and p != os.getcwd() and "git-bisect-fix" not in p]
    import bisect as _stdlib_bisect
finally:
    sys.path = _orig_path
    if _orig_bisect is not None:
        sys.modules['bisect'] = _orig_bisect

# Expose all standard library bisect symbols
globals().update({k: v for k, v in _stdlib_bisect.__dict__.items() if not k.startswith('__')})

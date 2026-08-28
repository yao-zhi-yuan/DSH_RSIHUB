from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import safe_relative_path
assert safe_relative_path(r'a\b\c.txt') == 'a/b/c.txt'
for value in ('', '/etc/passwd', '../x', 'a/../../x', r'C:\temp\x'):
    try: safe_relative_path(value)
    except ValueError: pass
    else: raise AssertionError(value)

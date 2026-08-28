from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import invoice_total
assert invoice_total([{'unit_cents': 1, 'quantity': 5}], 1000) == {'subtotal_cents': 5, 'tax_cents': 1, 'total_cents': 6}
assert invoice_total([], 0) == {'subtotal_cents': 0, 'tax_cents': 0, 'total_cents': 0}
for items, rate in [([{'unit_cents': -1, 'quantity': 1}], 0), ([{'unit_cents': 1, 'quantity': -1}], 0), ([], -1)]:
    try: invoice_total(items, rate)
    except ValueError: pass
    else: raise AssertionError((items, rate))

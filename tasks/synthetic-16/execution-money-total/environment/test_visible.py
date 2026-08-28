import unittest
from module import invoice_total

class Visible(unittest.TestCase):
    def test_basic(self): self.assertEqual(invoice_total([{'unit_cents': 100, 'quantity': 2}], 500)['total_cents'], 210)

if __name__ == '__main__': unittest.main()

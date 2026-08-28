import unittest
from module import canonical_key

class Visible(unittest.TestCase):
    def test_stable(self): self.assertEqual(canonical_key({'b': 2, 'a': 1}), canonical_key({'a': 1, 'b': 2}))

if __name__ == '__main__': unittest.main()

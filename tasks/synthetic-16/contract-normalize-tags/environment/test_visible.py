import unittest
from module import normalize_tags

class Visible(unittest.TestCase):
    def test_basic(self): self.assertEqual(normalize_tags([' A ', 'b']), ['a', 'b'])

if __name__ == '__main__': unittest.main()

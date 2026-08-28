import unittest
from module import parse_size

class Visible(unittest.TestCase):
    def test_kb(self): self.assertEqual(parse_size('2KB'), 2048)

if __name__ == '__main__': unittest.main()

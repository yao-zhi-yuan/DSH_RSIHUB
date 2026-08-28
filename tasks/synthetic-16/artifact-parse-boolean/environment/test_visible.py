import unittest
from module import parse_bool

class Visible(unittest.TestCase):
    def test_words(self): self.assertTrue(parse_bool(' yes ')); self.assertFalse(parse_bool('NO'))

if __name__ == '__main__': unittest.main()

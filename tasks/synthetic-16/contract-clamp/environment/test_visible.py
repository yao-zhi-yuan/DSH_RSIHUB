import unittest
from module import clamp

class Visible(unittest.TestCase):
    def test_inside(self): self.assertEqual(clamp(5, 0, 10), 5)
    def test_low(self): self.assertEqual(clamp(-1, 0, 10), 0)

if __name__ == '__main__': unittest.main()

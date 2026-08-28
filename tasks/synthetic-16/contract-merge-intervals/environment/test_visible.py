import unittest
from module import merge_intervals

class Visible(unittest.TestCase):
    def test_overlap(self): self.assertEqual(merge_intervals([(1, 3), (2, 4)]), [(1, 4)])

if __name__ == '__main__': unittest.main()

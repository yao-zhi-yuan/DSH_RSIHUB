import unittest
from module import retry_delays

class Visible(unittest.TestCase):
    def test_three(self): self.assertEqual(retry_delays(3), [1.0, 2.0, 4.0])

if __name__ == '__main__': unittest.main()

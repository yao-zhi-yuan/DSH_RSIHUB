import unittest
from module import next_action

class Visible(unittest.TestCase):
    def test_verified(self): self.assertEqual(next_action(100, True, True), 'submit')
    def test_verify(self): self.assertEqual(next_action(100, False, True), 'verify')

if __name__ == '__main__': unittest.main()

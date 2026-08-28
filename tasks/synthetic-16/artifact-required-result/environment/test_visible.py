import subprocess
import unittest

class Visible(unittest.TestCase):
    def test_script_runs(self):
        completed = subprocess.run(['python3', 'build_result.py'], check=False)
        self.assertEqual(completed.returncode, 0)

if __name__ == '__main__': unittest.main()

import unittest
from smalldata_tools.azimuthalBinning import azimuthalBinning as ab

DEFAULT_NAME = 'azav'

class TestAzimuthatlBinning(unittest.TestCase):
    def test_name(self):
        ab = ab()
        self.assertEqual(ab.name, DEFAULT_NAME)

if __name__ == '__main__':
    unittest.main()

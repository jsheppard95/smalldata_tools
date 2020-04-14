import unittest
import smalldata_tools.utilities as util
from smalldata_tools.azimuthalBinning import azimuthalBinning as ab

# Constants

# Default values for keyword args
DFLT_NAME = 'azav'
DFLT_MASK = None
DFLT_GAIN_IMG = None
DFLT_DARK_IMG = None
DFLT_DEBUG = False
DFLT_ADU_PER = 1.0
DFLT_DIS_SAM = 100e-3
DFLT_EBEAM = 9.5
DFLT_LAM = util.E2lam(DFLT_EBEAM) * 1e10
DFLT_PHI_BINS = 1
DFLT_PPLANE = 0
DFLT_TX = 0.
DFLT_TY = 0.
DFLT_Q_BIN = 5e-3
DFLT_THRESH_RMS = None
DFLT_THRESH_ADU = None
DFLT_THRESH_ADU_H = None
DFLT_X = None
DFLT_Y = None
DFLT_XCEN = None
DFLT_YCEN = None

class TestAzimuthatlBinning(unittest.TestCase):
    """Test AzimuthalBinning class"""
    def test_default_props(self):
        azb = ab()
        self.assertEqual(azb.name, DFLT_NAME)
        self.assertEqual(azb.mask, DFLT_MASK)
        self.assertEqual(azb.gainImg, DFLT_GAIN_IMG)
        self.assertEqual(azb.darkImg, DFLT_DARK_IMG)
        self.assertEqual(azb.debug, DFLT_DEBUG)
        self.assertEqual(azb.ADU_per_Photon, DFLT_ADU_PER)
        self.assertEqual(azb.dis_to_sam, DFLT_DIS_SAM)
        self.assertEqual(azb.eBeam, DFLT_EBEAM)
        self.assertEqual(azb.lam, DFLT_LAM)
        self.assertEqual(azb.phiBins, DFLT_PHI_BINS)
        self.assertEqual(azb.Pplane, DFLT_PPLANE)
        self.assertEqual(azb.tx, DFLT_TX)
        self.assertEqual(azb.ty, DFLT_TY)
        self.assertEqual(azb.qbin, DFLT_Q_BIN)
        self.assertEqual(azb.thresRMS, DFLT_THRESH_RMS)
        self.assertEqual(azb.thresADU, DFLT_THRESH_ADU)
        self.assertEqual(azb.thresADUhigh, DFLT_THRESH_ADU_H)
        self.assertEqual(azb.x, DFLT_X)
        self.assertEqual(azb.y, DFLT_Y)
        self.assertEqual(azb.xcen, DFLT_XCEN)
        self.assertEqual(azb.ycen, DFLT_YCEN)

if __name__ == '__main__':
    unittest.main()

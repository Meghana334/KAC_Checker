
import cv2
import numpy as np

import unittest
from unittest.mock import MagicMock
import sys

# Mock pytesseract before importing visual_analyser
sys.modules["pytesseract"] = MagicMock()

from visual_analyser import ImageAudit, ImageAuditConfig
import os

class TestLinearRGBConversion(unittest.TestCase):
    def setUp(self):
        # Create a dummy image
        self.img_path = "test_image.png"
        # Create a simple 2x2 image with known values
        # Pixel 1: (0, 0, 0) -> Linear (0, 0, 0)
        # Pixel 2: (255, 255, 255) -> Linear (1, 1, 1)
        # Pixel 3: (128, 128, 128) -> Linear approx 0.21586
        # Pixel 4: (10, 10, 10) (Low value for linear segment check) -> 10/255 = 0.0392 -> < 0.04045 so / 12.92
        
        # BGR format for cv2
        img = np.array([
            [[0, 0, 0], [255, 255, 255]],
            [[128, 128, 128], [10, 10, 10]]
        ], dtype=np.uint8)
        
        cv2.imwrite(self.img_path, img)
        self.config = ImageAuditConfig(image_path=self.img_path)

    def tearDown(self):
        if os.path.exists(self.img_path):
            os.remove(self.img_path)

    def test_conversion_logic(self):
        audit = ImageAudit(self.config)
        result = audit.convert_to_linear_rgb()
        
        linear_rgb = audit.linear_rgb
        
        # Check metadata
        self.assertIn("linear_rgb_metadata", result)
        metadata = result["linear_rgb_metadata"]
        self.assertEqual(metadata["color_space"], "Linear RGB")
        self.assertTrue(metadata["gamma_removed"])
        
        # Check values
        # (0,0,0) -> 0.0
        np.testing.assert_allclose(linear_rgb[0, 0], [0.0, 0.0, 0.0], atol=1e-5)
        
        # (255,255,255) -> 1.0
        np.testing.assert_allclose(linear_rgb[0, 1], [1.0, 1.0, 1.0], atol=1e-5)
        
        # (128,128,128) -> ((128/255 + 0.055)/1.055)^2.4
        # 128/255 = 0.50196
        # (0.50196 + 0.055) / 1.055 = 0.52792
        # 0.52792^2.4 = 0.21586
        expected_128 = ((128/255 + 0.055) / 1.055) ** 2.4
        np.testing.assert_allclose(linear_rgb[1, 0], [expected_128]*3, atol=1e-4)
        
        # (10,10,10) -> 10/255 / 12.92
        # 10/255 = 0.039215
        # 0.039215 / 12.92 = 0.003035
        expected_10 = (10/255) / 12.92
        np.testing.assert_allclose(linear_rgb[1, 1], [expected_10]*3, atol=1e-5)
        
        print("\nTest passed! Sample values verified.")

if __name__ == "__main__":
    unittest.main()

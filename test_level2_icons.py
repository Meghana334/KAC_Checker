import unittest
import cv2
import numpy as np
import os
import json
from visual_analyser import ImageAudit, ImageAuditConfig

class TestLevel2Icons(unittest.TestCase):
    def setUp(self):
        self.img_path = "test_icon_alpha.png"
        # Create a 4-channel image (BGRA)
        # Transparent Background
        self.img = np.zeros((100, 100, 4), dtype=np.uint8)
        
        # Draw a "Stroke" or Icon Shape (Blue Circle)
        # Blue: (255, 0, 0)
        # 3:1 Contrast against White (White L=1.0)
        # Blue L = 0.0722. Ratio = 1.05 / 0.12 ~= 8.75 (Pass)
        
        # Test Case: Low Contrast Icon
        # Light Gray Icon on Transparent (White effective BG)
        # Gray: (200, 200, 200) -> L ~= 0.59
        # Ratio = 1.05 / 0.64 ~= 1.64 (Fail)
        
        cv2.circle(self.img, (50, 50), 30, (200, 200, 200, 255), -1)
        
        cv2.imwrite(self.img_path, self.img)
        
        # Asset type "icon" triggers the new logic
        self.config = ImageAuditConfig(image_path=self.img_path, asset_type="icon")

    def tearDown(self):
        if os.path.exists(self.img_path):
            os.remove(self.img_path)
        if os.path.exists("test_icon_alpha_analysis.png"):
            os.remove("test_icon_alpha_analysis.png")

    def test_icon_contrast_failure(self):
        audit = ImageAudit(self.config)
        result = audit.analyze()
        
        print("\n=== Level 2 Output Dump ===")
        print(json.dumps(result, indent=2))
        
        # 1. Method Check
        self.assertIn("method", result)
        self.assertIn("Edge Detection", result["method"])
        
        # 2. Output Check
        self.assertEqual(result["severity"], "critical")
        self.assertIn("Contrast Failure", result["issue"])
        self.assertEqual(result["required_ratio"], "3.0:1")
        
        # 3. Suggestions
        self.assertTrue(len(result["fix_suggestions"]) > 0)

if __name__ == "__main__":
    unittest.main()

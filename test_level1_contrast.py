import unittest
import cv2
import numpy as np
import os
import json
from visual_analyser import ImageAudit, ImageAuditConfig

class TestLevel1Contrast(unittest.TestCase):
    def setUp(self):
        self.img_path = "test_low_contrast.png"
        # Create an image with White BG and specific Gray FG Text-like block
        # White: (255, 255, 255)
        # Low Contrast Gray: (180, 180, 180) 
        # Contrast check:
        # L_white = 1.0
        # L_gray (180) ~= ((180/255+0.055)/1.055)^2.4 ~= 0.46
        # Ratio = 1.05 / 0.51 ~= 2.05 (Fail < 3:1)
        
        self.img = np.full((100, 100, 3), 255, dtype=np.uint8) # White BG
        
        # Add a "text" rectangle in center
        # CV2 uses BGR
        cv2.rectangle(self.img, (30, 30), (70, 70), (180, 180, 180), -1) 
        
        cv2.imwrite(self.img_path, self.img)
        self.config = ImageAuditConfig(image_path=self.img_path, asset_type="button") # Strict threshold 3:1

    def tearDown(self):
        if os.path.exists(self.img_path):
            os.remove(self.img_path)
        # Cleanup evidence images
        if os.path.exists("test_low_contrast_analysis.png"):
            os.remove("test_low_contrast_analysis.png")

    def test_contrast_failure_output(self):
        audit = ImageAudit(self.config)
        result = audit.analyze()
        
        print("\n=== Level 1 Output Dump ===")
        print(json.dumps(result, indent=2))
        
        # 1. Structure Check
        self.assertIn("element", result)
        self.assertIn("wcag", result)
        self.assertIn("location", result)
        self.assertIn("fix_suggestions", result)
        
        # 2. Value Check
        self.assertEqual(result["severity"], "critical")
        self.assertTrue(result["issue"].startswith("Contrast Failure"))
        
        # 3. Location Check
        coords = result["location"]["coordinates"]
        self.assertTrue(len(coords) > 0)
        # Should detect the rectangle roughly around 30,30,70,70
        rect = coords[0] # [[x,y], [x2,y2]]
        x, y = rect[0]
        x2, y2 = rect[1]
        
        # Flexible assertions for contour bounding box
        self.assertTrue(20 <= x <= 40)
        self.assertTrue(20 <= y <= 40)
        self.assertTrue(60 <= x2 <= 80)
        self.assertTrue(60 <= y2 <= 80)
        
        # 4. Suggestions Check
        suggestions = result["fix_suggestions"]
        self.assertTrue(len(suggestions) > 0)
        # Should suggest darkening (since it's light on white)
        self.assertTrue(any("Darken" in s for s in suggestions))

if __name__ == "__main__":
    unittest.main()

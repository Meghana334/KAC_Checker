import unittest
import cv2
import numpy as np
import os
import json
from visual_analyser import ImageAudit, ImageAuditConfig

class TestLevel3Automation(unittest.TestCase):
    def setUp(self):
        self.img_path = "test_level3_complex.png"
        
        # Create a complex image (Gradient-ish or multi-color)
        # Background: Left half Red, Right half Blue
        self.img = np.zeros((100, 100, 3), dtype=np.uint8)
        self.img[:, :50] = [0, 0, 255] # Red BGR
        self.img[:, 50:] = [255, 0, 0] # Blue BGR
        
        # Text: White "TEST" in center (spanning both)
        # White on Red (Pass 4.5?: Red L~0.21, White L=1.0 -> 4.x?)
        # White on Blue (Pass: Blue L~0.07 -> >7)
        
        cv2.putText(self.img, "TEST", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.imwrite(self.img_path, self.img)
        
        self.config = ImageAuditConfig(image_path=self.img_path, asset_type="button")

    def tearDown(self):
        if os.path.exists(self.img_path):
            os.remove(self.img_path)
        if os.path.exists("test_level3_complex_analysis.png"):
            os.remove("test_level3_complex_analysis.png")

    def test_pipeline_structure(self):
        audit = ImageAudit(self.config)
        result = audit.analyze()
        
        print("\n=== Level 3 Output Dump ===")
        print(json.dumps(result, indent=2))
        
        # Check Final Report Structure Keys
        required_keys = [
            "asset_type", "file", "issue", "wcag", "current", "required",
            "text_detected", "location", "why_axe_missed", "fix_suggestions", "preview"
        ]
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")
            
        # Check Type Correctness
        self.assertIsInstance(result["current"], float)
        self.assertIsInstance(result["required"], float)
        self.assertIsInstance(result["fix_suggestions"], list)
        
        # Check Logic
        self.assertEqual(result["why_axe_missed"], "Checks CSS color but misses opacity/gradients/images")
        
        # Check K-Means (implicit) logic invocation
        # We can't easily check if K-Means was run from output unless we add debug info, 
        # but if it didn't crash, it's good.

if __name__ == "__main__":
    unittest.main()

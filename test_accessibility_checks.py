
import unittest
import numpy as np
import cv2
import os
from unittest.mock import MagicMock
import sys

# Mock
sys.modules["mistralai"] = MagicMock()

from visual_analyser import ImageAudit, ImageAuditConfig

class TestAccessibilityChecks(unittest.TestCase):
    def setUp(self):
        self.img_path = "test_contrast.png"
        self.rgba_path = "test_alpha.png"

    def tearDown(self):
        if os.path.exists(self.img_path):
            os.remove(self.img_path)
        if os.path.exists(self.rgba_path):
            os.remove(self.rgba_path)

    def create_opaque_image(self):
        # 100x100 Black Image with White Text-like pattern
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        # Draw thin lines (Text simulation)
        # Thickness 2 pixels, sufficiently smaller than block size (approx 5) to avoid hollowing
        cv2.line(img, (20, 50), (80, 50), (255, 255, 255), 2)
        cv2.line(img, (50, 20), (50, 80), (255, 255, 255), 2)
        cv2.imwrite(self.img_path, img)

    def create_transparent_image(self):
        # 100x100 Transparent Image
        # FG: 50% Opacity Black Text-like pattern
        
        img = np.zeros((100, 100, 4), dtype=np.uint8)
        # BG Transparent
        img[:] = [0, 0, 0, 0] 
        
        # Draw Lines: Black, 128 Alpha
        cv2.line(img, (20, 50), (80, 50), (0, 0, 0, 128), 2)
        cv2.line(img, (50, 20), (50, 80), (0, 0, 0, 128), 2)
        
        cv2.imwrite(self.rgba_path, img)

    def test_alpha_blending_and_contrast(self):
        self.create_transparent_image()
        config = ImageAuditConfig(image_path=self.rgba_path, asset_type="icon")
        audit = ImageAudit(config)
        
        # Audit logic normally blends in __init__
        # Verify blended pixels
        # Center pixel (FG) should be ~127 Gray
        center_px = audit.img[50, 50]
        # BGR
        self.assertTrue(120 <= center_px[0] <= 135, f"Expected ~127, got {center_px[0]}")
        
        # Run analysis
        report = audit.analyze()
        
        # Structure Check
        self.assertIn("audit", report)
        self.assertIn("wcag_sc", report["audit"])
        self.assertEqual(report["audit"]["threshold"], 3.0) # Icon type
        
        # Contrast: Gray(127) vs White(255) (Default BG) implies White BG was used for blending?
        # Wait, blending happens in __init__ against White. 
        # But `segment_and_analyze` splits FG (Gray) and BG (Transparent->White).
        # So we compare Gray(127) vs White(255).
        # L_Gray ~ 0.21. L_White = 1.0.
        # Contrast = 1.05 / 0.26 ~ 4.0.
        
        ratio = report["audit"]["contrast_ratio"]
        self.assertTrue(3.5 < ratio < 4.5, f"Expected ~4.0, got {ratio}")
        self.assertEqual(report["audit"]["status"], "PASS")

    def test_wcag_thresholds(self):
        self.create_opaque_image() # White on Black -> 21:1
        
        # Case 1: Text -> Threshold 4.5
        config = ImageAuditConfig(image_path=self.img_path, asset_type="general")
        audit = ImageAudit(config)
        report = audit.analyze()
        self.assertEqual(report["audit"]["threshold"], 4.5)
        self.assertEqual(report["audit"]["status"], "PASS")
        
        # Case 2: Icon -> Threshold 3.0
        config2 = ImageAuditConfig(image_path=self.img_path, asset_type="icon")
        audit2 = ImageAudit(config2)
        report2 = audit2.analyze()
        self.assertEqual(report2["audit"]["threshold"], 3.0)
        self.assertEqual(report2["audit"]["wcag_sc"], "1.4.11")

    def test_evidence_generation(self):
        self.create_opaque_image()
        config = ImageAuditConfig(image_path=self.img_path, asset_type="general")
        audit = ImageAudit(config)
        report = audit.analyze()
        
        # Check if evidence image key exists
        self.assertIn("evidence_image", report["audit"]["evidence"])
        evidence_path = report["audit"]["evidence"]["evidence_image"]
        
        # Check if file was created
        full_evidence_path = os.path.join(os.path.dirname(self.img_path), evidence_path)
        self.assertTrue(os.path.exists(full_evidence_path), "Evidence image should be created")
        
        # Cleanup
        if os.path.exists(full_evidence_path):
            os.remove(full_evidence_path)

if __name__ == "__main__":
    unittest.main()

import cv2
import numpy as np
import pytesseract
import os
import logging
from datetime import datetime
from pydantic import BaseModel, Field, validator


# ---------------------------
# Logging Configuration
# ---------------------------

LOG_FILE = "image_audit.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ],
)

logger = logging.getLogger("ImageAudit")


# ---------------------------
# Config Model (Pydantic)
# ---------------------------

class ImageAuditConfig(BaseModel):
    image_path: str = Field(..., description="Path to the input image")

    @validator("image_path")
    def validate_path(cls, v):
        if not os.path.exists(v):
            raise ValueError(f"Image path does not exist: {v}")
        return v


# ---------------------------
# Image Audit Class
# ---------------------------

class ImageAudit:
    def __init__(self, config: ImageAuditConfig):
        self.path = config.image_path
        self.img = cv2.imread(self.path)

        if self.img is None:
            raise ValueError("Failed to load image. Unsupported format or corrupt file.")

        logger.info(f"Loaded image: {self.path}")

    # ---- metric functions ---- #

    def compute_blur(self):
        gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        val = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        logger.info(f"Blur (Variance of Laplacian): {val}")
        return val

    def compute_brightness(self):
        gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        val = float(np.mean(gray))
        logger.info(f"Brightness: {val}")
        return val

    def compute_sharpness(self):
        gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1)
        val = float(np.mean(gx**2 + gy**2))
        logger.info(f"Sharpness (Tenengrad): {val}")
        return val

    def compute_colorfulness(self):
        (B, G, R) = cv2.split(self.img.astype("float"))
        rg = np.abs(R - G)
        yb = np.abs(0.5 * (R + G) - B)
        val = float(np.sqrt(np.mean(rg**2) + np.mean(yb**2)))
        logger.info(f"Colorfulness: {val}")
        return val

    def compute_entropy(self):
        gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        histogram = cv2.calcHist([gray], [0], None, [256], [0, 256])
        histogram = histogram / np.sum(histogram)
        val = float(-np.sum([p * np.log2(p) for p in histogram if p != 0]))
        logger.info(f"Entropy: {val}")
        return val

    def compute_ocr(self):
        # gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        # text = pytesseract.image_to_string(gray)
        # logger.info(f"OCR Extracted Text: {text.strip() if text.strip() else '[None]'}")
        return "text ocr  is turned off"

    def compute_text_contrast(self, text):
        gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)

        if not text:
            logger.info("No OCR text found. Skipping text contrast.")
            return None

        mean_intensity = float(np.mean(gray))
        text_pixels = gray[gray < mean_intensity]

        if len(text_pixels) == 0:
            return None

        text_intensity = float(np.mean(text_pixels))
        contrast = abs(text_intensity - mean_intensity) / (mean_intensity + 1e-6)

        logger.info(f"Text Contrast Ratio (simple local estimate): {contrast}")
        return contrast

    # ---- main analysis wrapper ---- #

    def analyze(self):
        h, w = self.img.shape[:2]
        file_size = os.path.getsize(self.path)

        logger.info(f"Image Dimensions: {w}x{h}")
        logger.info(f"File Size: {file_size} bytes")

        # Extract metrics
        blur = self.compute_blur()
        brightness = self.compute_brightness()
        sharpness = self.compute_sharpness()
        colorfulness = self.compute_colorfulness()
        entropy = self.compute_entropy()
        text = self.compute_ocr()
        # text_contrast = self.compute_text_contrast(text)

        return {
            "path": self.path,
            "width": w,
            "height": h,
            "file_size_bytes": file_size,
            "blur": blur,
            "brightness": brightness,
            "sharpness": sharpness,
            "colorfulness": colorfulness,
            "entropy": entropy,
            "ocr_text": text,
            # "text_contrast": text_contrast,
        }
    # ---------------------------
    # Threshold Checker
    # ---------------------------
    def evaluate_thresholds(self, metrics: dict):
        """
        Evaluates all image quality metrics against recommended thresholds.
        Returns a dictionary containing warnings/suggestions.
        """

        warnings = []

        # ---- Threshold Definitions ---- #
        THRESHOLDS = {
            "blur": {
                "min": 200,   # too low = blurry
                "max": 1000,  # values above mean extremely sharp
                "desc": "Blur (Variance of Laplacian)"
            },
            "brightness": {
                "min": 40,    # too dark
                "max": 230,   # too bright
                "desc": "Brightness"
            },
            "sharpness": {
                "min": 2000,
                "max": 10000,
                "desc": "Sharpness (Tenengrad)"
            },
            "colorfulness": {
                "min": 10,    # too gray or desaturated
                "max": 80,    # too saturated
                "desc": "Colorfulness"
            },
            "entropy": {
                "min": 3,     # very low detail
                "max": 7.5,   # extremely complex image
                "desc": "Entropy"
            },
            "text_contrast": {
                "min": 3.0,   # WCAG minimum for large text
                "max": 21.0,
                "desc": "Text Contrast Ratio (WCAG)"
            },
        }

        # ---- Check each metric ---- #
        for key, th in THRESHOLDS.items():
            if key not in metrics or metrics[key] is None:
                continue

            val = metrics[key]

            if val < th["min"]:
                warnings.append(
                    f"{th['desc']} is too LOW ({val:.2f}). Recommended minimum is {th['min']}."
                )

            elif val > th["max"]:
                warnings.append(
                    f"{th['desc']} is too HIGH ({val:.2f}). Recommended maximum is {th['max']}."
                )

        # If no problems
        if not warnings:
            return {"status": "PASS", "warnings": []}

        return {"status": "FAIL", "warnings": warnings}





# ---------------------------
# MAIN EXECUTION (No CLI)
# ---------------------------

if __name__ == "__main__":
    # <<< CHANGE IMAGE HERE >>>
    IMAGE_PATH = "ad_banner_1.jpeg"

    config = ImageAuditConfig(image_path=IMAGE_PATH)
    audit = ImageAudit(config)

    result = audit.analyze()

    threshold_report = audit.evaluate_thresholds(result)

    print("\n=== IMAGE AUDIT REPORT ===")
    for k, v in result.items():
        print(f"{k}: {v}")

    print("\n=== THRESHOLD ANALYSIS ===")
    print("Status:", threshold_report["status"])
    if threshold_report["warnings"]:
        for w in threshold_report["warnings"]:
            print(" -", w)
    else:
        print("All values are within recommended ranges.")

import cv2
import numpy as np
import pytesseract
import os
import logging
import base64
import json
from datetime import datetime
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv
from mistralai import Mistral

# ---------------------------
# Load Environment Variables
# ---------------------------
load_dotenv()
API_KEY = os.getenv("MISTRAL_API_KEY")

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
        
        if not API_KEY:
            logger.warning("MISTRAL_API_KEY not found in environment variables. Mistral features will be disabled.")
            self.mistral_client = None
        else:
            self.mistral_client = Mistral(api_key=API_KEY)

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

    def encode_image(self):
        """Encode image to base64 for Mistral API."""
        with open(self.path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def analyze_with_mistral(self):
        """Use Mistral VLM to analyze text and accessibility."""
        if not self.mistral_client:
            return {"error": "Mistral API key not configured"}
            
        logger.info("Sending image to Mistral for analysis...")
        base64_image = self.encode_image()
        
        prompt = """
        Analyze this image for accessibility and content. Provide a JSON response with the following keys:
        
        1. "ocr_text": Transcribe all visible text in the image.
        2. "text_contrast": Evaluate the contrast between text and background. Is it sufficient? (Low/Medium/High/Sufficient/Insufficient).
        3. "non_text_contrast": Evaluate the contrast of essential visual elements (icons, borders, focus indicators) against adjacent colors. Is it at least 3:1? (Pass/Fail/Not Applicable).
        4. "font_size_readability": Assess font size and general readability.
        5. "focus_visibility": Are there clear visual indicators for focus states (if applicable)?
        6. "touch_target_size": Do interactive elements appear large enough for touch?
        7. "image_based_text": Is this an image of text that should be real text? (Yes/No).
        8. "visual_error_indicators": Are there any error states shown?
        9. "chart_legibility": If charts/graphs are present, are they legible and labeled?
        10. "alt_text_suggestion": Suggest a descriptive alt text for this image.
        11. "wcag_violations": List potential WCAG violations found.
        
        Return ONLY valid JSON.
        """

        try:
            chat_response = self.mistral_client.chat.complete(
                model="pixtral-12b-2409",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                        ]
                    }
                ],
                response_format={"type": "json_object"}
            )
            
            content = chat_response.choices[0].message.content
            logger.info("Mistral analysis complete.")
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"Mistral analysis failed: {e}")
            return {"error": str(e)}

    # ---- main analysis wrapper ---- #

    def analyze(self):
        h, w = self.img.shape[:2]
        file_size = os.path.getsize(self.path)

        logger.info(f"Image Dimensions: {w}x{h}")
        logger.info(f"File Size: {file_size} bytes")

        # Extract cv2 metrics
        blur = self.compute_blur()
        brightness = self.compute_brightness()
        sharpness = self.compute_sharpness()
        colorfulness = self.compute_colorfulness()
        entropy = self.compute_entropy()
        
        # Mistral Analysis
        mistral_results = self.analyze_with_mistral()

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
            "mistral_analysis": mistral_results
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
            }
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
                
        # ---- Check Mistral Findings ---- #
        mistral = metrics.get("mistral_analysis", {})
        if "error" in mistral:
            warnings.append(f"Mistral Analysis Failed: {mistral['error']}")
        else:
            if mistral.get("image_based_text") == "Yes":
                 warnings.append("Potential WCAG 1.4.5 Violation: Image of text detected.")
            
            contrast = mistral.get("text_contrast", "").lower()
            if "insufficient" in contrast or "low" in contrast:
                 warnings.append(f"Text Contrast Issue: {mistral.get('text_contrast')}")
                 
            non_text_contrast = mistral.get("non_text_contrast", "").lower()
            if "fail" in non_text_contrast:
                 warnings.append(f"Non-Text Contrast Issue (WCAG 1.4.11): Detected failure for visual elements.")

            wcag = mistral.get("wcag_violations", [])
            if wcag:
                warnings.append(f"WCAG Violations Detected: {wcag}")

        # If no problems
        if not warnings:
            return {"status": "PASS", "warnings": []}

        return {"status": "FAIL", "warnings": warnings}


# ---------------------------
# MAIN EXECUTION (CLI Support)
# ---------------------------

def process_directory(directory_path: str):
    """Process all images in a directory recursively and generate a report."""
    results = []
    
    print(f"Scanning directory: {directory_path}...")
    
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if os.path.splitext(file)[1].lower() in image_extensions:
                file_path = os.path.join(root, file)
                print(f"\nProcessing: {file_path}")
                
                try:
                    config = ImageAuditConfig(image_path=file_path)
                    audit = ImageAudit(config)
                    
                    analysis = audit.analyze()
                    threshold_report = audit.evaluate_thresholds(analysis)
                    
                    # Merge status into result
                    analysis["threshold_status"] = threshold_report["status"]
                    analysis["threshold_warnings"] = threshold_report["warnings"]
                    
                    results.append(analysis)
                    
                except Exception as e:
                    logger.error(f"Failed to process {file_path}: {e}")
                    results.append({
                        "path": file_path,
                        "error": str(e),
                        "status": "ERROR"
                    })

    # Save consolidated report
    report_path = os.path.join(directory_path, "audit_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"\n=== BATCH ANALYSIS COMPLETE ===")
    print(f"Processed {len(results)} images.")
    print(f"Report saved to: {report_path}")
    
    # Print summary
    pass_count = sum(1 for r in results if r.get("threshold_status") == "PASS")
    fail_count = sum(1 for r in results if r.get("threshold_status") == "FAIL")
    error_count = sum(1 for r in results if "error" in r)
    
    print(f"PASS: {pass_count}")
    print(f"FAIL: {fail_count}")
    print(f"ERRORS: {error_count}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Visual Analyzer & Accessibility Auditor")
    parser.add_argument("--path", type=str, help="Path to single image or directory", default="output")
    
    args = parser.parse_args()
    target_path = args.path
    
    if os.path.isdir(target_path):
        process_directory(target_path)
    elif os.path.isfile(target_path):
        # Single file mode (legacy behavior preserved but cleaned up)
        print(f"Analyzing single file: {target_path}")
        try:
            config = ImageAuditConfig(image_path=target_path)
            audit = ImageAudit(config)
            result = audit.analyze()
            threshold_report = audit.evaluate_thresholds(result)
            
            print("\n=== IMAGE AUDIT REPORT ===")
            print(json.dumps(result, indent=2))
            print("\n=== THRESHOLD ANALYSIS ===")
            print("Status:", threshold_report["status"])
            if threshold_report["warnings"]:
                for w in threshold_report["warnings"]:
                    print(" -", w)
            else:
                 print("All values are within recommended ranges.")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print(f"Error: Path not found: {target_path}")
        print("Usage: python visual_analyser.py --path <file_or_directory>")


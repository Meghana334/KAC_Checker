# KAC Checker

KAC Checker is a Python-based toolsuite designed for web content analysis. It consists of two main components: a web crawler that captures visual elements from websites, and a visual analyzer that audits images for various quality metrics.

## Features

- **Web Crawler (`web_crawler.py`)**
  - Crawls a specified URL using Playwright.
  - Captures screenshots of various visual elements:
    - Images (`img` tags)
    - SVGs
    - Icons (FontAwesome, Material Icons, etc.)
    - Background images
    - Buttons
  - Deduplicates elements to avoid redundant captures.
  - Generates a `manifest.json` report of captured elements.

- **Visual Analyzer (`visual_analyser.py`)**
  - Audits individual images for quality metrics:
    - **Blur**: Variance of Laplacian.
    - **Brightness**: Mean pixel intensity.
    - **Sharpness**: Tenengrad method.
    - **Colorfulness**: Metric based on color distribution.
    - **Entropy**: Measure of image detail.
    - **Text Contrast**: WCAG contrast ratio estimate.
  - Evaluates metrics against configurable thresholds to generate a "PASS/FAIL" report.

## Installation

This project uses [Poetry](https://python-poetry.org/) for dependency management.

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd KAC_Checker
   ```

2. **Install dependencies:**
   ```bash
   poetry install
   ```

3. **Install Playwright browsers:**
   ```bash
   poetry run playwright install chromium
   ```

## Usage

### Web Crawler

Run the crawler to capture elements from a website.

```bash
# Default usage (crawls https://www.kao.com/global/en/)
python web_crawler.py

# Specify custom URL and output directory
python web_crawler.py --url https://example.com --output my_output_dir
```

**Arguments:**
- `--url`: The URL to crawl (default: `https://www.kao.com/global/en/`).
- `--output`: Directory to save captured screenshots and manifest (default: `output`).

### Visual Analyzer

The visual analyzer currently runs on a single image file specified within the script.

1. **Open `visual_analyser.py`** and modify the `IMAGE_PATH` variable in the `__main__` block:
   ```python
   # inside visual_analyser.py
   if __name__ == "__main__":
       # <<< CHANGE IMAGE HERE >>>
       IMAGE_PATH = "path/to/your/image.jpg" 
   ```

2. **Run the analyzer:**
   ```bash
   python visual_analyser.py
   ```

It will print an audit report to the console and log details to `image_audit.log`.

## Dependencies

- **Python**: >=3.13
- **Drivers**: `playwright`
- **Image Processing**: `numpy`, `pillow`, `opencv-python`, `pytesseract`
- **Utilities**: `pydantic`, `rich`

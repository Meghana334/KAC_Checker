#!/usr/bin/env python3
"""
Playwright Web Crawler with Screenshot Capture
Crawls a website and captures screenshots of images and visual elements.
"""

import asyncio
import json
import os
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse, urljoin

from playwright.async_api import async_playwright, Page, ElementHandle


# ---------------------------
# Configuration
# ---------------------------

DEFAULT_OUTPUT_DIR = "output"
DEFAULT_URL = "https://www.kao.com/global/en/"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("web_crawler.log"),
        logging.StreamHandler()
    ],
)
logger = logging.getLogger("WebCrawler")


# ---------------------------
# Utility Functions
# ---------------------------

def sanitize_filename(name: str, max_length: int = 50) -> str:
    """Convert a string into a safe filename."""
    # Remove or replace invalid characters
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '_', name)
    name = name.strip('_').lower()
    return name[:max_length] if name else "unnamed"


def create_output_dirs(base_dir: str) -> Dict[str, Path]:
    """Create organized output directory structure."""
    base_path = Path(base_dir)
    
    dirs = {
        "base": base_path,
        "images": base_path / "images",
        "icons": base_path / "icons",
        "svg": base_path / "svg",
        "backgrounds": base_path / "backgrounds",
        "buttons": base_path / "buttons",
    }
    
    for dir_path in dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created output directories in: {base_path.absolute()}")
    return dirs


# ---------------------------
# Web Crawler Class
# ---------------------------

class WebCrawler:
    def __init__(self, url: str, output_dir: str = DEFAULT_OUTPUT_DIR):
        self.url = url
        self.output_dir = output_dir
        self.dirs = create_output_dirs(output_dir)
        self.manifest = []
        self.screenshot_count = 0
        # Track captured URLs to prevent duplicates
        self.captured_img_urls = set()
        self.captured_svg_signatures = set()
        self.captured_icon_classes = set()
        self.captured_bg_urls = set()
        self.captured_button_signatures = set()
        
    async def capture_element_screenshot(
        self,
        element: ElementHandle,
        element_type: str,
        index: int,
        metadata: Dict
    ) -> Optional[str]:
        """Capture screenshot of a single element."""
        try:
            # Scroll element into view
            try:
                await element.scroll_into_view_if_needed(timeout=2000)
                # Small wait for lazy loading / render
                await asyncio.sleep(0.5)
            except Exception:
                pass # Ignore scroll errors, try capturing anyway

            # Check if element is visible
            is_visible = await element.is_visible()
            if not is_visible:
                logger.debug(f"Skipping invisible {element_type} element {index}")
                return None
            
            # Get element dimensions
            box = await element.bounding_box()
            if not box or box['width'] < 10 or box['height'] < 10:
                logger.debug(f"Skipping too small {element_type} element {index}")
                return None
            
            # Generate filename
            name_part = sanitize_filename(metadata.get('alt', metadata.get('title', '')))
            if not name_part:
                name_part = f"element_{index}"
            
            filename = f"{element_type}_{index:03d}_{name_part}.png"
            
            # Determine output subdirectory
            if element_type == "svg":
                filepath = self.dirs["svg"] / filename
            elif element_type == "icon":
                filepath = self.dirs["icons"] / filename
            elif element_type == "background":
                filepath = self.dirs["backgrounds"] / filename
            elif element_type == "button":
                filepath = self.dirs["buttons"] / filename
            else:
                filepath = self.dirs["images"] / filename
            
            # Capture screenshot
            await element.screenshot(path=str(filepath))
            logger.info(f"Captured: {filename}")
            
            self.screenshot_count += 1
            
            return str(filepath.relative_to(self.dirs["base"]))
            
        except Exception as e:
            logger.warning(f"Failed to capture {element_type} {index}: {e}")
            return None

    async def capture_state_screenshot(
        self,
        element: ElementHandle,
        element_type: str,
        index: int,
        state: str,
        base_filename: str
    ) -> Optional[str]:
        """Capture screenshot of an element in a specific state (hover, focus)."""
        try:
            # Trigger state
            if state == "hover":
                await element.hover()
            elif state == "focus":
                await element.focus()
            
            # Brief wait for transition
            await asyncio.sleep(0.3)
            
            filename = f"{base_filename}_{state}.png"
            
            # Determine output subdirectory (same logic as main capture)
            if element_type == "button":
                filepath = self.dirs["buttons"] / filename
            else:
                 # Default to buttons dir or create specific if needed for other interactive elements
                 # For now, we only really do this for buttons/interactive
                filepath = self.dirs["buttons"] / filename

            await element.screenshot(path=str(filepath))
            logger.info(f"Captured {state} state: {filename}")
            self.screenshot_count += 1
            
            # Reset state (rough attempt)
            if state == "hover":
                # Hover somewhere else?
                pass 
            
            return str(filepath.relative_to(self.dirs["base"]))

        except Exception as e:
            logger.debug(f"Failed to capture {state} state for {element_type} {index}: {e}")
            return None

    async def capture_full_page(self, page: Page):
        """Capture a full page screenshot."""
        try:
            filename = "full_page.png"
            filepath = self.dirs["base"] / filename
            await page.screenshot(path=str(filepath), full_page=True)
            logger.info(f"Captured Full Page Screenshot: {filepath}")
            self.screenshot_count += 1
            
            # Add to manifest
            self.manifest.append({
                "type": "full_page",
                "index": 0,
                "screenshot": filename
            })
        except Exception as e:
            logger.error(f"Failed to capture full page screenshot: {e}")
    
    async def auto_scroll(self, page: Page):
        """Scrolls the page to trigger lazy loading."""
        logger.info("Auto-scrolling page to trigger lazy loading...")
        await page.evaluate("""
            async () => {
                await new Promise((resolve) => {
                    var totalHeight = 0;
                    var distance = 200;
                    var timer = setInterval(() => {
                        var scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if(totalHeight >= scrollHeight){
                            clearInterval(timer);
                            resolve();
                        }
                    }, 50);
                });
            }
        """)
        # Scroll back to top
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)
    
    async def extract_images(self, page: Page):
        """Extract and screenshot all image elements."""
        logger.info("Extracting <img> elements...")
        
        images = await page.query_selector_all("img")
        logger.info(f"Found {len(images)} image elements")
        
        captured = 0
        skipped = 0
        
        for i, img in enumerate(images):
            try:
                # Get image metadata
                src = await img.get_attribute("src") or ""
                
                # Skip if we've already captured this URL
                if src in self.captured_img_urls:
                    skipped += 1
                    logger.debug(f"Skipping duplicate image: {src[:80]}...")
                    continue
                
                alt = await img.get_attribute("alt") or ""
                title = await img.get_attribute("title") or ""
                width = await img.get_attribute("width") or ""
                height = await img.get_attribute("height") or ""
                
                metadata = {
                    "type": "img",
                    "index": captured,  # Use captured count for consistent indexing
                    "src": src,
                    "alt": alt,
                    "title": title,
                    "width": width,
                    "height": height,
                }
                
                screenshot_path = await self.capture_element_screenshot(
                    img, "img", captured, metadata
                )
                
                if screenshot_path:
                    metadata["screenshot"] = screenshot_path
                    self.manifest.append(metadata)
                    self.captured_img_urls.add(src)
                    captured += 1
                    
            except Exception as e:
                logger.error(f"Error processing image {i}: {e}")
        
        logger.info(f"Captured {captured} unique images, skipped {skipped} duplicates")
    
    async def extract_svg_elements(self, page: Page):
        """Extract and screenshot SVG elements."""
        logger.info("Extracting <svg> elements...")
        
        svgs = await page.query_selector_all("svg")
        logger.info(f"Found {len(svgs)} SVG elements")
        
        captured = 0
        skipped = 0
        
        for i, svg in enumerate(svgs):
            try:
                # Get SVG metadata
                aria_label = await svg.get_attribute("aria-label") or ""
                role = await svg.get_attribute("role") or ""
                class_name = await svg.get_attribute("class") or ""
                
                # Create signature for deduplication
                signature = f"{aria_label}|{role}|{class_name}"
                
                if signature in self.captured_svg_signatures:
                    skipped += 1
                    logger.debug(f"Skipping duplicate SVG: {class_name}")
                    continue
                
                metadata = {
                    "type": "svg",
                    "index": captured,
                    "aria_label": aria_label,
                    "role": role,
                    "class": class_name,
                }
                
                screenshot_path = await self.capture_element_screenshot(
                    svg, "svg", captured, metadata
                )
                
                if screenshot_path:
                    metadata["screenshot"] = screenshot_path
                    self.manifest.append(metadata)
                    self.captured_svg_signatures.add(signature)
                    captured += 1
                    
            except Exception as e:
                logger.error(f"Error processing SVG {i}: {e}")
        
        logger.info(f"Captured {captured} unique SVGs, skipped {skipped} duplicates")
    
    async def extract_icons(self, page: Page):
        """Extract and screenshot icon elements (common patterns)."""
        logger.info("Extracting icon elements...")
        
        # Common icon selectors
        icon_selectors = [
            'i[class*="icon"]',
            '[class*="icon-"]',
            '.fa, .fas, .far, .fab',  # FontAwesome
            '[class*="material-icons"]',  # Material Icons
        ]
        
        all_icons = []
        for selector in icon_selectors:
            try:
                icons = await page.query_selector_all(selector)
                all_icons.extend(icons)
            except Exception as e:
                logger.debug(f"Error with selector {selector}: {e}")
        
        logger.info(f"Found {len(all_icons)} icon elements")
        
        captured = 0
        skipped = 0
        
        for i, icon in enumerate(all_icons):
            try:
                # Get icon metadata
                class_name = await icon.get_attribute("class") or ""
                aria_label = await icon.get_attribute("aria-label") or ""
                title = await icon.get_attribute("title") or ""
                
                # Use class as deduplication key
                if class_name in self.captured_icon_classes:
                    skipped += 1
                    logger.debug(f"Skipping duplicate icon: {class_name}")
                    continue
                
                metadata = {
                    "type": "icon",
                    "index": captured,
                    "class": class_name,
                    "aria_label": aria_label,
                    "title": title,
                }
                
                screenshot_path = await self.capture_element_screenshot(
                    icon, "icon", captured, metadata
                )
                
                if screenshot_path:
                    metadata["screenshot"] = screenshot_path
                    self.manifest.append(metadata)
                    self.captured_icon_classes.add(class_name)
                    captured += 1
                    
            except Exception as e:
                logger.error(f"Error processing icon {i}: {e}")
        
        logger.info(f"Captured {captured} unique icons, skipped {skipped} duplicates")
    
    async def extract_background_images(self, page: Page):
        """Extract elements with background images."""
        logger.info("Extracting elements with background images...")
        
        # Find all elements with background-image CSS property
        elements_with_bg = await page.query_selector_all('[style*="background"]')
        
        # Also check computed styles for common containers
        containers = await page.query_selector_all('div, section, header, footer, aside')
        
        all_elements = list(set(elements_with_bg + containers))
        logger.info(f"Checking {len(all_elements)} elements for background images")
        
        bg_count = 0
        skipped = 0
        
        for i, element in enumerate(all_elements):
            try:
                # Get computed background-image
                bg_image = await element.evaluate(
                    '(el) => window.getComputedStyle(el).backgroundImage'
                )
                
                if bg_image and bg_image != 'none' and 'url(' in bg_image:
                    # Extract URL from url(...)
                    url_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', bg_image)
                    if url_match:
                        bg_url = url_match.group(1)
                        
                        # Skip if already captured
                        if bg_url in self.captured_bg_urls:
                            skipped += 1
                            logger.debug(f"Skipping duplicate background: {bg_url[:80]}...")
                            continue
                        
                        metadata = {
                            "type": "background",
                            "index": bg_count,
                            "background_url": bg_url,
                        }
                        
                        screenshot_path = await self.capture_element_screenshot(
                            element, "background", bg_count, metadata
                        )
                        
                        if screenshot_path:
                            metadata["screenshot"] = screenshot_path
                            self.manifest.append(metadata)
                            self.captured_bg_urls.add(bg_url)
                            bg_count += 1
                            
            except Exception as e:
                logger.debug(f"Error checking background for element {i}: {e}")
        
        logger.info(f"Captured {bg_count} unique backgrounds, skipped {skipped} duplicates")
    
    async def extract_buttons(self, page: Page):
        """Extract and screenshot button elements."""
        logger.info("Extracting button elements...")
        
        # Find all button elements (button tags, input type=button/submit, and elements with role=button)
        button_selectors = [
            'button',
            'input[type="button"]',
            'input[type="submit"]',
            '[role="button"]',
            'a.btn, a.button',  # Common button-styled links
        ]
        
        all_buttons = []
        for selector in button_selectors:
            try:
                buttons = await page.query_selector_all(selector)
                all_buttons.extend(buttons)
            except Exception as e:
                logger.debug(f"Error with selector {selector}: {e}")
        
        logger.info(f"Found {len(all_buttons)} button elements")
        
        captured = 0
        skipped = 0
        
        for i, button in enumerate(all_buttons):
            try:
                # Get button metadata
                text = await button.inner_text() or ""
                text = text.strip()[:100]  # Limit text length
                
                aria_label = await button.get_attribute("aria-label") or ""
                class_name = await button.get_attribute("class") or ""
                button_type = await button.get_attribute("type") or ""
                value = await button.get_attribute("value") or ""
                
                # Create signature for deduplication (text + class)
                signature = f"{text}|{class_name}|{button_type}"
                
                if signature in self.captured_button_signatures:
                    skipped += 1
                    logger.debug(f"Skipping duplicate button: {text[:30]}...")
                    continue
                
                metadata = {
                    "type": "button",
                    "index": captured,
                    "text": text,
                    "class": class_name,
                    "button_type": button_type,
                    "value": value,
                    "aria_label": aria_label,
                }
                
                screenshot_path = await self.capture_element_screenshot(
                    button, "button", captured, metadata
                )
                
                if screenshot_path:
                    metadata["screenshot"] = screenshot_path
                    
                    # Capture States for interactive elements
                    # Generate base filename for states from the main screenshot path
                    base_name = Path(screenshot_path).stem
                    
                    # Hover
                    hover_path = await self.capture_state_screenshot(button, "button", captured, "hover", base_name)
                    if hover_path:
                        metadata["screenshot_hover"] = hover_path
                        
                    # Focus
                    focus_path = await self.capture_state_screenshot(button, "button", captured, "focus", base_name)
                    if focus_path:
                        metadata["screenshot_focus"] = focus_path

                    self.manifest.append(metadata)
                    self.captured_button_signatures.add(signature)
                    captured += 1
                    
            except Exception as e:
                logger.error(f"Error processing button {i}: {e}")
        
        logger.info(f"Captured {captured} unique buttons, skipped {skipped} duplicates")
    
    async def crawl(self):
        """Main crawling function."""
        logger.info(f"Starting crawl of: {self.url}")
        
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            
            try:
                # Navigate to URL
                logger.info(f"Navigating to {self.url}...")
                await page.goto(self.url, wait_until="domcontentloaded", timeout=90000)
                logger.info("Page loaded successfully")
                
                # Wait a bit for dynamic content
                await page.wait_for_timeout(3000)
                
                # Auto-scroll to trigger lazy loading
                await self.auto_scroll(page)
                
                # Capture Full Page Screenshot
                await self.capture_full_page(page)

                # Extract all visual elements
                await self.extract_images(page)
                await self.extract_svg_elements(page)
                await self.extract_icons(page)
                await self.extract_background_images(page)
                await self.extract_buttons(page)
                
                # Save manifest
                manifest_path = self.dirs["base"] / "manifest.json"
                with open(manifest_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        "url": self.url,
                        "timestamp": datetime.now().isoformat(),
                        "total_screenshots": self.screenshot_count,
                        "elements": self.manifest
                    }, f, indent=2)
                
                logger.info(f"Saved manifest to: {manifest_path}")
                logger.info(f"✓ Crawl complete! Captured {self.screenshot_count} screenshots")
                
            except Exception as e:
                logger.error(f"Error during crawl: {e}", exc_info=True)
                
            finally:
                await browser.close()


# ---------------------------
# Main Entry Point
# ---------------------------


# ---------------------------
# Main Entry Point
# ---------------------------

async def main():
    import argparse

    from visual_analyser import process_directory
    
    parser = argparse.ArgumentParser(
        description="Crawl a website and capture screenshots of visual elements"
    )
    # Changed to accept multiple URLs
    parser.add_argument(
        "--urls",
        nargs='+',
        default=[DEFAULT_URL],
        help=f"List of URLs to crawl (default: {DEFAULT_URL})"
    )
    # Added option for file input
    parser.add_argument(
        "--file",
        type=str,
        help="Path to a text file containing URLs (one per line)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output directory (default: {DEFAULT_OUTPUT_DIR})"
    )
    
    args = parser.parse_args()

    # Collect all URLs to process
    urls_to_crawl = []
    if args.file:
        try:
            with open(args.file, 'r') as f:
                file_urls = [line.strip() for line in f if line.strip()]
                urls_to_crawl.extend(file_urls)
        except Exception as e:
            logger.error(f"Error reading URL file: {e}")
            return

    if args.urls:
         if not args.file:
             urls_to_crawl.extend(args.urls)
         elif args.urls != [DEFAULT_URL]:
             urls_to_crawl.extend(args.urls)

    # Dedup URLs
    urls_to_crawl = list(set(urls_to_crawl))

    if not urls_to_crawl:
        logger.error("No URLs provided to crawl.")
        return
    logger.info(f"Starting batch crawl for {len(urls_to_crawl)} URLs...")

    for url in urls_to_crawl:
        try:
            # Create a unique sub-directory for this URL
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            sanitized_name = sanitize_filename(urlparse(url).netloc, max_length=30)
            run_output_dir = os.path.join(args.output, f"{sanitized_name}_{timestamp}")
            
            logger.info(f"Processing URL: {url} -> {run_output_dir}")
            
            crawler = WebCrawler(url=url, output_dir=run_output_dir)
            await crawler.crawl()
            
            # Run Visual Analysis
            logger.info("Starting Visual Analysis...")
            try:
                process_directory(run_output_dir)
            except Exception as e:
                logger.error(f"Visual Analysis failed: {e}")


            
        except Exception as e:
            logger.error(f"Failed to process {url}: {e}", exc_info=True)

    logger.info("Batch crawl completed.")

if __name__ == "__main__":
    asyncio.run(main())

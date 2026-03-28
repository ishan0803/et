import httpx
from bs4 import BeautifulSoup
from typing import Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class ScrapedContent:
    text: str
    image_urls: list[str]

def scrape_article(url: str) -> Optional[ScrapedContent]:
    """Scrapes paragraph text and high-quality image URLs from a news article."""
    if not url or not url.startswith("http"):
        return None
        
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Extract text paragraphs
            paragraphs = soup.find_all(['p', 'h1', 'h2', 'h3'])
            text_blocks = []
            for p in paragraphs:
                txt = p.get_text(separator=" ", strip=True)
                if len(txt) > 30:  # Skip tiny nav links or boilerplate
                    text_blocks.append(txt)
            
            full_text = "\n\n".join(text_blocks)
            
            # Extract images
            image_urls = []
            
            # 1. OpenGraph Image (usually highest quality hero image)
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                if og_image["content"].startswith("http"):
                    image_urls.append(og_image["content"])
                
            # 2. Extract standard images scoring them on size/relevance
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or img.get("data-original")
                if not src or not src.startswith("http"):
                    continue
                    
                # Filter out obvious icons, logos, tracking pixels
                src_lower = src.lower()
                if any(bad in src_lower for bad in ["icon", "logo", "avatar", "svg", "spinner", "1x1", "tracking", "pixel", "scorecard", "analytics", "metrics", "adsystem", "banner"]):
                    continue
                    
                # Strict extension constraint for deep DOM traversal
                valid_exts = [".jpg", ".jpeg", ".png", ".webp", ".avif"]
                if not any(ext in src_lower for ext in valid_exts):
                    continue
                    
                image_urls.append(src)
            
            # Deduplicate preserving order
            unique_imgs = []
            for img in image_urls:
                if img not in unique_imgs:
                    unique_imgs.append(img)
                    
            logger.info(f"Scraped {len(full_text)} characters and {len(unique_imgs)} images from {url}")
            return ScrapedContent(text=full_text[:12000], image_urls=unique_imgs[:15])
            
    except Exception as e:
        logger.error(f"Failed to scrape article {url}: {e}")
        return None

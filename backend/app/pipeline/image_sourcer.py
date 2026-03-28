"""Image sourcing service using Pexels API."""

import os
import logging
import httpx
from PIL import Image, ImageDraw, ImageFilter
import random
import math

from app.config import settings, WIDTH, HEIGHT, COLOR_PALETTE
from app.models import VisualPlan
from app.utils.helpers import job_dir, hex_to_rgb

logger = logging.getLogger(__name__)

PEXELS_API_URL = "https://api.pexels.com/v1/search"


def source_images(visual_plan: VisualPlan, job_id: str, scraped_image_urls: list[str] = None) -> dict[int, str]:
    """Download images for each scene from Pexels, or directly via scraped URLs."""
    work_dir = job_dir(job_id)
    images_dir = os.path.join(work_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    scene_images: dict[int, str] = {}

    for scene in visual_plan.scenes:
        if scene.has_chart:
            # Charts are generated separately
            continue

        image_path = os.path.join(images_dir, f"scene_{scene.scene_id}.jpg")

        if scraped_image_urls:
            # Try scraped images, validate they have actual visual content
            url = random.choice(scraped_image_urls)
            if _download_direct_image(url, image_path):
                if _is_valid_image(image_path):
                    _process_image(image_path, WIDTH, HEIGHT)
                    scene_images[scene.scene_id] = image_path
                    logger.info(f"Scene {scene.scene_id}: directly injected scraped source image {url}")
                    continue
                else:
                    logger.warning(f"Scene {scene.scene_id}: scraped image {url} is too dark/corrupted, falling back to Pexels")

        success = False

        for attempt in range(3):
            try:
                downloaded = _download_pexels_image(scene.search_query, image_path)
                if downloaded:
                    # Process: resize/crop to 1080x1920
                    _process_image(image_path, WIDTH, HEIGHT)
                    
                    # Validate with Gemini
                    headline = getattr(scene, 'headline', scene.visual_description)
                    is_valid = _validate_image_with_gemini(image_path, scene.search_query, headline)
                    
                    if is_valid:
                        scene_images[scene.scene_id] = image_path
                        logger.info(f"Scene {scene.scene_id}: downloaded and validated image (attempt {attempt+1})")
                        success = True
                        break
                    else:
                        logger.info(f"Scene {scene.scene_id}: image rejected by LLM validator (attempt {attempt+1})")
                else:
                    logger.warning(f"Scene {scene.scene_id}: No image found on Pexels")
            except Exception as e:
                logger.warning(f"Scene {scene.scene_id} attempt {attempt+1} failed during sourcing: {e}")

        if not success:
            logger.warning(f"Scene {scene.scene_id}: All 3 attempts failed or were rejected by QA. Enforcing a generic news broadcast fallback image.")
            
            generic_queries = ["breaking news", "global news background", "journalism", "abstract technology network"]
            generic_success = False
            for gq in generic_queries:
                if _download_pexels_image(gq, image_path):
                    _process_image(image_path, WIDTH, HEIGHT)
                    scene_images[scene.scene_id] = image_path
                    generic_success = True
                    logger.info(f"Scene {scene.scene_id}: Loaded generic fallback image via query: '{gq}'")
                    break
            
            if not generic_success:
                gradient_path = _generate_gradient_bg(scene.scene_id, images_dir)
                scene_images[scene.scene_id] = gradient_path

    return scene_images


def _download_pexels_image(query: str, output_path: str) -> bool:
    """Download the top landscape image from Pexels based on the query."""
    headers = {"Authorization": settings.pexels_api_key}
    params = {
        "query": query,
        "per_page": 10,
        "orientation": "landscape",
        "size": "large",
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(PEXELS_API_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

            photos = data.get("photos", [])
            if not photos:
                # Retry with broader query
                params["query"] = query.split()[0] if query.split() else "news"
                resp = client.get(PEXELS_API_URL, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                photos = data.get("photos", [])

            if not photos:
                return False

            # Pick a random photo from top results for variety
            photo = random.choice(photos[:5])
            img_url = photo["src"]["large2x"]

            # Download the image
            img_resp = client.get(img_url)
            img_resp.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(img_resp.content)

            return True

    except Exception as e:
        logger.error(f"Pexels download error: {e}")
        return False


def _download_direct_image(url: str, output_path: str) -> bool:
    """Directly download an image from a scraped URL."""
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return True
    except Exception as e:
        logger.error(f"Failed to download direct image {url}: {e}")
        return False


def _is_valid_image(image_path: str, min_file_size: int = 5000,
                     min_brightness: int = 10,
                     min_width: int = 800, min_height: int = 600) -> bool:
    """Validate that a downloaded image is high-resolution and contains actual visual content."""
    try:
        file_size = os.path.getsize(image_path)
        if file_size < min_file_size:
            logger.warning(f"Image too small ({file_size} bytes), skipping: {image_path}")
            return False

        with Image.open(image_path) as img:
            w, h = img.size
            if w < min_width or h < min_height:
                logger.warning(f"Image too low-res ({w}x{h}), need at least {min_width}x{min_height}: {image_path}")
                return False

            img = img.convert("RGB")
            small = img.resize((64, 64), Image.LANCZOS)
            pixels = list(small.getdata())
            avg_brightness = sum(sum(p) / 3 for p in pixels) / len(pixels)
            if avg_brightness < min_brightness:
                logger.warning(f"Image too dark (avg brightness {avg_brightness:.1f}), skipping: {image_path}")
                return False
        return True
    except Exception as e:
        logger.warning(f"Image validation failed for {image_path}: {e}")
        return False


def _process_image(image_path: str, target_w: int, target_h: int):
    """Smart crop and resize image to target dimensions."""
    with Image.open(image_path) as img:
        img = img.convert("RGB")

        # Calculate crop dimensions to fill target aspect ratio
        target_ratio = target_w / target_h
        img_ratio = img.width / img.height

        if img_ratio > target_ratio:
            # Image is wider — crop sides
            new_w = int(img.height * target_ratio)
            left = (img.width - new_w) // 2
            img = img.crop((left, 0, left + new_w, img.height))
        else:
            # Image is taller — crop top/bottom
            new_h = int(img.width / target_ratio)
            top = (img.height - new_h) // 2
            img = img.crop((0, top, img.width, top + new_h))

        # Resize to exact output dimensions
        img = img.resize((target_w, target_h), Image.LANCZOS)
        img.save(image_path, "JPEG", quality=88)


def _generate_gradient_bg(scene_id: int, output_dir: str) -> str:
    """Generate a gradient background as fallback."""
    w, h = WIDTH, HEIGHT
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)

    # Use different gradients per scene for variety
    gradients = [
        (hex_to_rgb(COLOR_PALETTE["gradient_start"]), hex_to_rgb(COLOR_PALETTE["bg_dark"])),
        (hex_to_rgb("#1a1a2e"), hex_to_rgb("#16213e")),
        (hex_to_rgb("#0f3460"), hex_to_rgb("#1a1a2e")),
        (hex_to_rgb("#533483"), hex_to_rgb("#0f3460")),
        (hex_to_rgb("#e94560"), hex_to_rgb("#1a1a2e")),
    ]

    c1, c2 = gradients[scene_id % len(gradients)]

    for y in range(h):
        ratio = y / h
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Add subtle noise/texture
    noise = Image.effect_noise((w, h), 15)
    noise = noise.convert("RGB")
    img = Image.blend(img, noise, 0.03)

    path = os.path.join(output_dir, f"scene_{scene_id}.jpg")
    img.save(path, "JPEG", quality=92)
    return path


def _validate_image_with_gemini(image_path: str, query: str, context: str) -> bool:
    """Validate sourced image using Groq."""
    try:
        from groq import Groq
        import base64
        
        client = Groq(api_key=settings.groq_api_key)
        
        with open(image_path, "rb") as f:
            base64_img = base64.b64encode(f.read()).decode('utf-8')
        
        prompt = f"You are a strict news editor. Does this stock image reasonably match the search query '{query}' or the context '{context}'? It doesn't have to be perfect, just relevant enough for a background visual. Answer ONLY 'YES' or 'NO'."
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                    ]
                }
            ],
            temperature=0.1,
            max_tokens=10
        )
        ans = response.choices[0].message.content.strip().upper()
        return "YES" in ans
    except Exception as e:
        logger.warning(f"Multimodal image validation failed to execute: {e}")
        return True  # Fallback to true if API goes down

"""Web scraper tool for the Scraping Agent."""

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import asyncio

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def scrape_article(url: str) -> dict | None:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        title_tag = soup.find("h1")
        if not title_tag:
            return None

        title = title_tag.text.strip()
        paragraphs = soup.find_all("p")
        content = " ".join([p.text.strip() for p in paragraphs])

        date = None
        time_tag = soup.find("time")
        if time_tag:
            date = time_tag.text.strip()

        if len(content) < 150:
            return None

        return {
            "title": title,
            "content": content,
            "date": date,
            "source": "Economic Times",
            "url": url,
        }
    except Exception as e:
        print(f"Error scraping article {url}:", e)
        return None


async def scrape_topic(query: str, max_articles: int = 5) -> list[dict]:
    """Search for a topic and scrape results."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape_topic_sync, query, max_articles)


def _scrape_topic_sync(query: str, max_articles: int) -> list[dict]:
    import os

    search_url = f"https://economictimes.indiatimes.com/searchresult.cms?query={quote(query)}"

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

    options.binary_location = chrome_bin

    try:
        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(15)
    except Exception as e:
        print("Failed to initialize Chrome Driver:", e)
        return []

    try:
        driver.get(search_url)
    except Exception:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass

    html = driver.page_source
    driver.quit()

    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/articleshow/" in href:
            if href.startswith("http"):
                link = href
            else:
                link = "https://economictimes.indiatimes.com" + href
            if link not in links:
                links.append(link)

    articles = []
    for link in links[:max_articles]:
        article = scrape_article(link)
        if article:
            articles.append(article)

    return articles

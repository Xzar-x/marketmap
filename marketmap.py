#!/usr/bin/env python3
"""
MarketMap — E-Commerce Scraper GUI
Real-time scraping of Allegro, OLX, and Vinted listings with keyword filtering.
Single-file architecture, ready for PyInstaller compilation.
"""

from __future__ import annotations

import json
import logging
import math
import queue
import random
import re
import threading
import time
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple, List

import customtkinter as ctk
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# DrissionPage for advanced Allegro scraping (CDP-based)
try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    DRISSION_AVAILABLE = True
except ImportError:
    DRISSION_AVAILABLE = False
    ChromiumPage = None
    ChromiumOptions = None

# Configure logging for DrissionPage scraper
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
drission_logger = logging.getLogger("AllegroDrission")

# ──────────────────────────────────────────────────────────────────────────────
# HUMAN SIMULATION & ANTI-BOT EVASION
# ──────────────────────────────────────────────────────────────────────────────

class HumanSimulator:
    """Simulates human-like browsing behavior to evade anti-bot detection."""

    # Realistic browser fingerprints with matching User-Agents and headers
    BROWSER_PROFILES: list[dict] = [
        {
            "name": "Chrome Windows",
            "user_agents": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ],
            "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec_ch_ua_platform": '"Windows"',
            "sec_ch_ua_mobile": "?0",
        },
        {
            "name": "Firefox Windows",
            "user_agents": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            ],
            "sec_ch_ua": None,
            "sec_ch_ua_platform": None,
            "sec_ch_ua_mobile": None,
        },
        {
            "name": "Edge Windows",
            "user_agents": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            ],
            "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"',
            "sec_ch_ua_platform": '"Windows"',
            "sec_ch_ua_mobile": "?0",
        },
        {
            "name": "Chrome Mac",
            "user_agents": [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            ],
            "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec_ch_ua_platform": '"macOS"',
            "sec_ch_ua_mobile": "?0",
        },
        {
            "name": "Safari Mac",
            "user_agents": [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            ],
            "sec_ch_ua": None,
            "sec_ch_ua_platform": None,
            "sec_ch_ua_mobile": None,
        },
    ]

    # Realistic screen resolutions
    SCREEN_RESOLUTIONS: list[str] = [
        "1920x1080", "2560x1440", "1366x768", "1536x864",
        "1440x900", "1680x1050", "2560x1080", "3840x2160",
    ]

    # Realistic Accept-Language headers for Polish users
    ACCEPT_LANGUAGES: list[str] = [
        "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
        "pl-PL,pl;q=0.9,en;q=0.8",
        "pl,en-US;q=0.9,en;q=0.8",
        "pl-PL,pl;q=0.8,en-US;q=0.6,en;q=0.4",
    ]

    def __init__(self) -> None:
        self._current_profile: dict = random.choice(self.BROWSER_PROFILES)
        self._current_ua: str = random.choice(self._current_profile["user_agents"])
        self._session_start: float = time.time()
        self._request_count: int = 0
        self._last_request_time: float = 0
        # Fallback to fake_useragent for variety
        self._ua_fallback: UserAgent = UserAgent()

    def rotate_identity(self) -> None:
        """Rotate to a new browser identity."""
        self._current_profile = random.choice(self.BROWSER_PROFILES)
        self._current_ua = random.choice(self._current_profile["user_agents"])
        self._request_count = 0

    def get_user_agent(self) -> str:
        """Get current or rotated User-Agent string."""
        # Rotate identity every 5-15 requests randomly
        if self._request_count > random.randint(5, 15):
            self.rotate_identity()

        # 20% chance to use fake_useragent for more variety
        if random.random() < 0.2:
            try:
                return self._ua_fallback.random
            except Exception:
                pass

        return self._current_ua

    def get_headers(self, referer: Optional[str] = None) -> dict[str, str]:
        """Generate realistic browser headers with fingerprint consistency."""
        self._request_count += 1
        ua = self.get_user_agent()

        headers: dict[str, str] = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": random.choice(self.ACCEPT_LANGUAGES),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "DNT": "1" if random.random() > 0.5 else "0",
        }

        # Add Sec-CH-UA headers for Chromium-based browsers
        if self._current_profile.get("sec_ch_ua"):
            headers["Sec-CH-UA"] = self._current_profile["sec_ch_ua"]
            headers["Sec-CH-UA-Mobile"] = self._current_profile["sec_ch_ua_mobile"]
            headers["Sec-CH-UA-Platform"] = self._current_profile["sec_ch_ua_platform"]

        # Add Sec-Fetch headers (modern browsers)
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "same-origin" if referer else "none"
        headers["Sec-Fetch-User"] = "?1"

        if referer:
            headers["Referer"] = referer

        return headers

    def human_delay(self, min_sec: float = 1.0, max_sec: float = 4.0) -> None:
        """Simulate human-like delay with natural variation."""
        # Add jitter to make delays less predictable
        base_delay = random.uniform(min_sec, max_sec)

        # Occasionally add longer "thinking" pauses (simulating reading)
        if random.random() < 0.15:
            base_delay += random.uniform(1.0, 3.0)

        # Add micro-variations to avoid detection patterns
        jitter = random.gauss(0, 0.2)
        final_delay = max(0.5, base_delay + jitter)

        time.sleep(final_delay)

    def reading_delay(self) -> None:
        """Simulate time spent reading a page."""
        # Humans take time to read/process content
        time.sleep(random.uniform(0.5, 2.0))

    def typing_delay(self) -> None:
        """Simulate typing speed delay."""
        # Simulate human typing speed (40-80 WPM)
        time.sleep(random.uniform(0.05, 0.15))

    def request_throttle(self) -> None:
        """Ensure minimum time between requests to avoid rate limiting."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        # Minimum 0.5-1.5 seconds between requests
        min_interval = random.uniform(0.5, 1.5)
        if time_since_last < min_interval:
            time.sleep(min_interval - time_since_last)

        self._last_request_time = time.time()

    def should_take_break(self) -> bool:
        """Determine if we should take a longer break (simulates human fatigue)."""
        # Take a break every 20-40 requests
        return self._request_count > 0 and self._request_count % random.randint(20, 40) == 0

    def take_break(self) -> None:
        """Take a longer break to simulate human behavior."""
        print("[HumanSimulator] Taking a short break...")
        time.sleep(random.uniform(5.0, 15.0))
        self.rotate_identity()  # Change identity after break


# Global human simulator instance for consistent behavior
_human_sim: Optional[HumanSimulator] = None


def get_human_simulator() -> HumanSimulator:
    """Get or create the global human simulator instance."""
    global _human_sim
    if _human_sim is None:
        _human_sim = HumanSimulator()
    return _human_sim


# ──────────────────────────────────────────────────────────────────────────────
# DRISSIONPAGE CDP SCRAPER (Advanced Allegro Anti-Bot Evasion)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DrissionListing:
    """Represents a single Allegro listing from DrissionPage scraper."""
    title: str
    price: Optional[float]
    price_text: str
    url: str
    seller: str = ""
    is_promoted: bool = False


@dataclass
class DrissionScrapeResult:
    """Result of a DrissionPage scraping session."""
    success: bool
    listings: List[DrissionListing] = field(default_factory=list)
    error_message: str = ""
    pages_scraped: int = 0


class BezierMouseMover:
    """Generates human-like mouse movements using cubic Bezier curves."""

    @staticmethod
    def _bezier_point(
        t: float,
        p0: Tuple[float, float],
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        p3: Tuple[float, float],
    ) -> Tuple[float, float]:
        """Calculate a point on a cubic Bezier curve at parameter t."""
        u = 1 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t
        x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
        y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
        return (x, y)

    @staticmethod
    def _generate_control_points(
        start: Tuple[float, float],
        end: Tuple[float, float],
    ) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """Generate random control points for a Bezier curve."""
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.sqrt(dx * dx + dy * dy)
        offset_range = max(50, distance * 0.3)
        cp1_x = start[0] + dx * random.uniform(0.2, 0.4) + random.uniform(-offset_range, offset_range)
        cp1_y = start[1] + dy * random.uniform(0.2, 0.4) + random.uniform(-offset_range, offset_range)
        cp2_x = start[0] + dx * random.uniform(0.6, 0.8) + random.uniform(-offset_range, offset_range)
        cp2_y = start[1] + dy * random.uniform(0.6, 0.8) + random.uniform(-offset_range, offset_range)
        return ((cp1_x, cp1_y), (cp2_x, cp2_y))

    def generate_path(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        num_points: int = 50,
    ) -> List[Tuple[int, int]]:
        """Generate a list of points along a Bezier curve from start to end."""
        cp1, cp2 = self._generate_control_points(start, end)
        points: List[Tuple[int, int]] = []
        for i in range(num_points + 1):
            t = i / num_points
            if 0 < t < 1:
                t += random.gauss(0, 0.01)
                t = max(0, min(1, t))
            point = self._bezier_point(t, start, cp1, cp2, end)
            points.append((int(point[0]), int(point[1])))
        return points


class DrissionHumanTyper:
    """Simulates human-like typing with Gaussian delays."""
    BASE_DELAY_MS: float = 80
    VARIANCE_MS: float = 30
    SPACE_DELAY_FACTOR: float = 1.2
    SHIFT_DELAY_FACTOR: float = 1.5
    PUNCTUATION_DELAY_FACTOR: float = 1.3
    PAUSE_PROBABILITY: float = 0.05
    PAUSE_MIN_MS: float = 200
    PAUSE_MAX_MS: float = 600

    def get_delay_for_char(self, char: str, prev_char: str = "") -> float:
        """Calculate delay before typing a character (in seconds)."""
        delay_ms = random.gauss(self.BASE_DELAY_MS, self.VARIANCE_MS)
        delay_ms = max(20, delay_ms)
        if char == " ":
            delay_ms *= self.SPACE_DELAY_FACTOR
        elif char.isupper():
            delay_ms *= self.SHIFT_DELAY_FACTOR
        elif not char.isalnum():
            delay_ms *= self.PUNCTUATION_DELAY_FACTOR
        if random.random() < self.PAUSE_PROBABILITY:
            delay_ms += random.uniform(self.PAUSE_MIN_MS, self.PAUSE_MAX_MS)
        return delay_ms / 1000

    def type_text(self, page, element, text: str) -> None:
        """Type text into an element with human-like delays."""
        prev_char = ""
        for char in text:
            delay = self.get_delay_for_char(char, prev_char)
            time.sleep(delay)
            element.input(char, clear=False)
            prev_char = char


class SmartScroller:
    """Implements human-like scrolling behavior for lazy-loading."""
    MIN_SCROLL_PX: int = 200
    MAX_SCROLL_PX: int = 600
    MIN_PAUSE_SEC: float = 0.3
    MAX_PAUSE_SEC: float = 1.5
    READING_PAUSE_PROBABILITY: float = 0.15
    READING_PAUSE_MIN_SEC: float = 1.5
    READING_PAUSE_MAX_SEC: float = 4.0
    SCROLL_BACK_PROBABILITY: float = 0.08
    SCROLL_BACK_AMOUNT: int = 150

    def scroll_page(self, page, scroll_times: int = 5, wait_for_content: bool = True) -> None:
        """Scroll the page with human-like behavior."""
        for i in range(scroll_times):
            scroll_amount = random.randint(self.MIN_SCROLL_PX, self.MAX_SCROLL_PX)
            if random.random() < self.SCROLL_BACK_PROBABILITY and i > 0:
                page.scroll.down(self.SCROLL_BACK_AMOUNT * -1)
                time.sleep(random.uniform(0.2, 0.5))
            page.scroll.down(scroll_amount)
            if wait_for_content:
                time.sleep(random.uniform(self.MIN_PAUSE_SEC, self.MAX_PAUSE_SEC))
            if random.random() < self.READING_PAUSE_PROBABILITY:
                time.sleep(random.uniform(self.READING_PAUSE_MIN_SEC, self.READING_PAUSE_MAX_SEC))


class AllegroDrissionScraper:
    """Allegro.pl scraper using DrissionPage with CDP (Chrome DevTools Protocol)."""
    ALLEGRO_URL: str = "https://allegro.pl"
    COOKIE_ACCEPT_SELECTOR: str = "button[data-role='accept-consent']"
    SEARCH_INPUT_SELECTOR: str = "input[type='search'], input[data-role='search-input'], input[name='string']"
    SEARCH_BUTTON_SELECTOR: str = "button[type='submit'], button[data-role='search-button']"

    def __init__(self, headless: bool = False) -> None:
        if not DRISSION_AVAILABLE:
            raise RuntimeError("DrissionPage is required. Install with: pip install DrissionPage")
        self._headless = headless
        self._page = None
        self._mouse_mover = BezierMouseMover()
        self._typer = DrissionHumanTyper()
        self._scroller = SmartScroller()
        drission_logger.info("AllegroDrissionScraper initialized")

    def _create_browser_options(self):
        """Create browser options with anti-detection settings."""
        options = ChromiumOptions()
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        ]
        options.set_user_agent(random.choice(user_agents))
        options.set_argument("--disable-blink-features=AutomationControlled")
        options.set_argument("--disable-infobars")
        options.set_argument("--disable-dev-shm-usage")
        options.set_argument("--no-sandbox")
        options.set_argument(f"--window-size={random.randint(1280, 1920)},{random.randint(800, 1080)}")
        options.set_argument("--lang=pl-PL")
        if self._headless:
            options.set_argument("--headless=new")
        options.set_argument("--disable-webrtc")
        return options

    def _start_browser(self) -> None:
        """Start the browser with anti-detection settings."""
        drission_logger.info("Starting browser...")
        options = self._create_browser_options()
        self._page = ChromiumPage(options)
        self._inject_anti_detection_js()
        drission_logger.info("Browser started successfully")

    def _inject_anti_detection_js(self) -> None:
        """Inject JavaScript to evade bot detection."""
        if self._page is None:
            return
        js_code = """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['pl-PL', 'pl', 'en-US', 'en'] });
        window.chrome = { runtime: {} };
        """
        try:
            self._page.run_js(js_code)
        except Exception as e:
            drission_logger.warning(f"Failed to inject anti-detection JS: {e}")

    def _human_delay(self, min_sec: float = 0.5, max_sec: float = 2.0) -> None:
        time.sleep(random.uniform(min_sec, max_sec))

    def _handle_cookie_popup(self) -> bool:
        """Handle the RODO/cookie consent popup."""
        try:
            self._human_delay(1.0, 2.0)
            selectors = [
                self.COOKIE_ACCEPT_SELECTOR,
                "[data-role='accept-consent']",
                "button:contains('Akceptuję')",
                "[class*='cookie'] button",
            ]
            for selector in selectors:
                try:
                    button = self._page.ele(selector, timeout=2)
                    if button:
                        button.click()
                        drission_logger.info("Cookie popup accepted")
                        self._human_delay(0.5, 1.0)
                        return True
                except:
                    continue
            return False
        except:
            return False

    def _perform_search(self, query: str) -> bool:
        """Perform a search on Allegro."""
        try:
            search_input = None
            for selector in [self.SEARCH_INPUT_SELECTOR, "input[type='search']", "#search-input"]:
                try:
                    search_input = self._page.ele(selector, timeout=3)
                    if search_input:
                        break
                except:
                    continue
            if not search_input:
                return False
            search_input.click()
            self._human_delay(0.3, 0.6)
            search_input.clear()
            self._typer.type_text(self._page, search_input, query)
            self._human_delay(0.5, 1.0)
            try:
                search_btn = self._page.ele(self.SEARCH_BUTTON_SELECTOR, timeout=2)
                if search_btn:
                    search_btn.click()
            except:
                search_input.input("\n", clear=False)
            self._human_delay(2.0, 4.0)
            return True
        except Exception as e:
            drission_logger.error(f"Search failed: {e}")
            return False

    def _parse_drission_price(self, price_text: str) -> Optional[float]:
        """Parse price from text."""
        if not price_text:
            return None
        cleaned = price_text.replace("\xa0", "").replace(" ", "").replace(",", ".")
        match = re.search(r"(\d+\.?\d*)", cleaned)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def _extract_listings(self) -> List[DrissionListing]:
        """Extract listing data from the current page."""
        listings: List[DrissionListing] = []
        try:
            self._scroller.scroll_page(self._page, scroll_times=3)
            articles = []
            for selector in ["article[data-item]", "div[data-box-name='items'] article", "article"]:
                try:
                    found = self._page.eles(selector)
                    if found and len(found) > 0:
                        articles = found
                        break
                except:
                    continue
            for article in articles:
                try:
                    title_elem = article.ele("h2") or article.ele("h3") or article.ele("[class*='title']")
                    title = title_elem.text.strip() if title_elem else ""
                    if not title:
                        continue
                    price_elem = article.ele("[class*='price']")
                    price_text = price_elem.text.strip() if price_elem else ""
                    price = self._parse_drission_price(price_text)
                    link_elem = article.ele("a[href*='/oferta/']")
                    url = link_elem.attr("href") if link_elem else ""
                    if url and not url.startswith("http"):
                        url = f"https://allegro.pl{url}"
                    listings.append(DrissionListing(
                        title=title, price=price, price_text=price_text, url=url
                    ))
                except:
                    continue
            drission_logger.info(f"Extracted {len(listings)} listings")
        except Exception as e:
            drission_logger.error(f"Error extracting listings: {e}")
        return listings

    def search(self, query: str, max_pages: int = 1) -> DrissionScrapeResult:
        """Perform a search on Allegro and return results."""
        result = DrissionScrapeResult(success=False)
        try:
            if self._page is None:
                self._start_browser()
            drission_logger.info(f"Navigating to {self.ALLEGRO_URL}")
            self._page.get(self.ALLEGRO_URL)
            self._human_delay(2.0, 4.0)
            self._handle_cookie_popup()
            if not self._perform_search(query):
                result.error_message = "Search failed"
                return result
            self._human_delay(2.0, 3.0)
            all_listings: List[DrissionListing] = []
            for page_num in range(max_pages):
                page_listings = self._extract_listings()
                all_listings.extend(page_listings)
            result.success = True
            result.listings = all_listings
            result.pages_scraped = max_pages
            drission_logger.info(f"Search complete: {len(all_listings)} listings")
        except Exception as e:
            drission_logger.error(f"Search error: {e}")
            result.error_message = str(e)
        return result

    def close(self) -> None:
        """Close the browser."""
        if self._page:
            try:
                self._page.quit()
            except:
                pass
            self._page = None

    def __enter__(self) -> "AllegroDrissionScraper":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ──────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ScrapeResult:
    """Single scraped listing."""
    portal: str
    title: str
    price: Optional[float]
    price_text: str
    url: str
    matched_keywords: list[str] = field(default_factory=list)


@dataclass
class ScrapeConfig:
    """Configuration passed from GUI to the scraper manager."""
    platforms: list[str]
    keyword_expression: str  # Boolean expression, e.g. "ddr5 i ram i (cl30 lub cl40)"
    price_min: Optional[float]
    price_max: Optional[float]


# ──────────────────────────────────────────────────────────────────────────────
# PRICE PARSER
# ──────────────────────────────────────────────────────────────────────────────

def parse_price(raw: str) -> Optional[float]:
    """Extract a numeric price from a string like '1 299,50 zł'."""
    if not raw:
        return None
    cleaned: str = raw.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    match = re.search(r"(\d+\.?\d*)", cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


# ──────────────────────────────────────────────────────────────────────────────
# INTELLIGENT KEYWORD FILTER (Boolean Expression Parser)
# Syntax: keyword1 i keyword2 lub (keyword3 i keyword4)
# Operators: 'i' (AND), 'lub' (OR), parentheses for grouping
# ──────────────────────────────────────────────────────────────────────────────

class TokenType:
    """Token types for the expression parser."""
    KEYWORD = "KEYWORD"
    AND = "AND"
    OR = "OR"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    EOF = "EOF"


@dataclass
class Token:
    """A single token from the expression."""
    type: str
    value: str


class KeywordExpressionLexer:
    """Tokenizes a keyword expression string."""

    # Operators in Polish and symbols
    AND_KEYWORDS = {"i", "and", "&", "&&", "+"}
    OR_KEYWORDS = {"lub", "or", "|", "||"}

    def __init__(self, expression: str) -> None:
        self._expr: str = expression
        self._pos: int = 0
        self._length: int = len(expression)

    def _current_char(self) -> Optional[str]:
        if self._pos >= self._length:
            return None
        return self._expr[self._pos]

    def _advance(self) -> None:
        self._pos += 1

    def _skip_whitespace(self) -> None:
        while self._current_char() is not None and self._current_char().isspace():
            self._advance()

    def _read_word(self) -> str:
        """Read a word (keyword or operator)."""
        start = self._pos
        while self._current_char() is not None:
            ch = self._current_char()
            if ch.isspace() or ch in "()":
                break
            self._advance()
        return self._expr[start:self._pos]

    def tokenize(self) -> list[Token]:
        """Convert the expression into a list of tokens."""
        tokens: list[Token] = []

        while self._pos < self._length:
            self._skip_whitespace()

            if self._pos >= self._length:
                break

            ch = self._current_char()

            if ch == "(":
                tokens.append(Token(TokenType.LPAREN, "("))
                self._advance()
            elif ch == ")":
                tokens.append(Token(TokenType.RPAREN, ")"))
                self._advance()
            else:
                word = self._read_word()
                if not word:
                    continue

                word_lower = word.lower()
                if word_lower in self.AND_KEYWORDS:
                    tokens.append(Token(TokenType.AND, word))
                elif word_lower in self.OR_KEYWORDS:
                    tokens.append(Token(TokenType.OR, word))
                else:
                    tokens.append(Token(TokenType.KEYWORD, word))

        tokens.append(Token(TokenType.EOF, ""))
        return tokens


class KeywordExpressionNode(ABC):
    """Base class for expression AST nodes."""

    @abstractmethod
    def evaluate(self, text: str) -> bool:
        """Evaluate this node against the given text."""
        ...

    @abstractmethod
    def get_keywords(self) -> list[str]:
        """Return all keywords in this expression."""
        ...

    @abstractmethod
    def get_matched_keywords(self, text: str) -> list[str]:
        """Return keywords that matched in the text."""
        ...


@dataclass
class KeywordNode(KeywordExpressionNode):
    """A leaf node representing a single keyword."""
    keyword: str

    def evaluate(self, text: str) -> bool:
        return self.keyword.lower() in text.lower()

    def get_keywords(self) -> list[str]:
        return [self.keyword]

    def get_matched_keywords(self, text: str) -> list[str]:
        if self.evaluate(text):
            return [self.keyword]
        return []


@dataclass
class AndNode(KeywordExpressionNode):
    """A node representing AND operation between two expressions."""
    left: KeywordExpressionNode
    right: KeywordExpressionNode

    def evaluate(self, text: str) -> bool:
        return self.left.evaluate(text) and self.right.evaluate(text)

    def get_keywords(self) -> list[str]:
        return self.left.get_keywords() + self.right.get_keywords()

    def get_matched_keywords(self, text: str) -> list[str]:
        return self.left.get_matched_keywords(text) + self.right.get_matched_keywords(text)


@dataclass
class OrNode(KeywordExpressionNode):
    """A node representing OR operation between two expressions."""
    left: KeywordExpressionNode
    right: KeywordExpressionNode

    def evaluate(self, text: str) -> bool:
        return self.left.evaluate(text) or self.right.evaluate(text)

    def get_keywords(self) -> list[str]:
        return self.left.get_keywords() + self.right.get_keywords()

    def get_matched_keywords(self, text: str) -> list[str]:
        return self.left.get_matched_keywords(text) + self.right.get_matched_keywords(text)


class KeywordExpressionParser:
    """
    Recursive descent parser for keyword expressions.

    Grammar:
        expression  -> term ((OR) term)*
        term        -> factor ((AND) factor)*
        factor      -> KEYWORD | LPAREN expression RPAREN

    Examples:
        - "ddr5 i ram" -> ddr5 AND ram
        - "ddr5 lub ddr4" -> ddr5 OR ddr4
        - "ddr5 i (cl30 lub cl40)" -> ddr5 AND (cl30 OR cl40)
        - "ddr5 i ram i (cl30 lub cl40) i (2x16 lub 32)" -> complex expression
    """

    def __init__(self, expression: str) -> None:
        self._expression: str = expression
        self._tokens: list[Token] = []
        self._pos: int = 0

    def _current_token(self) -> Token:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return Token(TokenType.EOF, "")

    def _advance(self) -> Token:
        token = self._current_token()
        self._pos += 1
        return token

    def _expect(self, token_type: str) -> Token:
        token = self._current_token()
        if token.type != token_type:
            raise ValueError(f"Expected {token_type}, got {token.type} at position {self._pos}")
        return self._advance()

    def parse(self) -> KeywordExpressionNode:
        """Parse the expression and return the AST root."""
        # Handle empty or simple expressions
        if not self._expression.strip():
            raise ValueError("Empty expression")

        lexer = KeywordExpressionLexer(self._expression)
        self._tokens = lexer.tokenize()
        self._pos = 0

        # Check if it's a simple comma/space-separated list (legacy format)
        has_operators = any(
            t.type in (TokenType.AND, TokenType.OR, TokenType.LPAREN)
            for t in self._tokens
        )

        if not has_operators:
            # Legacy mode: treat as simple keyword list (implicit AND)
            keywords = [t.value for t in self._tokens if t.type == TokenType.KEYWORD]
            if not keywords:
                raise ValueError("No keywords found")
            if len(keywords) == 1:
                return KeywordNode(keywords[0])
            # Chain all keywords with AND
            result: KeywordExpressionNode = KeywordNode(keywords[0])
            for kw in keywords[1:]:
                result = AndNode(result, KeywordNode(kw))
            return result

        return self._parse_expression()

    def _parse_expression(self) -> KeywordExpressionNode:
        """Parse: expression -> term ((OR) term)*"""
        left = self._parse_term()

        while self._current_token().type == TokenType.OR:
            self._advance()  # consume OR
            right = self._parse_term()
            left = OrNode(left, right)

        return left

    def _parse_term(self) -> KeywordExpressionNode:
        """Parse: term -> factor ((AND) factor)*"""
        left = self._parse_factor()

        while self._current_token().type == TokenType.AND:
            self._advance()  # consume AND
            right = self._parse_factor()
            left = AndNode(left, right)

        return left

    def _parse_factor(self) -> KeywordExpressionNode:
        """Parse: factor -> KEYWORD | LPAREN expression RPAREN"""
        token = self._current_token()

        if token.type == TokenType.KEYWORD:
            self._advance()
            return KeywordNode(token.value)

        if token.type == TokenType.LPAREN:
            self._advance()  # consume (
            node = self._parse_expression()
            self._expect(TokenType.RPAREN)  # consume )
            return node

        raise ValueError(f"Unexpected token: {token.type} '{token.value}'")


class KeywordFilter:
    """
    Intelligent keyword filter supporting boolean expressions.

    Usage:
        filter = KeywordFilter("ddr5 i ram i (cl30 lub cl40)")
        if filter.matches("DDR5 RAM 32GB CL30"):
            print("Match!")
    """

    def __init__(self, expression: str) -> None:
        self._expression: str = expression
        self._root: Optional[KeywordExpressionNode] = None
        self._parse_error: Optional[str] = None
        self._parse()

    def _parse(self) -> None:
        """Parse the expression."""
        try:
            parser = KeywordExpressionParser(self._expression)
            self._root = parser.parse()
        except ValueError as e:
            self._parse_error = str(e)
            self._root = None

    def is_valid(self) -> bool:
        """Check if the expression was parsed successfully."""
        return self._root is not None

    def get_error(self) -> Optional[str]:
        """Get the parse error message, if any."""
        return self._parse_error

    def matches(self, text: str) -> bool:
        """Check if the text matches the expression."""
        if self._root is None:
            return False
        return self._root.evaluate(text)

    def get_all_keywords(self) -> list[str]:
        """Get all keywords in the expression."""
        if self._root is None:
            return []
        return self._root.get_keywords()

    def get_matched_keywords(self, text: str) -> list[str]:
        """Get the keywords that matched in the text."""
        if self._root is None:
            return []
        return self._root.get_matched_keywords(text)

    def get_search_terms(self) -> list[str]:
        """
        Get keywords suitable for search queries.
        Returns unique keywords without duplicates.
        """
        if self._root is None:
            return []
        return list(dict.fromkeys(self._root.get_keywords()))


# ──────────────────────────────────────────────────────────────────────────────
# AI ANALYSIS - SMART ANALYZER & GEMINI
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    """Result of AI/Smart analysis for a single listing."""
    score: float  # 0-100, higher is better value
    recommendation: str  # "🌟 SWEET SPOT", "✅ Dobra oferta", "⚠️ Przepłacone", etc.
    reasoning: str  # Why this score
    price_percentile: float  # Where this price falls in the distribution
    quality_indicators: list[str]  # Detected quality keywords


class SmartAnalyzer:
    """
    Local heuristic-based analyzer for finding price/quality sweet spots.
    Works offline, no API needed.
    """

    # Quality indicators with their weight multipliers
    QUALITY_KEYWORDS: dict[str, float] = {
        # High quality indicators
        "nowy": 1.2, "nowe": 1.2, "nowa": 1.2,
        "oryginał": 1.3, "orginalny": 1.3,
        "gwarancja": 1.25, "gwarancją": 1.25,
        "faktura": 1.15, "vat": 1.1,
        "premium": 1.3, "pro": 1.15,
        "idealne": 1.2, "idealny": 1.2,
        "pełny zestaw": 1.2, "komplet": 1.15,
        # Technical quality
        "rgb": 1.05, "gaming": 1.1,
        "16gb": 1.1, "32gb": 1.2, "64gb": 1.25,
        "ssd": 1.1, "nvme": 1.15,
        "rtx": 1.2, "gtx": 1.1,
        "i7": 1.15, "i9": 1.2, "ryzen 7": 1.15, "ryzen 9": 1.2,
        # Negative indicators (reduce score)
        "uszkodzony": 0.5, "uszkodzona": 0.5,
        "na części": 0.4, "części": 0.6,
        "niesprawny": 0.3, "zepsuty": 0.3,
        "do naprawy": 0.4,
        "bez": 0.8,  # "bez zasilacza", "bez kabla" etc.
        "brak": 0.7,
    }

    # Platform trust scores
    PLATFORM_TRUST: dict[str, float] = {
        "Allegro": 1.1,  # Higher trust due to buyer protection
        "OLX": 0.95,
        "Vinted": 1.0,
    }

    def analyze(self, results: list[ScrapeResult]) -> dict[str, AnalysisResult]:
        """
        Analyze all results and return analysis for each.
        Returns dict mapping result URL to AnalysisResult.
        """
        if not results:
            return {}

        # Calculate price statistics
        prices = [r.price for r in results if r.price is not None and r.price > 0]
        if not prices:
            return {}

        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)
        price_range = max_price - min_price if max_price > min_price else 1

        # Sort prices for percentile calculation
        sorted_prices = sorted(prices)

        analysis: dict[str, AnalysisResult] = {}

        for result in results:
            if result.price is None or result.price <= 0:
                continue

            # Calculate price percentile (0 = cheapest, 100 = most expensive)
            price_percentile = self._calculate_percentile(result.price, sorted_prices)

            # Calculate quality score based on title keywords
            quality_score, quality_indicators = self._analyze_quality(result.title)

            # Apply platform trust multiplier
            platform_multiplier = self.PLATFORM_TRUST.get(result.portal, 1.0)

            # Calculate value score
            # Sweet spot = good quality at lower price percentile
            # Formula: quality_score * (100 - price_percentile) * platform_trust
            raw_score = quality_score * ((100 - price_percentile) / 50) * platform_multiplier
            final_score = min(100, max(0, raw_score * 50))  # Normalize to 0-100

            # Determine recommendation
            recommendation, reasoning = self._get_recommendation(
                final_score, price_percentile, quality_score, quality_indicators, result.price, avg_price
            )

            analysis[result.url] = AnalysisResult(
                score=round(final_score, 1),
                recommendation=recommendation,
                reasoning=reasoning,
                price_percentile=round(price_percentile, 1),
                quality_indicators=quality_indicators,
            )

        return analysis

    def _calculate_percentile(self, price: float, sorted_prices: list[float]) -> float:
        """Calculate what percentile this price falls into."""
        count_below = sum(1 for p in sorted_prices if p < price)
        return (count_below / len(sorted_prices)) * 100

    def _analyze_quality(self, title: str) -> tuple[float, list[str]]:
        """Analyze title for quality indicators. Returns (score, indicators)."""
        title_lower = title.lower()
        score = 1.0
        indicators: list[str] = []

        for keyword, multiplier in self.QUALITY_KEYWORDS.items():
            if keyword in title_lower:
                score *= multiplier
                if multiplier > 1.0:
                    indicators.append(f"✅ {keyword}")
                elif multiplier < 1.0:
                    indicators.append(f"⚠️ {keyword}")

        return score, indicators

    def _get_recommendation(
        self,
        score: float,
        price_pct: float,
        quality: float,
        indicators: list[str],
        price: float,
        avg_price: float,
    ) -> tuple[str, str]:
        """Get recommendation text and reasoning."""
        price_vs_avg = ((price - avg_price) / avg_price) * 100 if avg_price > 0 else 0

        if score >= 75:
            rec = "🌟 SWEET SPOT"
            reason = f"Wysoka jakość ({quality:.1f}x) w dobrej cenie (percentyl {price_pct:.0f}%)"
        elif score >= 60:
            rec = "✅ Dobra oferta"
            reason = f"Dobry stosunek jakości do ceny"
        elif score >= 40:
            rec = "🟡 Przeciętna"
            if price_vs_avg > 20:
                reason = f"Cena {price_vs_avg:.0f}% powyżej średniej"
            else:
                reason = f"Standardowa oferta"
        elif score >= 20:
            rec = "⚠️ Droższa"
            reason = f"Cena w górnym przedziale (percentyl {price_pct:.0f}%)"
        else:
            rec = "❌ Przepłacone"
            reason = f"Wysoka cena, niska wartość"

        if indicators:
            negative = [i for i in indicators if "⚠️" in i]
            if negative:
                reason += f" | Uwaga: {', '.join(negative)}"

        return rec, reason

    def get_top_recommendations(self, results: list[ScrapeResult], top_n: int = 3) -> list[tuple[ScrapeResult, AnalysisResult]]:
        """Get top N sweet spot recommendations."""
        analysis = self.analyze(results)
        scored_results = [
            (r, analysis[r.url])
            for r in results
            if r.url in analysis
        ]
        scored_results.sort(key=lambda x: x[1].score, reverse=True)
        return scored_results[:top_n]


class GeminiAnalyzer:
    """
    Google Gemini AI analyzer for advanced price/quality analysis.
    Requires free API key from Google AI Studio.
    Uses fallback strategy: best model first, then fallback to older models.
    """

    # Models in order of preference (best first, fallback to older)
    GEMINI_MODELS = [
        "gemini-2.5-flash",      # Best price-performance, stable
        "gemini-2.5-pro",        # Most capable, stable
        "gemini-2.0-flash",      # Previous gen (deprecated March 2026)
    ]

    API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def analyze(self, results: list[ScrapeResult], context: str = "") -> Optional[str]:
        """
        Analyze results using Gemini AI with fallback strategy.
        Returns AI-generated analysis text.
        """
        if not results:
            return None

        # Prepare data for AI
        listings_text = self._prepare_listings(results)

        prompt = f"""Jesteś ekspertem od zakupów online w Polsce. Przeanalizuj poniższe ogłoszenia i wskaż najlepsze oferty (sweet spot cena/jakość).

Kontekst wyszukiwania: {context if context else 'brak'}

Ogłoszenia:
{listings_text}

Przeanalizuj i odpowiedz w formacie:
1. 🌟 TOP 3 REKOMENDACJE - najlepszy stosunek cena/jakość
2. ⚠️ UNIKAJ - oferty przepłacone lub podejrzane
3. 📊 PODSUMOWANIE - ogólna ocena rynku i sugerowany przedział cenowy

Bądź zwięzły i konkretny. Odpowiadaj po polsku."""

        # Try each model in order until one works
        last_error = None
        for model in self.GEMINI_MODELS:
            try:
                url = f"{self.API_BASE}/{model}:generateContent?key={self._api_key}"
                response = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.7,
                            "maxOutputTokens": 8096,
                        }
                    },
                    timeout=60,
                )

                if response.status_code == 200:
                    data = response.json()
                    if "candidates" in data and data["candidates"]:
                        print(f"[Gemini] Success with model: {model}")
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    last_error = f"{response.status_code}: {response.text[:100]}"
                    print(f"[Gemini] Model {model} failed: {last_error}")
                    continue  # Try next model

            except Exception as exc:
                last_error = str(exc)
                print(f"[Gemini] Model {model} error: {exc}")
                continue  # Try next model

        print(f"[Gemini] All models failed. Last error: {last_error}")
        return None

    def _prepare_listings(self, results: list[ScrapeResult]) -> str:
        """Format results for AI prompt."""
        lines: list[str] = []
        for i, r in enumerate(results[:20], 1):  # Limit to 20 to avoid token limits
            price_str = f"{r.price:.2f} zł" if r.price else "brak ceny"
            lines.append(f"{i}. [{r.portal}] {r.title[:80]} - {price_str}")
        return "\n".join(lines)

    @staticmethod
    def validate_api_key(api_key: str) -> bool:
        """Quick validation of API key using current model."""
        if not api_key or len(api_key) < 20:
            return False
        try:
            # Try with gemini-2.5-flash (best price-performance)
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": "test"}]}]},
                timeout=10,
            )
            return resp.status_code == 200
        except:
            return False


# ──────────────────────────────────────────────────────────────────────────────
# BASE SCRAPER
# ──────────────────────────────────────────────────────────────────────────────

class BaseScraper(ABC):
    """Abstract base for all platform scrapers."""

    PORTAL_NAME: str = ""
    REQUEST_TIMEOUT: int = 15
    MAX_RETRIES: int = 3

    def __init__(self) -> None:
        self._human: HumanSimulator = get_human_simulator()
        self._session: requests.Session = requests.Session()
        # Initialize session with realistic browser behavior
        self._session.headers.update(self._human.get_headers())

    def _get_headers(self, referer: Optional[str] = None) -> dict[str, str]:
        """Get realistic browser headers using HumanSimulator."""
        return self._human.get_headers(referer=referer)

    def _fetch(self, url: str, referer: Optional[str] = None) -> Optional[BeautifulSoup]:
        """Fetch a URL with human-like behavior and return parsed soup."""
        # Throttle requests to avoid detection
        self._human.request_throttle()

        # Check if we should take a break
        if self._human.should_take_break():
            self._human.take_break()

        for attempt in range(self.MAX_RETRIES):
            try:
                # Update headers for each request (rotation)
                headers = self._get_headers(referer=referer)
                self._session.headers.update(headers)

                resp: requests.Response = self._session.get(
                    url,
                    timeout=self.REQUEST_TIMEOUT,
                )

                # Check for anti-bot responses
                if resp.status_code == 429:  # Too Many Requests
                    print(f"[{self.PORTAL_NAME}] Rate limited, waiting...")
                    self._human.take_break()
                    continue

                if resp.status_code == 403:
                    print(f"[{self.PORTAL_NAME}] Access forbidden, rotating identity...")
                    self._human.rotate_identity()
                    self._human.human_delay(2.0, 5.0)
                    continue

                resp.raise_for_status()

                # Simulate reading the page
                self._human.reading_delay()

                return BeautifulSoup(resp.text, "html.parser")

            except requests.RequestException as exc:
                print(f"[{self.PORTAL_NAME}] Request error (attempt {attempt + 1}): {exc}")
                if attempt < self.MAX_RETRIES - 1:
                    self._human.human_delay(2.0, 5.0)
                    self._human.rotate_identity()
                continue

        return None

    def _random_delay(self) -> None:
        """Human-like delay between actions."""
        self._human.human_delay()

    @abstractmethod
    def search(
        self,
        keywords: list[str],
        price_min: Optional[float],
        price_max: Optional[float],
        cancel_event: threading.Event,
    ) -> list[ScrapeResult]:
        """Run the search and return raw results (before keyword filtering)."""
        ...


# ──────────────────────────────────────────────────────────────────────────────
# ALLEGRO SCRAPER
# ──────────────────────────────────────────────────────────────────────────────

class AllegroScraper(BaseScraper):
    PORTAL_NAME: str = "Allegro"
    ALLEGRO_BASE: str = "https://allegro.pl"
    MAX_RETRIES: int = 5  # More retries for Allegro

    # Mobile user agents (often less blocked)
    MOBILE_USER_AGENTS: list[str] = [
        "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cookies_acquired: bool = False
        self._use_mobile: bool = False
        self._attempt_count: int = 0
        self._last_successful_ua: Optional[str] = None

    def _get_allegro_headers(self, referer: Optional[str] = None, mobile: bool = False) -> dict[str, str]:
        """Get headers optimized for Allegro with anti-detection measures."""
        if mobile:
            ua = random.choice(self.MOBILE_USER_AGENTS)
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin" if referer else "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }
        else:
            headers = self._human.get_headers(referer=referer)
            # Add extra headers that real browsers send
            headers["Pragma"] = "no-cache"
            headers["Cache-Control"] = "no-cache"

        if referer:
            headers["Referer"] = referer

        return headers

    def _create_fresh_session(self) -> None:
        """Create a completely fresh session with new identity."""
        self._session = requests.Session()
        self._cookies_acquired = False
        self._human.rotate_identity()

    def _warm_up_session(self) -> bool:
        """Visit Allegro with realistic browsing pattern."""
        if self._cookies_acquired:
            return True

        print(f"[{self.PORTAL_NAME}] Warming up session (mobile={self._use_mobile})...")

        try:
            # Step 1: Visit main page
            headers = self._get_allegro_headers(mobile=self._use_mobile)
            self._session.headers.update(headers)

            self._human.request_throttle()
            resp = self._session.get(
                self.ALLEGRO_BASE,
                timeout=self.REQUEST_TIMEOUT,
                allow_redirects=True
            )

            # Check for Cloudflare challenge
            if resp.status_code == 403 or "cf-" in resp.text.lower() or "challenge" in resp.text.lower():
                print(f"[{self.PORTAL_NAME}] Cloudflare challenge detected during warm-up")
                return False

            if resp.status_code == 200:
                self._cookies_acquired = True
                self._last_successful_ua = headers.get("User-Agent")
                self._human.reading_delay()
                print(f"[{self.PORTAL_NAME}] Session warmed up successfully")

                # Step 2: Sometimes visit a category page to look more natural
                if random.random() < 0.3:
                    self._human.human_delay(1.0, 2.5)
                    category_url = f"{self.ALLEGRO_BASE}/kategoria/elektronika"
                    self._session.get(category_url, timeout=self.REQUEST_TIMEOUT)
                    self._human.reading_delay()

                return True

        except requests.RequestException as exc:
            print(f"[{self.PORTAL_NAME}] Warm-up failed: {exc}")

        return False

    def _fetch_with_session(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch using session with advanced anti-bot evasion for Allegro."""
        strategies = [
            {"mobile": False, "fresh_session": False},
            {"mobile": False, "fresh_session": True},
            {"mobile": True, "fresh_session": True},
            {"mobile": True, "fresh_session": False},
            {"mobile": False, "fresh_session": True},  # Last resort: try desktop again
        ]

        for attempt, strategy in enumerate(strategies[:self.MAX_RETRIES]):
            if attempt > 0:
                # Exponential backoff with jitter
                wait_time = min(30, (2 ** attempt) + random.uniform(0, 2))
                print(f"[{self.PORTAL_NAME}] Waiting {wait_time:.1f}s before retry...")
                time.sleep(wait_time)

            self._use_mobile = strategy["mobile"]

            if strategy["fresh_session"]:
                self._create_fresh_session()

            # Try to warm up
            if not self._warm_up_session():
                print(f"[{self.PORTAL_NAME}] Warm-up failed, trying next strategy...")
                continue

            self._human.human_delay(1.5, 3.0)

            try:
                # Use the same UA that worked for warm-up
                headers = self._get_allegro_headers(
                    referer=f"{self.ALLEGRO_BASE}/",
                    mobile=self._use_mobile
                )
                if self._last_successful_ua:
                    headers["User-Agent"] = self._last_successful_ua

                self._session.headers.update(headers)
                self._human.request_throttle()

                resp: requests.Response = self._session.get(
                    url,
                    timeout=self.REQUEST_TIMEOUT,
                    allow_redirects=True
                )

                # Check for various anti-bot responses
                if resp.status_code == 429:
                    print(f"[{self.PORTAL_NAME}] Rate limited (429)")
                    self._cookies_acquired = False
                    continue

                if resp.status_code == 403:
                    print(f"[{self.PORTAL_NAME}] Forbidden (403)")
                    self._cookies_acquired = False
                    continue

                # Check for Cloudflare/CAPTCHA in response body
                if any(marker in resp.text.lower() for marker in ["captcha", "cf-browser-verification", "challenge-running"]):
                    print(f"[{self.PORTAL_NAME}] CAPTCHA/Challenge detected in response")
                    self._cookies_acquired = False
                    continue

                resp.raise_for_status()

                # Verify we got actual listing content
                soup = BeautifulSoup(resp.text, "html.parser")
                if soup.select("article") or soup.select("[data-box-name='items']") or "listing" in resp.url:
                    self._human.reading_delay()
                    return soup
                else:
                    print(f"[{self.PORTAL_NAME}] Response doesn't contain listings, might be blocked")
                    self._cookies_acquired = False
                    continue

            except requests.RequestException as exc:
                print(f"[{self.PORTAL_NAME}] Request error (attempt {attempt + 1}): {exc}")
                self._cookies_acquired = False

        # All strategies failed
        print(f"[{self.PORTAL_NAME}] All strategies exhausted")
        raise requests.RequestException(
            "Allegro anti-bot active. Spróbuj później lub użyj VPN."
        )

    def search(
        self,
        keywords: list[str],
        price_min: Optional[float],
        price_max: Optional[float],
        cancel_event: threading.Event,
    ) -> list[ScrapeResult]:
        results: list[ScrapeResult] = []
        query: str = "+".join(kw.strip() for kw in keywords)
        url: str = f"https://allegro.pl/listing?string={query}"

        if price_min is not None:
            url += f"&price_from={price_min:.0f}"
        if price_max is not None:
            url += f"&price_to={price_max:.0f}"

        if cancel_event.is_set():
            return results

        # Try requests-based scraping first
        soup: Optional[BeautifulSoup] = None
        try:
            soup = self._fetch_with_session(url)
        except requests.RequestException as e:
            print(f"[{self.PORTAL_NAME}] Requests failed: {e}")
            # Fallback to DrissionPage
            if DRISSION_AVAILABLE:
                return self._search_with_drission(keywords, price_min, price_max)
            raise

        if soup is None:
            # Fallback to DrissionPage if requests returned nothing
            if DRISSION_AVAILABLE:
                return self._search_with_drission(keywords, price_min, price_max)
            return results

        # Allegro listing articles
        articles = soup.select("article[data-role='offer']")
        if not articles:
            articles = soup.select("div[data-box-name='items-v3'] article")
        if not articles:
            articles = soup.select("div.opbox-listing article")

        for article in articles:
            if cancel_event.is_set():
                break

            # Title — look for the offer link with /oferta/ in href
            title_el = article.select_one("a[href*='/oferta/']")
            if title_el is None:
                title_el = article.select_one("h2 a")
            if not title_el:
                continue
            title: str = title_el.get_text(strip=True)
            if not title:
                # Title might be in alt of image or a nested span
                alt_el = article.select_one("img[alt]")
                if alt_el:
                    title = alt_el.get("alt", "")
            if not title:
                continue

            link: str = title_el.get("href", "")
            if link and not link.startswith("http"):
                link = "https://allegro.pl" + link
            # Skip tracking/click redirect URLs
            if "/events/clicks" in link:
                real_link = article.select_one("a[href*='/oferta/']")
                if real_link:
                    link = real_link.get("href", link)
                    if link and not link.startswith("http"):
                        link = "https://allegro.pl" + link

            # Price
            price_el = article.select_one(
                "span[class*='price'], span[aria-label*='cena']"
            )
            price_text: str = price_el.get_text(strip=True) if price_el else ""
            price_val: Optional[float] = parse_price(price_text)

            results.append(
                ScrapeResult(
                    portal=self.PORTAL_NAME,
                    title=title,
                    price=price_val,
                    price_text=price_text,
                    url=link,
                )
            )

        self._random_delay()
        return results

    def _search_with_drission(self, keywords: list[str], price_min: Optional[float], price_max: Optional[float]) -> list[ScrapeResult]:
        """Fallback: Use DrissionPage CDP-based scraper for Allegro."""
        if not DRISSION_AVAILABLE:
            print(f"[{self.PORTAL_NAME}] DrissionPage not available")
            return []

        print(f"[{self.PORTAL_NAME}] Trying DrissionPage (CDP browser)...")
        results: list[ScrapeResult] = []

        try:
            query = " ".join(keywords)
            with AllegroDrissionScraper(headless=True) as scraper:
                drission_result = scraper.search(query, max_pages=1)

                if drission_result.success:
                    for listing in drission_result.listings:
                        # Filter by price if specified
                        if listing.price is not None:
                            if price_min is not None and listing.price < price_min:
                                continue
                            if price_max is not None and listing.price > price_max:
                                continue

                        results.append(ScrapeResult(
                            portal=self.PORTAL_NAME,
                            title=listing.title,
                            price=listing.price,
                            price_text=listing.price_text,
                            url=listing.url,
                        ))

                    print(f"[{self.PORTAL_NAME}] DrissionPage: {len(results)} results")
                else:
                    print(f"[{self.PORTAL_NAME}] DrissionPage failed: {drission_result.error_message}")

        except Exception as e:
            print(f"[{self.PORTAL_NAME}] DrissionPage error: {e}")

        return results


# ──────────────────────────────────────────────────────────────────────────────
# OLX SCRAPER
# ──────────────────────────────────────────────────────────────────────────────

class OLXScraper(BaseScraper):
    PORTAL_NAME: str = "OLX"
    OLX_BASE: str = "https://www.olx.pl"

    def __init__(self) -> None:
        super().__init__()
        self._cookies_acquired: bool = False

    def _warm_up_session(self) -> None:
        """Visit OLX homepage to establish cookies and appear more human."""
        if self._cookies_acquired:
            return

        print(f"[{self.PORTAL_NAME}] Warming up session...")
        self._human.request_throttle()

        try:
            headers = self._human.get_headers()
            self._session.headers.update(headers)
            resp = self._session.get(self.OLX_BASE, timeout=self.REQUEST_TIMEOUT)

            if resp.status_code == 200:
                self._cookies_acquired = True
                self._human.reading_delay()
                print(f"[{self.PORTAL_NAME}] Session warmed up successfully")

        except requests.RequestException as exc:
            print(f"[{self.PORTAL_NAME}] Warm-up failed: {exc}")

    def search(
        self,
        keywords: list[str],
        price_min: Optional[float],
        price_max: Optional[float],
        cancel_event: threading.Event,
    ) -> list[ScrapeResult]:
        results: list[ScrapeResult] = []
        query: str = " ".join(kw.strip() for kw in keywords)
        url: str = f"{self.OLX_BASE}/oferty/q-{query}/"

        params: list[str] = []
        if price_min is not None:
            params.append(f"search[filter_float_price:from]={price_min:.0f}")
        if price_max is not None:
            params.append(f"search[filter_float_price:to]={price_max:.0f}")
        if params:
            url += "?" + "&".join(params)

        if cancel_event.is_set():
            return results

        # Warm up session first
        self._warm_up_session()
        self._random_delay()

        # Fetch with retry — OLX sometimes serves empty pages on first hit
        cards: list = []
        soup: Optional[BeautifulSoup] = None
        for attempt in range(1 + self.MAX_RETRIES):
            if cancel_event.is_set():
                return results

            # Use base class _fetch with human simulation
            soup = self._fetch(url, referer=f"{self.OLX_BASE}/")
            if soup is None:
                self._human.rotate_identity()
                self._cookies_acquired = False
                continue

            cards = soup.select("div[data-cy='l-card']")
            if not cards:
                cards = soup.select("div[data-testid='l-card']")

            if cards:
                break  # Got results, no need to retry

            # No cards found — log and retry after delay
            print(f"[{self.PORTAL_NAME}] Attempt {attempt + 1}: 0 cards, retrying...")
            if attempt < self.MAX_RETRIES:
                self._human.rotate_identity()
                self._random_delay()

        for card in cards:
            if cancel_event.is_set():
                break

            # Title — data-testid='ad-card-title' is a <div> containing title text
            title_el = card.select_one(
                "[data-testid='ad-card-title'], h4, h6"
            )
            if title_el is None:
                continue
            title: str = title_el.get_text(strip=True)

            # Link — OLX uses /d/oferta/ pattern
            link_el = card.select_one("a[href*='/d/oferta/'], a[href*='/d/']")
            if link_el is None:
                link_el = card.select_one("a")
            if link_el is None:
                continue

            link: str = link_el.get("href", "")
            if link and not link.startswith("http"):
                link = "https://www.olx.pl" + link

            # Price — data-testid='ad-price' is a <p>
            price_el = card.select_one(
                "[data-testid='ad-price']"
            )
            price_text: str = price_el.get_text(strip=True) if price_el else ""
            price_val: Optional[float] = parse_price(price_text)

            results.append(
                ScrapeResult(
                    portal=self.PORTAL_NAME,
                    title=title,
                    price=price_val,
                    price_text=price_text,
                    url=link,
                )
            )

        self._random_delay()
        return results


# ──────────────────────────────────────────────────────────────────────────────
# VINTED SCRAPER
# ──────────────────────────────────────────────────────────────────────────────

class VintedScraper(BaseScraper):
    PORTAL_NAME: str = "Vinted"
    VINTED_BASE: str = "https://www.vinted.pl"

    def __init__(self) -> None:
        super().__init__()
        self._cookies_acquired: bool = False

    def _warm_up_session(self) -> None:
        """Visit Vinted homepage to establish cookies and appear more human."""
        if self._cookies_acquired:
            return

        print(f"[{self.PORTAL_NAME}] Warming up session...")
        self._human.request_throttle()

        try:
            headers = self._human.get_headers()
            self._session.headers.update(headers)
            resp = self._session.get(self.VINTED_BASE, timeout=self.REQUEST_TIMEOUT)

            if resp.status_code == 200:
                self._cookies_acquired = True
                self._human.reading_delay()
                print(f"[{self.PORTAL_NAME}] Session warmed up successfully")

        except requests.RequestException as exc:
            print(f"[{self.PORTAL_NAME}] Warm-up failed: {exc}")

    def search(
        self,
        keywords: list[str],
        price_min: Optional[float],
        price_max: Optional[float],
        cancel_event: threading.Event,
    ) -> list[ScrapeResult]:
        results: list[ScrapeResult] = []
        query: str = "+".join(kw.strip() for kw in keywords)
        url: str = f"{self.VINTED_BASE}/catalog?search_text={query}"

        if price_min is not None:
            url += f"&price_from={price_min:.0f}"
        if price_max is not None:
            url += f"&price_to={price_max:.0f}"

        if cancel_event.is_set():
            return results

        # Warm up session first
        self._warm_up_session()
        self._random_delay()

        soup: Optional[BeautifulSoup] = self._fetch(url, referer=f"{self.VINTED_BASE}/")
        if soup is None:
            return results

        # Vinted item grid — confirmed via live HTML
        items = soup.select("div.feed-grid__item")
        if not items:
            items = soup.select("div[data-testid='grid-item']")

        for item in items:
            if cancel_event.is_set():
                break

            # Link — overlay link contains title in its 'title' attribute
            link_el = item.select_one(
                "a[data-testid*='overlay-link'], "
                "a.new-item-box__overlay, "
                "a[href*='/items/']"
            )
            if link_el is None:
                link_el = item.select_one("a")
            if link_el is None:
                continue

            link: str = link_el.get("href", "")
            if link and not link.startswith("http"):
                link = "https://www.vinted.pl" + link

            # Title — stored in the overlay <a> tag's 'title' attribute
            title: str = link_el.get("title", "") or ""
            if not title:
                # Fallback: try img alt or description
                img_el = item.select_one("img[alt]")
                if img_el:
                    title = img_el.get("alt", "")
            if not title:
                # Last resort: description title
                desc_el = item.select_one("[data-testid*='description-title']")
                if desc_el:
                    title = desc_el.get_text(strip=True)

            # Price — data-testid contains 'price-text'
            price_el = item.select_one(
                "[data-testid*='price-text'], "
                "div.new-item-box__title, "
                "div.title-content"
            )
            price_text: str = price_el.get_text(strip=True) if price_el else ""
            price_val: Optional[float] = parse_price(price_text)

            if title:
                results.append(
                    ScrapeResult(
                        portal=self.PORTAL_NAME,
                        title=title,
                        price=price_val,
                        price_text=price_text,
                        url=link,
                    )
                )

        self._random_delay()
        return results


# ──────────────────────────────────────────────────────────────────────────────
# SCRAPER MANAGER
# ──────────────────────────────────────────────────────────────────────────────

SCRAPERS: dict[str, type[BaseScraper]] = {
    "Allegro": AllegroScraper,
    "OLX": OLXScraper,
    "Vinted": VintedScraper,
}


class ScraperManager:
    """Orchestrates scraping across platforms with intelligent keyword filtering."""

    def __init__(
        self,
        config: ScrapeConfig,
        result_queue: queue.Queue[ScrapeResult],
        cancel_event: threading.Event,
        on_status: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._config: ScrapeConfig = config
        self._queue: queue.Queue[ScrapeResult] = result_queue
        self._cancel: threading.Event = cancel_event
        self._on_status: Optional[Callable[[str], None]] = on_status
        self._on_done: Optional[Callable[[str], None]] = on_done
        self._total_found: int = 0
        # Per-platform tracking for detailed status
        self._platform_results: dict[str, int] = {}
        self._platform_errors: dict[str, str] = {}
        # Initialize the keyword filter with boolean expression support
        self._keyword_filter: KeywordFilter = KeywordFilter(config.keyword_expression)

    def _passes_filter(self, result: ScrapeResult) -> bool:
        """Check if result passes keyword expression and price range."""
        # Keyword filtering using boolean expression parser
        if not self._keyword_filter.matches(result.title):
            return False

        # Store matched keywords for display
        result.matched_keywords = self._keyword_filter.get_matched_keywords(result.title)

        # Price filtering
        if result.price is not None:
            if self._config.price_min is not None and result.price < self._config.price_min:
                return False
            if self._config.price_max is not None and result.price > self._config.price_max:
                return False

        return True

    def get_search_keywords(self) -> list[str]:
        """Get keywords to use for search queries (sent to platforms)."""
        return self._keyword_filter.get_search_terms()

    def _emit_status(self, msg: str) -> None:
        if self._on_status:
            self._on_status(msg)

    def _build_summary(self) -> str:
        """Build a detailed per-platform summary string."""
        parts: list[str] = []
        for platform in self._config.platforms:
            if platform in self._platform_errors:
                short_err: str = self._platform_errors[platform]
                # Shorten long error messages
                if len(short_err) > 30:
                    short_err = short_err[:27] + "..."
                parts.append(f"{platform}: ⚠ {short_err}")
            elif platform in self._platform_results:
                count: int = self._platform_results[platform]
                parts.append(f"{platform}: {count}")
            else:
                parts.append(f"{platform}: —")

        total: str = f"✅ {self._total_found} results"
        detail: str = " | ".join(parts)
        return f"{total}  ({detail})"

    def run(self) -> None:
        """Run all selected scrapers. Meant to be called in a background thread."""
        # Get search keywords from the expression (for platform queries)
        search_keywords = self.get_search_keywords()

        for platform in self._config.platforms:
            if self._cancel.is_set():
                break

            scraper_cls: Optional[type[BaseScraper]] = SCRAPERS.get(platform)
            if scraper_cls is None:
                continue

            self._emit_status(f"Scanning {platform}...")

            try:
                scraper: BaseScraper = scraper_cls()
                raw_results: list[ScrapeResult] = scraper.search(
                    keywords=search_keywords,
                    price_min=self._config.price_min,
                    price_max=self._config.price_max,
                    cancel_event=self._cancel,
                )

                platform_count: int = 0
                for result in raw_results:
                    if self._cancel.is_set():
                        break
                    if self._passes_filter(result):
                        self._total_found += 1
                        platform_count += 1
                        self._queue.put(result)

                self._platform_results[platform] = platform_count
                self._emit_status(
                    f"✓ {platform}: {platform_count} matches"
                )

            except Exception as exc:
                err_msg: str = str(exc) if str(exc) else type(exc).__name__
                self._platform_errors[platform] = err_msg
                self._emit_status(f"⚠ {platform}: {err_msg}")
                print(f"[ScraperManager] {platform} error: {exc}")
                continue

        if self._on_done:
            self._on_done(self._build_summary())


# ──────────────────────────────────────────────────────────────────────────────
# GUI COMPONENTS
# ──────────────────────────────────────────────────────────────────────────────

# Color palette
COLORS = {
    "bg_dark": "#0d0f12",
    "sidebar_bg": "#141820",
    "card_bg": "#1a1f2e",
    "card_hover": "#232a3c",
    "accent": "#6c63ff",
    "accent_hover": "#7f78ff",
    "accent_glow": "#6c63ff40",
    "success": "#00d68f",
    "warning": "#ffaa00",
    "danger": "#ff6b6b",
    "text_primary": "#e8eaf0",
    "text_secondary": "#8a8fa8",
    "text_muted": "#555b70",
    "border": "#2a3040",
    "allegro_badge": "#ff5a00",
    "olx_badge": "#002f34",
    "vinted_badge": "#09b1ba",
}


class ResultCard(ctk.CTkFrame):
    """Single result card widget displayed in the scrollable results area."""

    BADGE_COLORS: dict[str, str] = {
        "Allegro": COLORS["allegro_badge"],
        "OLX": COLORS["olx_badge"],
        "Vinted": COLORS["vinted_badge"],
    }

    def __init__(self, master: ctk.CTkBaseClass, result: ScrapeResult, **kwargs) -> None:
        super().__init__(
            master,
            fg_color=COLORS["card_bg"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border"],
            **kwargs,
        )
        self._result: ScrapeResult = result
        self._build_ui()
        # Bind mousewheel so scroll propagates to the parent scrollable frame
        self._bind_mousewheel(self)

    def _bind_mousewheel(self, widget: ctk.CTkBaseClass) -> None:
        """Recursively bind mousewheel events to propagate to parent scrollable frame."""
        widget.bind("<Button-4>", self._on_mousewheel, add="+")
        widget.bind("<Button-5>", self._on_mousewheel, add="+")
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_mousewheel(child)

    def _on_mousewheel(self, event) -> None:  # type: ignore[no-untyped-def]
        """Forward mousewheel events to the parent scrollable frame."""
        # Find the CTkScrollableFrame parent
        parent = self.master
        while parent is not None:
            if isinstance(parent, ctk.CTkScrollableFrame):
                # Access the internal canvas of CTkScrollableFrame
                canvas = parent._parent_canvas  # type: ignore[attr-defined]
                if event.num == 4 or (hasattr(event, 'delta') and event.delta > 0):
                    canvas.yview_scroll(-3, "units")
                elif event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
                    canvas.yview_scroll(3, "units")
                break
            parent = getattr(parent, 'master', None)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)

        # Portal badge
        badge_color: str = self.BADGE_COLORS.get(self._result.portal, COLORS["accent"])
        badge = ctk.CTkLabel(
            self,
            text=f" {self._result.portal} ",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=badge_color,
            corner_radius=6,
            text_color="#ffffff",
            width=70,
            height=26,
        )
        badge.grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=12, sticky="n")

        # Title
        title_label = ctk.CTkLabel(
            self,
            text=self._result.title[:100] + ("…" if len(self._result.title) > 100 else ""),
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLORS["text_primary"],
            anchor="w",
            wraplength=500,
        )
        title_label.grid(row=0, column=1, padx=4, pady=(12, 2), sticky="w")

        # Info row: matched keywords + price
        keywords_str: str = ", ".join(self._result.matched_keywords) if self._result.matched_keywords else "—"
        info_text: str = f"🔑 {keywords_str}"
        if self._result.price_text:
            info_text += f"   •   💰 {self._result.price_text}"

        info_label = ctk.CTkLabel(
            self,
            text=info_text,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        info_label.grid(row=1, column=1, padx=4, pady=(0, 12), sticky="w")

        # Open button
        open_btn = ctk.CTkButton(
            self,
            text="Otwórz →",
            width=90,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            corner_radius=8,
            command=lambda: webbrowser.open(self._result.url),
        )
        open_btn.grid(row=0, column=2, rowspan=2, padx=12, pady=12)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN APPLICATION
# ──────────────────────────────────────────────────────────────────────────────

class MarketMapApp(ctk.CTk):
    """Main application window."""

    APP_TITLE: str = "MarketMap — E-Commerce Scanner"
    APP_SIZE: tuple[int, int] = (1200, 720)
    SIDEBAR_WIDTH: int = 300
    POLL_INTERVAL_MS: int = 200

    def __init__(self) -> None:
        super().__init__()

        # Window config
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title(self.APP_TITLE)
        self.geometry(f"{self.APP_SIZE[0]}x{self.APP_SIZE[1]}")
        self.minsize(900, 550)
        self.configure(fg_color=COLORS["bg_dark"])

        # State
        self._result_queue: queue.Queue[ScrapeResult] = queue.Queue()
        self._cancel_event: threading.Event = threading.Event()
        self._is_scanning: bool = False
        self._result_count: int = 0
        self._result_cards: list[ResultCard] = []
        self._all_results: list[ScrapeResult] = []  # Store all results for AI analysis

        # Platform checkboxes state
        self._chk_allegro_var: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._chk_olx_var: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._chk_vinted_var: ctk.BooleanVar = ctk.BooleanVar(value=True)

        # AI Analysis state
        self._smart_analyzer: SmartAnalyzer = SmartAnalyzer()
        self._analysis_results: dict[str, AnalysisResult] = {}

        # Settings (loaded from config file)
        self._settings: dict = self._load_settings()

        # Build UI
        self._build_layout()

    # ── Settings Persistence ────────────────────────────────────────────────

    def _get_config_path(self) -> str:
        """Get path to config file."""
        import os
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        config_dir = os.path.join(app_data, "MarketMap")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "settings.json")

    def _load_settings(self) -> dict:
        """Load settings from config file."""
        default_settings = {
            "ai_provider": "gemini",  # gemini, openai, anthropic
            "gemini_api_key": "",
            "openai_api_key": "",
            "anthropic_api_key": "",
        }
        try:
            config_path = self._get_config_path()
            import os
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    default_settings.update(loaded)
        except Exception as e:
            print(f"[Settings] Failed to load: {e}")
        return default_settings

    def _save_settings(self) -> None:
        """Save settings to config file."""
        try:
            config_path = self._get_config_path()
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
        except Exception as e:
            print(f"[Settings] Failed to save: {e}")

    # ── Layout ────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_area()

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self,
            width=self.SIDEBAR_WIDTH,
            fg_color=COLORS["sidebar_bg"],
            corner_radius=0,
            border_width=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        row: int = 0

        # ── Logo / Title
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.grid(row=row, column=0, padx=20, pady=(24, 4), sticky="ew")

        logo_label = ctk.CTkLabel(
            logo_frame,
            text="🗺️  MarketMap",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        logo_label.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            logo_frame,
            text="E-Commerce Scanner",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        subtitle.pack(anchor="w", pady=(0, 0))
        row += 1

        # ── Divider
        div1 = ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"])
        div1.grid(row=row, column=0, padx=20, pady=(16, 16), sticky="ew")
        row += 1

        # ── Section: Platforms
        sec_platforms = ctk.CTkLabel(
            sidebar,
            text="PLATFORMS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        sec_platforms.grid(row=row, column=0, padx=24, pady=(0, 8), sticky="w")
        row += 1

        platforms_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        platforms_frame.grid(row=row, column=0, padx=20, sticky="ew")

        self._chk_allegro = ctk.CTkCheckBox(
            platforms_frame,
            text="🟠  Allegro",
            variable=self._chk_allegro_var,
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_primary"],
            fg_color=COLORS["allegro_badge"],
            hover_color=COLORS["allegro_badge"],
            border_color=COLORS["border"],
            corner_radius=6,
        )
        self._chk_allegro.pack(anchor="w", pady=3)

        self._chk_olx = ctk.CTkCheckBox(
            platforms_frame,
            text="🟢  OLX",
            variable=self._chk_olx_var,
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_primary"],
            fg_color=COLORS["olx_badge"],
            hover_color=COLORS["olx_badge"],
            border_color=COLORS["border"],
            corner_radius=6,
        )
        self._chk_olx.pack(anchor="w", pady=3)

        self._chk_vinted = ctk.CTkCheckBox(
            platforms_frame,
            text="🔵  Vinted",
            variable=self._chk_vinted_var,
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_primary"],
            fg_color=COLORS["vinted_badge"],
            hover_color=COLORS["vinted_badge"],
            border_color=COLORS["border"],
            corner_radius=6,
        )
        self._chk_vinted.pack(anchor="w", pady=3)
        row += 1

        # ── Divider
        div2 = ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"])
        div2.grid(row=row, column=0, padx=20, pady=16, sticky="ew")
        row += 1

        # ── Section: Keywords (with intelligent filtering)
        sec_kw = ctk.CTkLabel(
            sidebar,
            text="FILTER EXPRESSION",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        sec_kw.grid(row=row, column=0, padx=24, pady=(0, 6), sticky="w")
        row += 1

        self._keywords_entry = ctk.CTkEntry(
            sidebar,
            placeholder_text="np. ddr5 i (cl30 lub cl40)",
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["card_bg"],
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
            height=38,
        )
        self._keywords_entry.grid(row=row, column=0, padx=20, sticky="ew")
        row += 1

        # ── Syntax help label
        syntax_help = ctk.CTkLabel(
            sidebar,
            text="ℹ 'i' lub '+' (AND), 'lub' lub '||' (OR)",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        syntax_help.grid(row=row, column=0, padx=24, pady=(4, 0), sticky="w")
        row += 1

        # ── Divider
        div3 = ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"])
        div3.grid(row=row, column=0, padx=20, pady=16, sticky="ew")
        row += 1

        # ── Section: Price Range
        sec_price = ctk.CTkLabel(
            sidebar,
            text="PRICE RANGE (PLN)",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        sec_price.grid(row=row, column=0, padx=24, pady=(0, 6), sticky="w")
        row += 1

        price_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        price_frame.grid(row=row, column=0, padx=20, sticky="ew")
        price_frame.grid_columnconfigure((0, 1), weight=1)

        self._price_min_entry = ctk.CTkEntry(
            price_frame,
            placeholder_text="Min",
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["card_bg"],
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
            height=36,
            width=100,
        )
        self._price_min_entry.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self._price_max_entry = ctk.CTkEntry(
            price_frame,
            placeholder_text="Max",
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["card_bg"],
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
            height=36,
            width=100,
        )
        self._price_max_entry.grid(row=0, column=1, padx=(4, 0), sticky="ew")
        row += 1

        # ── Divider
        div4 = ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"])
        div4.grid(row=row, column=0, padx=20, pady=16, sticky="ew")
        row += 1

        # ── START / STOP button
        self._start_btn = ctk.CTkButton(
            sidebar,
            text="▶   START SCAN",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            corner_radius=10,
            height=48,
            command=self._on_start_stop,
        )
        self._start_btn.grid(row=row, column=0, padx=20, sticky="ew")
        row += 1

        # ── Status label
        self._status_label = ctk.CTkLabel(
            sidebar,
            text="Ready",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        self._status_label.grid(row=row, column=0, padx=24, pady=(10, 10), sticky="w")
        row += 1

        # ── Options button
        options_btn = ctk.CTkButton(
            sidebar,
            text="⚙   Opcje",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=10,
            height=40,
            command=self._show_options_dialog,
        )
        options_btn.grid(row=row, column=0, padx=20, pady=(0, 8), sticky="ew")
        row += 1

        # ── Close button
        close_btn = ctk.CTkButton(
            sidebar,
            text="✕   Zamknij",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=10,
            height=40,
            command=self.destroy,
        )
        close_btn.grid(row=row, column=0, padx=20, pady=(0, 20), sticky="ew")

    def _build_main_area(self) -> None:
        main_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], corner_radius=0)
        main_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)

        # ── Header bar
        header = ctk.CTkFrame(main_frame, fg_color="transparent", height=56)
        header.grid(row=0, column=0, padx=24, pady=(16, 4), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        results_title = ctk.CTkLabel(
            header,
            text="📋  Results",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        results_title.grid(row=0, column=0, sticky="w")

        self._results_counter = ctk.CTkLabel(
            header,
            text="0 items found",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["text_muted"],
            anchor="e",
        )
        self._results_counter.grid(row=0, column=1, sticky="e", padx=(0, 4))

        # ── AI Analyze button
        self._analyze_btn = ctk.CTkButton(
            header,
            text="🧠 Analizuj AI",
            width=110,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            corner_radius=8,
            command=self._show_ai_analysis,
        )
        self._analyze_btn.grid(row=0, column=2, padx=(8, 0))

        # ── Clear button
        clear_btn = ctk.CTkButton(
            header,
            text="🗑  Clear",
            width=80,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=8,
            command=self._clear_results,
        )
        clear_btn.grid(row=0, column=3, padx=(8, 0))

        # ── Scrollable results
        self._results_frame = ctk.CTkScrollableFrame(
            main_frame,
            fg_color=COLORS["bg_dark"],
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["text_muted"],
        )
        self._results_frame.grid(row=1, column=0, padx=16, pady=(8, 16), sticky="nsew")
        self._results_frame.grid_columnconfigure(0, weight=1)

        # ── Empty state
        self._empty_label = ctk.CTkLabel(
            self._results_frame,
            text="No results yet.\nConfigure your search and click START SCAN.",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_muted"],
            justify="center",
        )
        self._empty_label.grid(row=0, column=0, pady=120)

    # ── Actions ───────────────────────────────────────────────────────────

    def _on_start_stop(self) -> None:
        if self._is_scanning:
            self._stop_scan()
        else:
            self._start_scan()

    def _start_scan(self) -> None:
        # Validate inputs
        expression: str = self._keywords_entry.get().strip()
        if not expression:
            self._status_label.configure(text="⚠ Wpisz wyrażenie filtrujące!", text_color=COLORS["warning"])
            return

        # Validate the expression syntax
        test_filter = KeywordFilter(expression)
        if not test_filter.is_valid():
            error_msg = test_filter.get_error() or "Błąd składni"
            self._status_label.configure(
                text=f"⚠ {error_msg[:40]}...",
                text_color=COLORS["warning"]
            )
            return

        platforms: list[str] = []
        if self._chk_allegro_var.get():
            platforms.append("Allegro")
        if self._chk_olx_var.get():
            platforms.append("OLX")
        if self._chk_vinted_var.get():
            platforms.append("Vinted")

        if not platforms:
            self._status_label.configure(text="⚠ Wybierz co najmniej jedną platformę!", text_color=COLORS["warning"])
            return

        # Parse prices
        price_min: Optional[float] = None
        price_max: Optional[float] = None
        try:
            min_text: str = self._price_min_entry.get().strip()
            if min_text:
                price_min = float(min_text)
        except ValueError:
            self._status_label.configure(text="⚠ Nieprawidłowa cena minimalna!", text_color=COLORS["warning"])
            return
        try:
            max_text: str = self._price_max_entry.get().strip()
            if max_text:
                price_max = float(max_text)
        except ValueError:
            self._status_label.configure(text="⚠ Nieprawidłowa cena maksymalna!", text_color=COLORS["warning"])
            return

        # Build config with keyword expression
        config = ScrapeConfig(
            platforms=platforms,
            keyword_expression=expression,
            price_min=price_min,
            price_max=price_max,
        )

        # Reset state
        self._cancel_event.clear()
        self._result_queue = queue.Queue()
        self._is_scanning = True
        self._start_btn.configure(text="■   STOP SCAN", fg_color=COLORS["danger"], hover_color="#ff4040")
        self._status_label.configure(text="Initializing...", text_color=COLORS["accent"])

        # Launch scraper thread
        manager = ScraperManager(
            config=config,
            result_queue=self._result_queue,
            cancel_event=self._cancel_event,
            on_status=self._thread_safe_status,
            on_done=self._thread_safe_done,
        )
        thread = threading.Thread(target=manager.run, daemon=True)
        thread.start()

        # Start polling
        self._poll_results()

    def _stop_scan(self) -> None:
        self._cancel_event.set()
        self._is_scanning = False
        self._start_btn.configure(text="▶   START SCAN", fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])
        self._status_label.configure(text="Scan stopped.", text_color=COLORS["warning"])

    def _thread_safe_status(self, msg: str) -> None:
        """Called from the scraper thread — schedules GUI update."""
        self.after(0, lambda: self._status_label.configure(text=msg, text_color=COLORS["accent"]))

    def _thread_safe_done(self, summary: str) -> None:
        """Called from the scraper thread when all platforms are done."""
        def _update() -> None:
            self._is_scanning = False
            self._start_btn.configure(
                text="▶   START SCAN",
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
            )
            # Determine color based on whether there were any errors
            color: str = COLORS["success"] if "⚠" not in summary else COLORS["warning"]
            self._status_label.configure(text=summary, text_color=color)

        self.after(0, _update)

    def _poll_results(self) -> None:
        """Drain the result queue and add cards to the scrollable frame."""
        try:
            while True:
                result: ScrapeResult = self._result_queue.get_nowait()
                self._add_result_card(result)
        except queue.Empty:
            pass

        if self._is_scanning:
            self.after(self.POLL_INTERVAL_MS, self._poll_results)

    def _add_result_card(self, result: ScrapeResult) -> None:
        """Add a new result card to the results panel."""
        # Hide empty-state label
        if self._empty_label.winfo_ismapped():
            self._empty_label.grid_forget()

        # Store result for AI analysis
        self._all_results.append(result)

        card = ResultCard(self._results_frame, result)
        card.grid(
            row=len(self._result_cards),
            column=0,
            padx=8,
            pady=(0, 8),
            sticky="ew",
        )
        self._result_cards.append(card)
        self._result_count += 1
        self._results_counter.configure(text=f"{self._result_count} items found")

    def _clear_results(self) -> None:
        """Remove all result cards from the results panel."""
        for card in self._result_cards:
            card.destroy()
        self._result_cards.clear()
        self._all_results.clear()  # Clear AI analysis data
        self._analysis_results.clear()
        self._result_count = 0
        self._results_counter.configure(text="0 items found")
        self._empty_label.grid(row=0, column=0, pady=120)
        self._status_label.configure(text="Ready", text_color=COLORS["text_muted"])

    def _show_options_dialog(self) -> None:
        """Show options dialog for AI API key configuration."""
        popup = ctk.CTkToplevel(self)
        popup.title("⚙ Opcje")
        popup.geometry("500x520")
        popup.configure(fg_color=COLORS["bg_dark"])
        popup.transient(self)
        popup.grab_set()
        popup.resizable(False, False)

        # Header
        header = ctk.CTkLabel(
            popup,
            text="⚙ Ustawienia AI",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=COLORS["text_primary"],
        )
        header.pack(pady=(20, 15))

        # Main content frame - don't expand so buttons stay visible
        content = ctk.CTkFrame(popup, fg_color=COLORS["sidebar_bg"], corner_radius=10)
        content.pack(fill="x", padx=20, pady=(0, 10))

        # AI Provider selection
        provider_label = ctk.CTkLabel(
            content,
            text="Wybierz dostawcę AI:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text_primary"],
        )
        provider_label.pack(pady=(20, 10), padx=20, anchor="w")

        provider_var = ctk.StringVar(value=self._settings.get("ai_provider", "gemini"))

        providers_frame = ctk.CTkFrame(content, fg_color="transparent")
        providers_frame.pack(fill="x", padx=20)

        providers = [
            ("gemini", "✨ Google Gemini (darmowy)"),
            ("openai", "🧠 OpenAI GPT-4"),
            ("anthropic", "🤖 Anthropic Claude"),
        ]

        for value, label in providers:
            rb = ctk.CTkRadioButton(
                providers_frame,
                text=label,
                variable=provider_var,
                value=value,
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_secondary"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
            )
            rb.pack(anchor="w", pady=3)

        # Divider
        divider = ctk.CTkFrame(content, height=1, fg_color=COLORS["border"])
        divider.pack(fill="x", padx=20, pady=15)

        # API Keys section
        keys_label = ctk.CTkLabel(
            content,
            text="Klucze API:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text_primary"],
        )
        keys_label.pack(pady=(5, 10), padx=20, anchor="w")

        # Gemini API Key
        gemini_frame = ctk.CTkFrame(content, fg_color="transparent")
        gemini_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(gemini_frame, text="Gemini:", width=80, anchor="w",
                     text_color=COLORS["text_secondary"]).pack(side="left")
        gemini_entry = ctk.CTkEntry(
            gemini_frame, placeholder_text="Klucz API Gemini",
            fg_color=COLORS["card_bg"], border_color=COLORS["border"],
            show="*", width=300
        )
        gemini_entry.pack(side="left", fill="x", expand=True)
        if self._settings.get("gemini_api_key"):
            gemini_entry.insert(0, self._settings["gemini_api_key"])

        # OpenAI API Key
        openai_frame = ctk.CTkFrame(content, fg_color="transparent")
        openai_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(openai_frame, text="OpenAI:", width=80, anchor="w",
                     text_color=COLORS["text_secondary"]).pack(side="left")
        openai_entry = ctk.CTkEntry(
            openai_frame, placeholder_text="Klucz API OpenAI",
            fg_color=COLORS["card_bg"], border_color=COLORS["border"],
            show="*", width=300
        )
        openai_entry.pack(side="left", fill="x", expand=True)
        if self._settings.get("openai_api_key"):
            openai_entry.insert(0, self._settings["openai_api_key"])

        # Anthropic API Key
        anthropic_frame = ctk.CTkFrame(content, fg_color="transparent")
        anthropic_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(anthropic_frame, text="Anthropic:", width=80, anchor="w",
                     text_color=COLORS["text_secondary"]).pack(side="left")
        anthropic_entry = ctk.CTkEntry(
            anthropic_frame, placeholder_text="Klucz API Anthropic",
            fg_color=COLORS["card_bg"], border_color=COLORS["border"],
            show="*", width=300
        )
        anthropic_entry.pack(side="left", fill="x", expand=True)
        if self._settings.get("anthropic_api_key"):
            anthropic_entry.insert(0, self._settings["anthropic_api_key"])

        # Info label
        info_label = ctk.CTkLabel(
            content,
            text="ℹ Gemini: aistudio.google.com/app/apikey (darmowy)",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"],
        )
        info_label.pack(pady=(15, 10), padx=20, anchor="w")

        # Save function
        def save_and_close():
            self._settings["ai_provider"] = provider_var.get()
            self._settings["gemini_api_key"] = gemini_entry.get().strip()
            self._settings["openai_api_key"] = openai_entry.get().strip()
            self._settings["anthropic_api_key"] = anthropic_entry.get().strip()
            self._save_settings()
            self._status_label.configure(text="✅ Ustawienia zapisane", text_color=COLORS["success"])
            popup.destroy()

        # Buttons
        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        save_btn = ctk.CTkButton(
            btn_frame,
            text="💾 Zapisz",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            width=120,
            command=save_and_close,
        )
        save_btn.pack(side="left", padx=(0, 10))

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Anuluj",
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            width=100,
            command=popup.destroy,
        )
        cancel_btn.pack(side="left")

    def _show_ai_analysis(self) -> None:
        """Show AI analysis popup with smart recommendations."""
        if not self._all_results:
            self._status_label.configure(
                text="⚠ Brak wyników do analizy!",
                text_color=COLORS["warning"]
            )
            return

        # Create analysis popup window
        popup = ctk.CTkToplevel(self)
        popup.title("🧠 Analiza AI - Sweet Spot")
        popup.geometry("700x600")
        popup.configure(fg_color=COLORS["bg_dark"])
        popup.transient(self)
        popup.grab_set()

        # Header
        header = ctk.CTkLabel(
            popup,
            text="🧠 Analiza Cena/Jakość",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=COLORS["text_primary"],
        )
        header.pack(pady=(20, 10))

        # Tabs for Smart vs Gemini analysis
        tabview = ctk.CTkTabview(popup, fg_color=COLORS["sidebar_bg"])
        tabview.pack(fill="both", expand=True, padx=20, pady=10)

        # Tab 1: Smart Analysis (local)
        smart_tab = tabview.add("📊 Smart Analyzer")
        self._build_smart_analysis_tab(smart_tab)

        # Tab 2: Gemini AI
        gemini_tab = tabview.add("✨ Gemini AI")
        self._build_gemini_tab(gemini_tab)

        # Close button
        close_btn = ctk.CTkButton(
            popup,
            text="Zamknij",
            width=120,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=popup.destroy,
        )
        close_btn.pack(pady=(0, 20))

    def _build_smart_analysis_tab(self, parent: ctk.CTkFrame) -> None:
        """Build the Smart Analyzer tab content."""
        # Run analysis
        top_results = self._smart_analyzer.get_top_recommendations(self._all_results, top_n=5)

        if not top_results:
            no_data = ctk.CTkLabel(
                parent,
                text="Brak danych do analizy (brak cen)",
                font=ctk.CTkFont(size=14),
                text_color=COLORS["text_muted"],
            )
            no_data.pack(pady=40)
            return

        # Stats header
        prices = [r.price for r in self._all_results if r.price and r.price > 0]
        if prices:
            avg_price = sum(prices) / len(prices)
            min_price = min(prices)
            max_price = max(prices)
            stats_text = f"💰 Zakres cen: {min_price:.0f} - {max_price:.0f} zł  |  Średnia: {avg_price:.0f} zł  |  {len(self._all_results)} ogłoszeń"
            stats_label = ctk.CTkLabel(
                parent,
                text=stats_text,
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_secondary"],
            )
            stats_label.pack(pady=(10, 15))

        # Scrollable results
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=5)

        for i, (result, analysis) in enumerate(top_results):
            # Result frame
            frame = ctk.CTkFrame(scroll, fg_color=COLORS["card_bg"], corner_radius=10)
            frame.pack(fill="x", pady=5, padx=5)

            # Rank badge
            rank_colors = ["#FFD700", "#C0C0C0", "#CD7F32", COLORS["accent"], COLORS["accent"]]
            rank_label = ctk.CTkLabel(
                frame,
                text=f"#{i+1}",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=rank_colors[i] if i < len(rank_colors) else COLORS["text_primary"],
                width=40,
            )
            rank_label.grid(row=0, column=0, rowspan=2, padx=(10, 5), pady=10)

            # Recommendation badge
            rec_label = ctk.CTkLabel(
                frame,
                text=analysis.recommendation,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLORS["text_primary"],
            )
            rec_label.grid(row=0, column=1, sticky="w", padx=5, pady=(10, 2))

            # Title + price
            title_text = f"{result.title[:60]}{'...' if len(result.title) > 60 else ''}  •  {result.price:.0f} zł" if result.price else result.title[:60]
            title_label = ctk.CTkLabel(
                frame,
                text=title_text,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_secondary"],
                anchor="w",
            )
            title_label.grid(row=1, column=1, sticky="w", padx=5, pady=(0, 5))

            # Score + reasoning
            score_text = f"Score: {analysis.score:.0f}/100  |  {analysis.reasoning}"
            score_label = ctk.CTkLabel(
                frame,
                text=score_text,
                font=ctk.CTkFont(size=10),
                text_color=COLORS["text_muted"],
                anchor="w",
            )
            score_label.grid(row=2, column=1, sticky="w", padx=5, pady=(0, 10))

            # Open button
            open_btn = ctk.CTkButton(
                frame,
                text="Otwórz",
                width=60,
                height=28,
                font=ctk.CTkFont(size=11),
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                command=lambda url=result.url: webbrowser.open(url),
            )
            open_btn.grid(row=0, column=2, rowspan=3, padx=10, pady=10)

    def _build_gemini_tab(self, parent: ctk.CTkFrame) -> None:
        """Build the Gemini AI tab content."""
        # API Key input
        key_frame = ctk.CTkFrame(parent, fg_color="transparent")
        key_frame.pack(fill="x", padx=20, pady=(15, 10))

        key_label = ctk.CTkLabel(
            key_frame,
            text="Gemini API Key:",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
        )
        key_label.pack(side="left", padx=(0, 10))

        self._gemini_key_entry = ctk.CTkEntry(
            key_frame,
            placeholder_text="Wklej klucz API z Google AI Studio",
            width=300,
            fg_color=COLORS["card_bg"],
            border_color=COLORS["border"],
            show="*",
        )
        self._gemini_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        # Load saved API key from settings
        saved_key = self._settings.get("gemini_api_key", "")
        if saved_key:
            self._gemini_key_entry.insert(0, saved_key)

        # Info label
        info_label = ctk.CTkLabel(
            parent,
            text="ℹ Darmowy klucz: https://aistudio.google.com/app/apikey",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"],
        )
        info_label.pack(pady=(0, 10))

        # Analyze button
        analyze_btn = ctk.CTkButton(
            parent,
            text="✨ Analizuj z Gemini",
            width=180,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=lambda: self._run_gemini_analysis(parent),
        )
        analyze_btn.pack(pady=10)

        # Results area
        self._gemini_results_frame = ctk.CTkScrollableFrame(
            parent,
            fg_color=COLORS["card_bg"],
            corner_radius=10,
        )
        self._gemini_results_frame.pack(fill="both", expand=True, padx=20, pady=10)

        placeholder = ctk.CTkLabel(
            self._gemini_results_frame,
            text="Kliknij 'Analizuj z Gemini' aby uruchomić analizę AI",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"],
        )
        placeholder.pack(pady=40)

    def _run_gemini_analysis(self, parent: ctk.CTkFrame) -> None:
        """Run Gemini AI analysis in background."""
        api_key = self._gemini_key_entry.get().strip()
        if not api_key:
            self._show_gemini_error("Wprowadź klucz API Gemini")
            return

        self._gemini_api_key = api_key  # Save for later

        # Clear previous results
        for widget in self._gemini_results_frame.winfo_children():
            widget.destroy()

        # Show loading
        loading = ctk.CTkLabel(
            self._gemini_results_frame,
            text="⏳ Analizuję z Gemini AI...",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["accent"],
        )
        loading.pack(pady=40)
        self.update()

        # Run analysis in thread
        def analyze():
            gemini = GeminiAnalyzer(api_key)
            context = self._keywords_entry.get().strip()
            result = gemini.analyze(self._all_results, context)
            self.after(0, lambda: self._show_gemini_result(result))

        thread = threading.Thread(target=analyze, daemon=True)
        thread.start()

    def _show_gemini_result(self, result: Optional[str]) -> None:
        """Display Gemini analysis result."""
        for widget in self._gemini_results_frame.winfo_children():
            widget.destroy()

        if result:
            result_label = ctk.CTkLabel(
                self._gemini_results_frame,
                text=result,
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_primary"],
                anchor="w",
                justify="left",
                wraplength=600,
            )
            result_label.pack(pady=15, padx=15, anchor="w")
        else:
            self._show_gemini_error("Błąd analizy. Sprawdź klucz API.")

    def _show_gemini_error(self, message: str) -> None:
        """Show error in Gemini results frame."""
        for widget in self._gemini_results_frame.winfo_children():
            widget.destroy()

        error_label = ctk.CTkLabel(
            self._gemini_results_frame,
            text=f"⚠ {message}",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["warning"],
        )
        error_label.pack(pady=40)


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = MarketMapApp()
    app.mainloop()


if __name__ == "__main__":
    main()

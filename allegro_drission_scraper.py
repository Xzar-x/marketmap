#!/usr/bin/env python3
"""
Allegro.pl Scraper using DrissionPage (CDP-based)
Advanced anti-bot evasion with human-like behavior simulation.

Features:
- Bezier curve mouse movements
- Human-like typing with Gaussian delays
- Smart scrolling for lazy-loading
- Cookie/RODO popup handling
- Chrome DevTools Protocol (CDP) for undetectable automation

Author: MarketMap Project
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("AllegroScraper")

# DrissionPage imports
try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    from DrissionPage.errors import ElementNotFoundError
    DRISSION_AVAILABLE = True
except ImportError:
    DRISSION_AVAILABLE = False
    logger.warning("DrissionPage not installed. Run: pip install DrissionPage")


# ──────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class AllegroListing:
    """Represents a single Allegro listing."""
    title: str
    price: Optional[float]
    price_text: str
    url: str
    seller: str = ""
    is_promoted: bool = False


@dataclass
class ScrapeResult:
    """Result of a scraping session."""
    success: bool
    listings: List[AllegroListing] = field(default_factory=list)
    error_message: str = ""
    pages_scraped: int = 0


# ──────────────────────────────────────────────────────────────────────────────
# BEZIER CURVE MOUSE MOVEMENT
# ──────────────────────────────────────────────────────────────────────────────

class BezierMouseMover:
    """
    Generates human-like mouse movements using cubic Bezier curves.
    Real humans don't move mice in straight lines - they follow curves.
    """

    @staticmethod
    def _bezier_point(
        t: float,
        p0: Tuple[float, float],
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        p3: Tuple[float, float],
    ) -> Tuple[float, float]:
        """Calculate a point on a cubic Bezier curve at parameter t."""
        # B(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3
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
        """
        Generate random control points for a Bezier curve.
        Control points are offset from the line between start and end.
        """
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.sqrt(dx * dx + dy * dy)

        # Control point offset magnitude (proportional to distance)
        offset_range = max(50, distance * 0.3)

        # First control point - closer to start
        cp1_x = start[0] + dx * random.uniform(0.2, 0.4) + random.uniform(-offset_range, offset_range)
        cp1_y = start[1] + dy * random.uniform(0.2, 0.4) + random.uniform(-offset_range, offset_range)

        # Second control point - closer to end
        cp2_x = start[0] + dx * random.uniform(0.6, 0.8) + random.uniform(-offset_range, offset_range)
        cp2_y = start[1] + dy * random.uniform(0.6, 0.8) + random.uniform(-offset_range, offset_range)

        return ((cp1_x, cp1_y), (cp2_x, cp2_y))

    def generate_path(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        num_points: int = 50,
    ) -> List[Tuple[int, int]]:
        """
        Generate a list of points along a Bezier curve from start to end.
        Returns integer coordinates suitable for mouse movement.
        """
        cp1, cp2 = self._generate_control_points(start, end)

        points: List[Tuple[int, int]] = []
        for i in range(num_points + 1):
            t = i / num_points
            # Add slight noise to make it more human-like
            if 0 < t < 1:
                t += random.gauss(0, 0.01)
                t = max(0, min(1, t))

            point = self._bezier_point(t, start, cp1, cp2, end)
            points.append((int(point[0]), int(point[1])))

        return points


# ──────────────────────────────────────────────────────────────────────────────
# HUMAN-LIKE TYPING
# ──────────────────────────────────────────────────────────────────────────────

class HumanTyper:
    """
    Simulates human-like typing with realistic delays.
    Uses Gaussian distribution for timing variations.
    """

    # Average typing speeds for different character types
    BASE_DELAY_MS: float = 80  # Base delay between keystrokes
    VARIANCE_MS: float = 30  # Standard deviation for Gaussian noise

    # Special delays for specific character types
    SPACE_DELAY_FACTOR: float = 1.2  # Spaces are slightly slower
    SHIFT_DELAY_FACTOR: float = 1.5  # Uppercase letters need shift
    PUNCTUATION_DELAY_FACTOR: float = 1.3  # Punctuation is slower

    # Occasional pauses (simulating thinking)
    PAUSE_PROBABILITY: float = 0.05  # 5% chance of pause
    PAUSE_MIN_MS: float = 200
    PAUSE_MAX_MS: float = 600

    def get_delay_for_char(self, char: str, prev_char: str = "") -> float:
        """Calculate delay before typing a character (in seconds)."""
        # Base delay with Gaussian noise
        delay_ms = random.gauss(self.BASE_DELAY_MS, self.VARIANCE_MS)
        delay_ms = max(20, delay_ms)  # Minimum delay

        # Apply character-specific factors
        if char == " ":
            delay_ms *= self.SPACE_DELAY_FACTOR
        elif char.isupper():
            delay_ms *= self.SHIFT_DELAY_FACTOR
        elif not char.isalnum():
            delay_ms *= self.PUNCTUATION_DELAY_FACTOR

        # Occasional thinking pause
        if random.random() < self.PAUSE_PROBABILITY:
            delay_ms += random.uniform(self.PAUSE_MIN_MS, self.PAUSE_MAX_MS)

        return delay_ms / 1000  # Convert to seconds

    def type_text(self, page: "ChromiumPage", element, text: str) -> None:
        """Type text into an element with human-like delays."""
        logger.debug(f"Typing: '{text}'")

        prev_char = ""
        for char in text:
            delay = self.get_delay_for_char(char, prev_char)
            time.sleep(delay)
            element.input(char, clear=False)
            prev_char = char

        logger.debug("Typing complete")


# ──────────────────────────────────────────────────────────────────────────────
# SMART SCROLLING
# ──────────────────────────────────────────────────────────────────────────────

class SmartScroller:
    """
    Implements human-like scrolling behavior.
    Triggers lazy-loading content on infinite scroll pages.
    """

    # Scroll behavior parameters
    MIN_SCROLL_PX: int = 200
    MAX_SCROLL_PX: int = 600
    MIN_PAUSE_SEC: float = 0.3
    MAX_PAUSE_SEC: float = 1.5

    # Reading simulation - sometimes pause longer
    READING_PAUSE_PROBABILITY: float = 0.15
    READING_PAUSE_MIN_SEC: float = 1.5
    READING_PAUSE_MAX_SEC: float = 4.0

    # Scroll back probability (humans sometimes scroll up)
    SCROLL_BACK_PROBABILITY: float = 0.08
    SCROLL_BACK_AMOUNT: int = 150

    def scroll_page(
        self,
        page: "ChromiumPage",
        scroll_times: int = 5,
        wait_for_content: bool = True,
    ) -> None:
        """
        Scroll the page with human-like behavior.
        Useful for triggering lazy-loading of content.
        """
        logger.info(f"Smart scrolling ({scroll_times} iterations)...")

        for i in range(scroll_times):
            # Random scroll amount
            scroll_amount = random.randint(self.MIN_SCROLL_PX, self.MAX_SCROLL_PX)

            # Occasionally scroll back up slightly (human behavior)
            if random.random() < self.SCROLL_BACK_PROBABILITY and i > 0:
                page.scroll.down(self.SCROLL_BACK_AMOUNT * -1)
                time.sleep(random.uniform(0.2, 0.5))

            # Main scroll
            page.scroll.down(scroll_amount)

            # Wait for content to load
            if wait_for_content:
                time.sleep(random.uniform(self.MIN_PAUSE_SEC, self.MAX_PAUSE_SEC))

            # Occasional reading pause
            if random.random() < self.READING_PAUSE_PROBABILITY:
                pause = random.uniform(self.READING_PAUSE_MIN_SEC, self.READING_PAUSE_MAX_SEC)
                logger.debug(f"Reading pause: {pause:.1f}s")
                time.sleep(pause)

        logger.debug("Scrolling complete")

    def scroll_to_bottom(self, page: "ChromiumPage", max_iterations: int = 20) -> None:
        """Scroll to the bottom of the page, loading all lazy content."""
        logger.info("Scrolling to page bottom...")

        last_height = 0
        same_height_count = 0

        for i in range(max_iterations):
            # Get current scroll height
            current_height = page.run_js("return document.body.scrollHeight")

            if current_height == last_height:
                same_height_count += 1
                if same_height_count >= 3:
                    logger.debug("Reached page bottom")
                    break
            else:
                same_height_count = 0

            last_height = current_height

            # Scroll down
            scroll_amount = random.randint(self.MIN_SCROLL_PX, self.MAX_SCROLL_PX)
            page.scroll.down(scroll_amount)
            time.sleep(random.uniform(0.5, 1.5))


# ──────────────────────────────────────────────────────────────────────────────
# ALLEGRO SCRAPER (DrissionPage CDP)
# ──────────────────────────────────────────────────────────────────────────────

class AllegroDrissionScraper:
    """
    Allegro.pl scraper using DrissionPage with CDP (Chrome DevTools Protocol).
    Implements advanced anti-detection techniques.
    """

    ALLEGRO_URL: str = "https://allegro.pl"
    SEARCH_URL: str = "https://allegro.pl/listing"

    # Selectors
    COOKIE_ACCEPT_SELECTOR: str = "button[data-role='accept-consent']"
    COOKIE_ACCEPT_ALT_SELECTOR: str = "[data-role='accept-consent'], .opbox-cookie-consent button, #opbox-cookie-consent button"
    SEARCH_INPUT_SELECTOR: str = "input[type='search'], input[data-role='search-input'], input[name='string']"
    SEARCH_BUTTON_SELECTOR: str = "button[type='submit'], button[data-role='search-button']"
    LISTING_SELECTOR: str = "article[data-item], div[data-box-name='items'] article, section article"

    def __init__(self, headless: bool = False) -> None:
        """
        Initialize the scraper.

        Args:
            headless: Run browser in headless mode (more detectable)
        """
        if not DRISSION_AVAILABLE:
            raise RuntimeError("DrissionPage is required. Install with: pip install DrissionPage")

        self._headless = headless
        self._page: Optional[ChromiumPage] = None
        self._mouse_mover = BezierMouseMover()
        self._typer = HumanTyper()
        self._scroller = SmartScroller()

        logger.info("AllegroDrissionScraper initialized")

    def _create_browser_options(self) -> ChromiumOptions:
        """Create browser options with anti-detection settings."""
        options = ChromiumOptions()

        # Anti-detection: Use a real user agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        options.set_user_agent(random.choice(user_agents))

        # Anti-detection: Disable automation flags
        options.set_argument("--disable-blink-features=AutomationControlled")
        options.set_argument("--disable-infobars")
        options.set_argument("--disable-dev-shm-usage")
        options.set_argument("--no-sandbox")

        # Realistic window size
        width = random.randint(1280, 1920)
        height = random.randint(800, 1080)
        options.set_argument(f"--window-size={width},{height}")

        # Language
        options.set_argument("--lang=pl-PL")

        # Headless mode (if requested)
        if self._headless:
            options.set_argument("--headless=new")

        # Disable WebRTC leak
        options.set_argument("--disable-webrtc")

        return options

    def _start_browser(self) -> None:
        """Start the browser with anti-detection settings."""
        logger.info("Starting browser...")

        options = self._create_browser_options()
        self._page = ChromiumPage(options)

        # Execute anti-detection JavaScript
        self._inject_anti_detection_js()

        logger.info("Browser started successfully")

    def _inject_anti_detection_js(self) -> None:
        """Inject JavaScript to evade bot detection."""
        if self._page is None:
            return

        # Remove webdriver property
        js_code = """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // Override plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        // Override languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['pl-PL', 'pl', 'en-US', 'en']
        });

        // Override platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });

        // Chrome runtime
        window.chrome = {
            runtime: {}
        };

        // Permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        """

        try:
            self._page.run_js(js_code)
            logger.debug("Anti-detection JS injected")
        except Exception as e:
            logger.warning(f"Failed to inject anti-detection JS: {e}")

    def _human_delay(self, min_sec: float = 0.5, max_sec: float = 2.0) -> None:
        """Add a human-like random delay."""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def _move_mouse_to_element(self, element) -> None:
        """Move mouse to an element using Bezier curve."""
        if self._page is None:
            return

        try:
            # Get element center position
            rect = element.rect
            target_x = rect.get("x", 0) + rect.get("width", 0) / 2
            target_y = rect.get("y", 0) + rect.get("height", 0) / 2

            # Get current mouse position (approximate)
            viewport = self._page.rect
            current_x = random.randint(0, viewport.get("width", 1920))
            current_y = random.randint(0, viewport.get("height", 1080))

            # Generate Bezier path
            path = self._mouse_mover.generate_path(
                (current_x, current_y),
                (target_x, target_y),
                num_points=random.randint(30, 50),
            )

            # Move along the path
            for x, y in path:
                self._page.run_js(f"window.scrollTo({x}, {y})")
                time.sleep(random.uniform(0.005, 0.015))

            # Small final adjustment
            element.hover()

        except Exception as e:
            logger.debug(f"Mouse move failed, using direct hover: {e}")
            element.hover()

    def _handle_cookie_popup(self) -> bool:
        """Handle the RODO/cookie consent popup."""
        logger.info("Checking for cookie popup...")

        try:
            # Wait a moment for popup to appear
            self._human_delay(1.0, 2.0)

            # Try multiple selectors
            selectors = [
                self.COOKIE_ACCEPT_SELECTOR,
                self.COOKIE_ACCEPT_ALT_SELECTOR,
                "button:contains('Akceptuję')",
                "button:contains('Zgadzam się')",
                "button:contains('OK')",
                "[class*='cookie'] button",
                "[class*='consent'] button",
            ]

            for selector in selectors:
                try:
                    button = self._page.ele(selector, timeout=2)
                    if button:
                        logger.info(f"Found cookie button with selector: {selector}")
                        self._move_mouse_to_element(button)
                        self._human_delay(0.3, 0.8)
                        button.click()
                        logger.info("Cookie popup accepted")
                        self._human_delay(0.5, 1.0)
                        return True
                except:
                    continue

            logger.info("No cookie popup found (or already accepted)")
            return False

        except Exception as e:
            logger.warning(f"Error handling cookie popup: {e}")
            return False

    def _perform_search(self, query: str) -> bool:
        """Perform a search on Allegro."""
        logger.info(f"Searching for: '{query}'")

        try:
            # Find search input
            search_input = None
            selectors = [
                self.SEARCH_INPUT_SELECTOR,
                "input[type='search']",
                "input[placeholder*='szukaj']",
                "input[placeholder*='Szukaj']",
                "#search-input",
            ]

            for selector in selectors:
                try:
                    search_input = self._page.ele(selector, timeout=3)
                    if search_input:
                        logger.debug(f"Found search input with: {selector}")
                        break
                except:
                    continue

            if not search_input:
                logger.error("Search input not found")
                return False

            # Move to search input and click
            self._move_mouse_to_element(search_input)
            self._human_delay(0.2, 0.5)
            search_input.click()
            self._human_delay(0.3, 0.6)

            # Clear any existing text
            search_input.clear()
            self._human_delay(0.2, 0.4)

            # Type the query with human-like delays
            self._typer.type_text(self._page, search_input, query)
            self._human_delay(0.5, 1.0)

            # Find and click search button or press Enter
            try:
                search_btn = self._page.ele(self.SEARCH_BUTTON_SELECTOR, timeout=2)
                if search_btn:
                    self._move_mouse_to_element(search_btn)
                    self._human_delay(0.2, 0.5)
                    search_btn.click()
            except:
                # Press Enter instead
                search_input.input("\n", clear=False)

            logger.info("Search submitted")
            self._human_delay(2.0, 4.0)  # Wait for results to load

            return True

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return False

    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from text like '1 299,50 zł'."""
        if not price_text:
            return None

        import re
        cleaned = price_text.replace("\xa0", "").replace(" ", "").replace(",", ".")
        match = re.search(r"(\d+\.?\d*)", cleaned)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def _extract_listings(self) -> List[AllegroListing]:
        """Extract listing data from the current page."""
        logger.info("Extracting listings...")

        listings: List[AllegroListing] = []

        try:
            # Scroll to load lazy content
            self._scroller.scroll_page(self._page, scroll_times=3)

            # Find all listing articles
            selectors = [
                "article[data-item]",
                "div[data-box-name='items'] article",
                "section[data-box-name='items'] article",
                "article",
            ]

            articles = []
            for selector in selectors:
                try:
                    found = self._page.eles(selector)
                    if found and len(found) > 0:
                        articles = found
                        logger.debug(f"Found {len(articles)} articles with: {selector}")
                        break
                except:
                    continue

            if not articles:
                logger.warning("No listing articles found")
                return listings

            for article in articles:
                try:
                    # Extract title
                    title_elem = article.ele("h2") or article.ele("h3") or article.ele("[class*='title']")
                    title = title_elem.text.strip() if title_elem else ""

                    if not title:
                        continue

                    # Extract price
                    price_elem = article.ele("[class*='price']") or article.ele("span[class*='price']")
                    price_text = price_elem.text.strip() if price_elem else ""
                    price = self._parse_price(price_text)

                    # Extract URL
                    link_elem = article.ele("a[href*='/oferta/']") or article.ele("a")
                    url = link_elem.attr("href") if link_elem else ""
                    if url and not url.startswith("http"):
                        url = f"https://allegro.pl{url}"

                    # Check if promoted
                    is_promoted = bool(article.ele("[class*='promoted']") or article.ele("[class*='sponsorowany']"))

                    listing = AllegroListing(
                        title=title,
                        price=price,
                        price_text=price_text,
                        url=url,
                        is_promoted=is_promoted,
                    )
                    listings.append(listing)

                except Exception as e:
                    logger.debug(f"Error parsing article: {e}")
                    continue

            logger.info(f"Extracted {len(listings)} listings")

        except Exception as e:
            logger.error(f"Error extracting listings: {e}")

        return listings

    def search(self, query: str, max_pages: int = 1) -> ScrapeResult:
        """
        Perform a search on Allegro and return results.

        Args:
            query: Search query string
            max_pages: Maximum number of pages to scrape

        Returns:
            ScrapeResult with listings
        """
        logger.info(f"Starting Allegro search: '{query}'")

        result = ScrapeResult(success=False)

        try:
            # Start browser if not already running
            if self._page is None:
                self._start_browser()

            # Navigate to Allegro
            logger.info(f"Navigating to {self.ALLEGRO_URL}")
            self._page.get(self.ALLEGRO_URL)
            self._human_delay(2.0, 4.0)

            # Handle cookie popup
            self._handle_cookie_popup()

            # Perform search
            if not self._perform_search(query):
                result.error_message = "Search failed"
                return result

            # Wait for results
            self._human_delay(2.0, 3.0)

            # Extract listings from each page
            all_listings: List[AllegroListing] = []
            pages_scraped = 0

            for page_num in range(max_pages):
                logger.info(f"Scraping page {page_num + 1}/{max_pages}")

                # Extract listings
                page_listings = self._extract_listings()
                all_listings.extend(page_listings)
                pages_scraped += 1

                if page_num < max_pages - 1:
                    # Try to go to next page
                    try:
                        next_btn = self._page.ele("a[rel='next']") or self._page.ele("[class*='pagination'] a:last-child")
                        if next_btn:
                            self._move_mouse_to_element(next_btn)
                            self._human_delay(0.3, 0.8)
                            next_btn.click()
                            self._human_delay(2.0, 4.0)
                        else:
                            logger.info("No more pages available")
                            break
                    except:
                        logger.info("Could not navigate to next page")
                        break

            result.success = True
            result.listings = all_listings
            result.pages_scraped = pages_scraped

            logger.info(f"Search complete: {len(all_listings)} listings from {pages_scraped} pages")

        except Exception as e:
            logger.error(f"Search error: {e}")
            result.error_message = str(e)

        return result

    def close(self) -> None:
        """Close the browser."""
        if self._page:
            try:
                self._page.quit()
                logger.info("Browser closed")
            except:
                pass
            self._page = None

    def __enter__(self) -> "AllegroDrissionScraper":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ──────────────────────────────────────────────────────────────────────────────
# MAIN / DEMO
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Demo: Search Allegro for laptops."""
    print("=" * 60)
    print("Allegro DrissionPage Scraper Demo")
    print("=" * 60)

    query = "Laptop Dell"

    with AllegroDrissionScraper(headless=False) as scraper:
        result = scraper.search(query, max_pages=1)

        if result.success:
            print(f"\n✅ Znaleziono {len(result.listings)} ofert:\n")
            for i, listing in enumerate(result.listings[:10], 1):
                price_str = f"{listing.price:.2f} zł" if listing.price else "brak ceny"
                promoted = " [PROMOWANE]" if listing.is_promoted else ""
                print(f"{i}. {listing.title[:60]}...")
                print(f"   💰 {price_str}{promoted}")
                print(f"   🔗 {listing.url[:80]}...")
                print()
        else:
            print(f"\n❌ Błąd: {result.error_message}")


if __name__ == "__main__":
    main()

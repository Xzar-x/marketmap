#!/usr/bin/env python3
"""
MarketMap — E-Commerce Scraper GUI
Real-time scraping of Allegro, OLX, and Vinted listings with keyword filtering.
Single-file architecture, ready for PyInstaller compilation.
"""

from __future__ import annotations

import queue
import random
import re
import threading
import time
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

import customtkinter as ctk
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

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
    keywords: list[str]
    logic: str  # "AND" or "OR"
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
# BASE SCRAPER
# ──────────────────────────────────────────────────────────────────────────────

class BaseScraper(ABC):
    """Abstract base for all platform scrapers."""

    PORTAL_NAME: str = ""
    REQUEST_TIMEOUT: int = 15

    def __init__(self) -> None:
        self._ua: UserAgent = UserAgent()

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _fetch(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch a URL and return parsed soup, or None on error."""
        try:
            resp: requests.Response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=self.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as exc:
            print(f"[{self.PORTAL_NAME}] Request error: {exc}")
            return None

    def _random_delay(self) -> None:
        time.sleep(random.uniform(1.0, 3.0))

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

    def __init__(self) -> None:
        super().__init__()
        self._session: requests.Session = requests.Session()

    def _get_headers(self) -> dict[str, str]:
        """Allegro needs realistic browser headers to avoid Cloudflare."""
        return {
            "User-Agent": self._ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Connection": "keep-alive",
        }

    def _fetch_with_session(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch using session for cookie persistence."""
        self._session.headers.update(self._get_headers())
        try:
            # Get cookies from main page first
            self._session.get(
                "https://allegro.pl", timeout=self.REQUEST_TIMEOUT
            )
            self._random_delay()
            self._session.headers["Referer"] = "https://allegro.pl/"
            resp: requests.Response = self._session.get(
                url, timeout=self.REQUEST_TIMEOUT
            )
            # Detect Cloudflare CAPTCHA / JS challenge
            if resp.status_code == 403 or "captcha" in resp.text.lower():
                raise requests.RequestException(
                    "Allegro anti-bot protection (CAPTCHA / Cloudflare). "
                    "Try again later or use a browser."
                )
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as exc:
            print(f"[{self.PORTAL_NAME}] {exc}")
            raise

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

        soup: Optional[BeautifulSoup] = self._fetch_with_session(url)
        if soup is None:
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


# ──────────────────────────────────────────────────────────────────────────────
# OLX SCRAPER
# ──────────────────────────────────────────────────────────────────────────────

class OLXScraper(BaseScraper):
    PORTAL_NAME: str = "OLX"
    MAX_RETRIES: int = 2

    def __init__(self) -> None:
        super().__init__()
        self._session: requests.Session = requests.Session()

    def _fetch_with_session(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch using session for cookie persistence (prevents consent-page issue)."""
        self._session.headers.update(self._get_headers())
        try:
            resp: requests.Response = self._session.get(
                url, timeout=self.REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as exc:
            print(f"[{self.PORTAL_NAME}] Request error: {exc}")
            return None

    def search(
        self,
        keywords: list[str],
        price_min: Optional[float],
        price_max: Optional[float],
        cancel_event: threading.Event,
    ) -> list[ScrapeResult]:
        results: list[ScrapeResult] = []
        query: str = " ".join(kw.strip() for kw in keywords)
        url: str = f"https://www.olx.pl/oferty/q-{query}/"

        params: list[str] = []
        if price_min is not None:
            params.append(f"search[filter_float_price:from]={price_min:.0f}")
        if price_max is not None:
            params.append(f"search[filter_float_price:to]={price_max:.0f}")
        if params:
            url += "?" + "&".join(params)

        if cancel_event.is_set():
            return results

        # Warm up session — visit OLX homepage to get cookies
        self._session.headers.update(self._get_headers())
        try:
            self._session.get(
                "https://www.olx.pl", timeout=self.REQUEST_TIMEOUT
            )
        except requests.RequestException:
            pass  # Non-critical, continue with the search

        self._random_delay()

        # Fetch with retry — OLX sometimes serves empty pages on first hit
        cards: list = []
        soup: Optional[BeautifulSoup] = None
        for attempt in range(1 + self.MAX_RETRIES):
            if cancel_event.is_set():
                return results

            soup = self._fetch_with_session(url)
            if soup is None:
                break

            cards = soup.select("div[data-cy='l-card']")
            if not cards:
                cards = soup.select("div[data-testid='l-card']")

            if cards:
                break  # Got results, no need to retry

            # No cards found — log and retry after delay
            print(f"[{self.PORTAL_NAME}] Attempt {attempt + 1}: 0 cards, retrying...")
            if attempt < self.MAX_RETRIES:
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

    def _get_headers(self) -> dict[str, str]:
        headers: dict[str, str] = super()._get_headers()
        headers["Referer"] = "https://www.vinted.pl/"
        return headers

    def search(
        self,
        keywords: list[str],
        price_min: Optional[float],
        price_max: Optional[float],
        cancel_event: threading.Event,
    ) -> list[ScrapeResult]:
        results: list[ScrapeResult] = []
        query: str = "+".join(kw.strip() for kw in keywords)
        url: str = f"https://www.vinted.pl/catalog?search_text={query}"

        if price_min is not None:
            url += f"&price_from={price_min:.0f}"
        if price_max is not None:
            url += f"&price_to={price_max:.0f}"

        if cancel_event.is_set():
            return results

        soup: Optional[BeautifulSoup] = self._fetch(url)
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
    """Orchestrates scraping across platforms with keyword filtering."""

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

    def _match_keywords(self, title: str) -> list[str]:
        """Return which keywords match in the title, respecting AND/OR logic."""
        title_lower: str = title.lower()
        matched: list[str] = [
            kw for kw in self._config.keywords
            if kw.lower() in title_lower
        ]
        return matched

    def _passes_filter(self, result: ScrapeResult) -> bool:
        """Check if result passes keyword logic and price range."""
        # Keyword filtering
        matched: list[str] = self._match_keywords(result.title)
        result.matched_keywords = matched

        if self._config.logic == "AND":
            if len(matched) != len(self._config.keywords):
                return False
        else:  # OR
            if len(matched) == 0:
                return False

        # Price filtering
        if result.price is not None:
            if self._config.price_min is not None and result.price < self._config.price_min:
                return False
            if self._config.price_max is not None and result.price > self._config.price_max:
                return False

        return True

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
                    keywords=self._config.keywords,
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

        # Platform checkboxes state
        self._chk_allegro_var: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._chk_olx_var: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._chk_vinted_var: ctk.BooleanVar = ctk.BooleanVar(value=True)

        # Logic mode
        self._logic_var: ctk.StringVar = ctk.StringVar(value="OR")

        # Build UI
        self._build_layout()

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

        # ── Section: Keywords
        sec_kw = ctk.CTkLabel(
            sidebar,
            text="KEYWORDS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        sec_kw.grid(row=row, column=0, padx=24, pady=(0, 6), sticky="w")
        row += 1

        self._keywords_entry = ctk.CTkEntry(
            sidebar,
            placeholder_text="e.g. laptop, gaming, RTX",
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["card_bg"],
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
            height=38,
        )
        self._keywords_entry.grid(row=row, column=0, padx=20, sticky="ew")
        row += 1

        # ── Logic switch
        logic_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logic_frame.grid(row=row, column=0, padx=20, pady=(10, 0), sticky="ew")

        logic_label = ctk.CTkLabel(
            logic_frame,
            text="Logic:",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
        )
        logic_label.pack(side="left", padx=(4, 8))

        self._logic_switch = ctk.CTkSegmentedButton(
            logic_frame,
            values=["AND", "OR"],
            variable=self._logic_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["card_bg"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            unselected_color=COLORS["card_bg"],
            unselected_hover_color=COLORS["card_hover"],
            corner_radius=8,
        )
        self._logic_switch.pack(side="left", fill="x", expand=True)
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
        self._status_label.grid(row=row, column=0, padx=24, pady=(10, 20), sticky="w")

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
        clear_btn.grid(row=0, column=2, padx=(8, 0))

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
        keywords_raw: str = self._keywords_entry.get().strip()
        if not keywords_raw:
            self._status_label.configure(text="⚠ Enter at least one keyword!", text_color=COLORS["warning"])
            return

        platforms: list[str] = []
        if self._chk_allegro_var.get():
            platforms.append("Allegro")
        if self._chk_olx_var.get():
            platforms.append("OLX")
        if self._chk_vinted_var.get():
            platforms.append("Vinted")

        if not platforms:
            self._status_label.configure(text="⚠ Select at least one platform!", text_color=COLORS["warning"])
            return

        # Parse keywords
        keywords: list[str] = [kw.strip() for kw in keywords_raw.split(",") if kw.strip()]

        # Parse prices
        price_min: Optional[float] = None
        price_max: Optional[float] = None
        try:
            min_text: str = self._price_min_entry.get().strip()
            if min_text:
                price_min = float(min_text)
        except ValueError:
            self._status_label.configure(text="⚠ Invalid min price!", text_color=COLORS["warning"])
            return
        try:
            max_text: str = self._price_max_entry.get().strip()
            if max_text:
                price_max = float(max_text)
        except ValueError:
            self._status_label.configure(text="⚠ Invalid max price!", text_color=COLORS["warning"])
            return

        # Build config
        config = ScrapeConfig(
            platforms=platforms,
            keywords=keywords,
            logic=self._logic_var.get(),
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
        self._result_count = 0
        self._results_counter.configure(text="0 items found")
        self._empty_label.grid(row=0, column=0, pady=120)
        self._status_label.configure(text="Ready", text_color=COLORS["text_muted"])


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = MarketMapApp()
    app.mainloop()


if __name__ == "__main__":
    main()

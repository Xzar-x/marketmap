# 🗺️ MarketMap — E-Commerce Scanner

> **Desktop GUI application** for real-time scraping of **Allegro**, **OLX**, and **Vinted** listings with keyword filtering, price ranges, and live-feed results.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/CustomTkinter-GUI-1a1f2e?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-6c63ff?style=for-the-badge)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Multi-Platform Scanning** | Search Allegro, OLX, and Vinted simultaneously |
| 🧠 **Smart Keyword Logic** | AND (all keywords must match) or OR (any keyword matches) |
| 💰 **Price Filtering** | Set min/max PLN range to narrow results |
| ⚡ **Live Feed** | Results appear in real-time as they're found |
| 🌙 **Dark Mode UI** | Modern dark interface built with CustomTkinter |
| 🛡️ **Error Resilient** | Handles CAPTCHA, timeouts, and network errors gracefully |
| 📦 **Single-File** | One `.py` file — easy to package as `.exe` |

---

## 🚀 Quick Start

### Prerequisites

- Python **3.10+**

### Installation

```bash
# Clone the repository
git clone https://github.com/Xzar-x/marketmap.git
cd marketmap

# Install dependencies
pip install -r requirements.txt
```

### Run

```bash
python marketmap.py
```

---

## 🖥️ Usage

1. **Select platforms** — Check Allegro, OLX, and/or Vinted
2. **Enter keywords** — Comma-separated (e.g., `laptop, gaming, RTX`)
3. **Choose logic** — `AND` (must contain all) or `OR` (at least one)
4. **Set price range** — Optional min/max in PLN
5. **Click START SCAN** — Results appear in real-time!
6. **Click "Otwórz →"** on any result to open it in your browser

---

## 📦 Build Executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name MarketMap marketmap.py
```

The `.exe` will be in the `dist/` folder.

---

## ⚠️ Disclaimer

This tool is intended for **personal/educational use only**. Web scraping may violate the Terms of Service of some websites. CSS selectors may require updates as websites change their markup. Use responsibly.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

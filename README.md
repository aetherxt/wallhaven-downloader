# wallhaven-downloader

Download wallpapers from [wallhaven.cc](https://wallhaven.cc/) at your screen's resolution using Selenium.

## Setup

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

1. Add wallpaper URLs to `links.txt` (one per line)
2. Activate the virtual environment (see Setup above)
3. Run:

```bash
python3 download.py
```

Downloads land in `downloads/` cropped to 2880×1800.

## Changing dimensions

Edit `WIDTH` and `HEIGHT` at the top of `download.py`:

```python
WIDTH = 2880
HEIGHT = 1800
```

## Requirements

- Python 3.10+
- Chrome browser

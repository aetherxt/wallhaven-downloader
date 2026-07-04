import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

WIDTH = 2880
HEIGHT = 1800
LINKS_FILE = "links.txt"
DOWNLOAD_DIR = "downloads"
DOWNLOAD_TIMEOUT_SECONDS = 180
MAX_WORKERS = 5


def wallpaper_id(url: str) -> str:
    m = re.search(r"/w/([a-z0-9]+)$", url)
    if not m:
        raise ValueError(f"Cannot extract wallpaper ID from {url}")
    return m.group(1)


def read_links(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Links file not found: {path}")

    links = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            links.append(line)

    if not links:
        raise ValueError(f"No links found in {path}")
    return links


def make_driver(download_dir: Path) -> webdriver.Chrome:
    options = Options()
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")

    prefs = {
        "download.default_directory": str(download_dir.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(service=Service(), options=options)

    driver.execute_cdp_cmd(
        "Page.setDownloadBehavior",
        {"behavior": "allow", "downloadPath": str(download_dir.resolve())},
    )
    return driver


def snapshot_downloads(download_dir: Path) -> dict[Path, tuple[int, float]]:
    return {
        path: (path.stat().st_size, path.stat().st_mtime)
        for path in download_dir.iterdir()
        if path.is_file()
    }


def active_downloads(download_dir: Path) -> list[Path]:
    temporary_suffixes = (".crdownload", ".part", ".tmp")
    return [
        path
        for path in download_dir.iterdir()
        if path.is_file() and path.name.endswith(temporary_suffixes)
    ]


def changed_downloads(
    download_dir: Path, before: dict[Path, tuple[int, float]], expected_suffix: str = ""
) -> list[Path]:
    changed = []
    for path in download_dir.iterdir():
        if not path.is_file() or path in active_downloads(download_dir):
            continue
        if expected_suffix and expected_suffix not in path.name:
            continue

        stat = path.stat()
        previous = before.get(path)
        current = (stat.st_size, stat.st_mtime)
        if previous is None or previous != current:
            changed.append(path)
    return changed


def wait_for_download(
    download_dir: Path,
    before: dict[Path, tuple[int, float]],
    expected_suffix: str = "",
) -> Path:
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT_SECONDS
    last_candidate: Path | None = None
    last_size = -1
    stable_since: float | None = None

    while time.monotonic() < deadline:
        if active_downloads(download_dir):
            stable_since = None
            time.sleep(0.5)
            continue

        candidates = changed_downloads(download_dir, before, expected_suffix)
        if candidates:
            candidate = max(candidates, key=lambda path: path.stat().st_mtime)
            size = candidate.stat().st_size
            if candidate == last_candidate and size == last_size:
                if stable_since is None:
                    stable_since = time.monotonic()
                elif time.monotonic() - stable_since >= 1.0:
                    return candidate
            else:
                last_candidate = candidate
                last_size = size
                stable_since = None

        time.sleep(0.5)

    raise TimeoutException("Timed out waiting for the download to finish")


def download_wallpaper(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    url: str,
    download_dir: Path,
    width: int,
    height: int,
    expected_suffix: str,
) -> Path:
    print(f"Opening {url}")
    driver.get(url)

    crop_link = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.showcase-crop")))
    before = snapshot_downloads(download_dir)
    crop_link.click()

    width_input = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#form-respicker-custom-width"))
    )
    height_input = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#form-respicker-custom-height"))
    )

    width_input.clear()
    width_input.send_keys(str(width))
    height_input.clear()
    height_input.send_keys(str(height))

    done_button = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "form#respicker-form button.green.button"))
    )
    done_button.click()

    try:
        continue_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.overlay-submit"))
        )
        continue_button.click()
    except TimeoutException:
        pass

    downloaded = wait_for_download(download_dir, before, expected_suffix)
    print(f"Downloaded {downloaded.name}")
    return downloaded


def download_one(url: str, download_dir: Path) -> tuple[str, Path | None, str | None]:
    driver = None
    try:
        wid = wallpaper_id(url)
        driver = make_driver(download_dir)
        wait = WebDriverWait(driver, 30)
        path = download_wallpaper(driver, wait, url, download_dir, WIDTH, HEIGHT, wid)
        return (url, path, None)
    except Exception as e:
        return (url, None, str(e))
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    download_dir = Path(DOWNLOAD_DIR)
    download_dir.mkdir(parents=True, exist_ok=True)

    links = read_links(Path(LINKS_FILE))
    print(f"Processing {len(links)} wallpaper(s) with {MAX_WORKERS} parallel workers")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_one, url, download_dir) for url in links]

        for future in as_completed(futures):
            url, path, error = future.result()
            if error:
                print(f"Failed {url}: {error}")
            else:
                print(f"Completed {url} -> {path.name}")

    print(f"\nFinished. Downloaded files are in {download_dir.resolve()}")

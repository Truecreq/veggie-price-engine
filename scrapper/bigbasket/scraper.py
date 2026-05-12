# scrapper/bigbasket/scraper.py
from playwright.sync_api import sync_playwright
from lxml import html
import pandas as pd
import os, re, json
from datetime import datetime

BASE_URL        = "https://www.bigbasket.com/cl/fruits-vegetables/?nc=nb&page={}"
QTY_RE          = re.compile(r'\d+(\.\d+)?\s*(kg|g|gm|ml|ltr|l|pcs|pc|pack|nos|pieces|approx)', re.IGNORECASE)
BLOCK_RESOURCES = {"image", "media", "font", "stylesheet", "other"}
ROOT_DIR        = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
GEO_LAT         = 22.5726
GEO_LON         = 88.3639


def clean(v):
    return " ".join(str(v).split()).strip() if v else ""


def make_browser(p):
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1440,900",
            "--lang=en-IN",
        ]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        geolocation={"latitude": GEO_LAT, "longitude": GEO_LON},
        permissions=["geolocation"],
        extra_http_headers={
            "Accept-Language": "en-IN,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
        }
    )
    page = context.new_page()
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-IN','en']});
        window.chrome = {runtime: {}};
    """)
    return browser, context, page


def try_set_location(page, context, pincode):
    print(f"[LOC] Setting location: {pincode}")
    page.wait_for_timeout(3000)
    title = page.title()
    print(f"[LOC] Title: {title}")

    if "access denied" in title.lower() or "denied" in title.lower():
        print("[LOC] Access Denied — waiting and retrying...")
        page.wait_for_timeout(5000)
        page.goto("https://www.bigbasket.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        print(f"[LOC] Retry title: {page.title()}")

    # Try clicking location button
    btn_selectors = [
        "xpath=/html/body/div[2]/div[1]/header[2]/div[1]/div[2]/div[1]/div/div/button",
        "button[class*='location' i]",
        "button:has-text('Select')",
        "div[class*='location' i] button",
        "[data-testid*='location']",
    ]
    for sel in btn_selectors:
        try:
            loc = page.locator(sel).first if not sel.startswith("xpath=") else page.locator(sel)
            loc.wait_for(timeout=7000, state="visible")
            loc.click(force=True)
            print(f"[LOC] Button clicked: {sel}")
            page.wait_for_timeout(2500)
            break
        except Exception:
            continue

    # Find pincode input
    inp = None
    input_selectors = [
        "xpath=/html/body/div[2]/div[1]/header[2]/div[1]/div[2]/div[1]/div[1]/div/div/div[2]/div/input",
        'input[placeholder*="Pincode" i]',
        'input[placeholder*="Enter" i]',
        'input[placeholder*="Search" i]',
        'input[type="text"]',
        'input',
    ]
    for sel in input_selectors:
        try:
            loc = page.locator(sel).first if not sel.startswith("xpath=") else page.locator(sel)
            loc.wait_for(timeout=7000, state="visible")
            inp = loc
            print(f"[LOC] Input found: {sel}")
            break
        except Exception:
            continue

    if inp is None:
        page.screenshot(path=os.path.join(ROOT_DIR, "debug_bb_noinput.png"))
        return False

    inp.click(force=True)
    inp.fill(str(pincode))
    print(f"[LOC] Filled: {pincode}")
    page.wait_for_timeout(3000)

    # Click suggestion
    sug_selectors = [
        "xpath=/html/body/div[2]/div[1]/header[2]/div[1]/div[2]/div[1]/div[1]/div/div/div[3]/div/ul/li[1]",
        "ul li:first-child",
        "ul li",
    ]
    for sel in sug_selectors:
        try:
            loc = page.locator(sel).first if not sel.startswith("xpath=") else page.locator(sel)
            loc.wait_for(timeout=7000, state="visible")
            loc.click(timeout=5000)
            print(f"[LOC] Suggestion clicked: {sel}")
            page.wait_for_timeout(3000)
            return True
        except Exception:
            continue

    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    print("[LOC] Enter pressed as fallback")
    return True


def is_error_page(page):
    c = page.content().lower()
    return any(x in c for x in ["something went wrong", "no products found", "page not found", "access denied"])


def extract_page(source, pincode, page_num):
    parser = html.fromstring(source)
    listings = (
        parser.xpath("//section/section/ul/li") or
        parser.xpath("//ul/li[.//h3]") or
        parser.xpath("//li[.//h3]") or
        parser.xpath("//div[contains(@class,'SKUDeck')]") or
        parser.xpath("//div[contains(@class,'product')]")
    )
    print(f"  [PARSE] Page {page_num} -- {len(listings)} blocks")
    products, skipped = [], 0
    for item in listings:
        all_text = [clean(t) for t in item.xpath(".//text()") if clean(t)]
        full = " ".join(all_text).lower()
        if "out of stock" in full or "notify me" in full:
            skipped += 1
            continue
        raw_name = item.xpath('.//h3/text()')
        name = clean(raw_name[0]) if raw_name else ""
        if not name:
            continue
        raw_qty = item.xpath('.//span[contains(@class,"PackSelector")]/span/text() | .//div[contains(@aria-haspopup,"listbox")]//span/text()')
        quantity = clean(raw_qty[0]) if raw_qty else ""
        if not quantity:
            for t in all_text:
                if QTY_RE.search(t) and "Rs." not in t and "OFF" not in t:
                    quantity = t
                    break
        raw_price = item.xpath('.//span[contains(text(),"\u20b9")]/text()')
        prices = [clean(p) for p in raw_price if clean(p) and "OFF" not in clean(p)]
        if not prices:
            skipped += 1
            continue
        products.append({"Pincode": pincode, "Product Name": name, "Quantity": quantity,
                         "Sale Price": prices[0], "MRP": prices[1] if len(prices) > 1 else prices[0]})
    print(f"  [PARSE] skipped:{skipped} in-stock:{len(products)}")
    return products


def scrape_bigbasket(pincode):
    all_products = []
    print(f"\n[START] BigBasket | pincode={pincode}")

    with sync_playwright() as p:
        browser, context, page = make_browser(p)
        page.route("**/*", lambda route: route.abort()
            if route.request.resource_type in BLOCK_RESOURCES else route.continue_())

        # Load homepage first
        print("[NAV] Loading BigBasket homepage...")
        page.goto("https://www.bigbasket.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        print(f"[NAV] Homepage title: {page.title()}")

        ok = try_set_location(page, context, pincode)
        if not ok:
            print("[LOC] Location set failed — proceeding anyway with cookies")

        # Inject pincode cookies
        context.add_cookies([
            {"name": "bb_pincode",   "value": str(pincode), "domain": ".bigbasket.com", "path": "/"},
            {"name": "pincode",      "value": str(pincode), "domain": ".bigbasket.com", "path": "/"},
            {"name": "user_pincode", "value": str(pincode), "domain": ".bigbasket.com", "path": "/"},
        ])

        page_num = 1
        while True:
            url = BASE_URL.format(page_num)
            print(f"\n[NAV] Page {page_num} -> {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"[NAV] Failed: {e}")
                break
            page.wait_for_timeout(2500)
            title = page.title()
            print(f"[NAV] Title: {title}")
            if is_error_page(page) or "access denied" in title.lower():
                page.screenshot(path=os.path.join(ROOT_DIR, f"debug_bb_p{page_num}.png"))
                print("[NAV] Error/Denied — stopping pagination")
                break
            products = extract_page(page.content(), pincode, page_num)
            if not products:
                page.screenshot(path=os.path.join(ROOT_DIR, f"debug_bb_empty_p{page_num}.png"))
                print("[NAV] No products found — stopping")
                break
            all_products.extend(products)
            print(f"[TOTAL] {len(all_products)}")
            page_num += 1

        browser.close()

    print(f"[DONE] BigBasket total: {len(all_products)}")
    return all_products


def save_files(products, pincode):
    out_dir  = os.path.join(ROOT_DIR, "output")
    os.makedirs(out_dir, exist_ok=True)
    date_str = datetime.now().strftime("%d%m%Y")
    fname    = f"bigbasket_{pincode}_{date_str}"
    df = pd.DataFrame(products)
    df.to_csv( os.path.join(out_dir, f"{fname}.csv"),  index=False, encoding="utf-8-sig")
    df.to_json(os.path.join(out_dir, f"{fname}.json"), orient="records", indent=2, force_ascii=False)
    print(f"  CSV  -> output/{fname}.csv  ({len(df)} rows)")
    print(f"  JSON -> output/{fname}.json ({len(df)} rows)")

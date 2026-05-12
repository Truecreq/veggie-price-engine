# scrapper/bigbasket/scraper.py
from playwright.sync_api import sync_playwright
from lxml import html
import pandas as pd
import os, re, json
from datetime import datetime

LOCATION_BUTTON_XPATH = "/html/body/div[2]/div[1]/header[2]/div[1]/div[2]/div[1]/div/div/button"
PINCODE_INPUT_XPATH   = "/html/body/div[2]/div[1]/header[2]/div[1]/div[2]/div[1]/div[1]/div/div/div[2]/div/input"
FIRST_LOCATION_XPATH  = "/html/body/div[2]/div[1]/header[2]/div[1]/div[2]/div[1]/div[1]/div/div/div[3]/div/ul/li[1]"
ERROR_PAGE_XPATH      = "/html/body/div[2]/div[1]/div/div/p[1]/span"
BASE_URL              = "https://www.bigbasket.com/cl/fruits-vegetables/?nc=nb&page={}"

QTY_RE          = re.compile(r'\d+(\.\d+)?\s*(kg|g|gm|ml|ltr|l|pcs|pc|pack|nos|pieces|approx)', re.IGNORECASE)
BLOCK_RESOURCES = {"image", "media", "font", "stylesheet", "other"}
ROOT_DIR        = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))


def clean(v):
    return " ".join(str(v).split()).strip() if v else ""


def set_location(page, context, pincode):
    print("[LOC] Loading BigBasket homepage...")
    page.goto("https://www.bigbasket.com/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    print(f"[LOC] Page title: {page.title()}")

    try:
        page.locator(f"xpath={LOCATION_BUTTON_XPATH}").click(timeout=15000)
        print("[LOC] Location button clicked!")
    except Exception as e:
        print(f"[LOC] XPATH click failed: {e}")
        try:
            page.get_by_text("Select your location").click(timeout=8000)
        except Exception:
            pass
    page.wait_for_timeout(2000)

    inp = None
    for sel in [
        f"xpath={PINCODE_INPUT_XPATH}",
        'input[placeholder*="Pincode"]',
        'input[placeholder*="pincode"]',
        'input[placeholder*="Enter"]',
        'input[type="text"]',
        'input',
    ]:
        try:
            loc = page.locator(sel).first if not sel.startswith("xpath=") else page.locator(sel)
            loc.wait_for(timeout=6000, state="visible")
            inp = loc
            print(f"[LOC] Input found via: {sel}")
            break
        except Exception:
            continue

    if inp is None:
        page.screenshot(path=os.path.join(ROOT_DIR, "debug_bb_location.png"))
        raise RuntimeError("Pincode input not found on BigBasket")

    inp.click(force=True)
    inp.fill(str(pincode))
    print(f"[LOC] Pincode filled: {pincode}")
    page.wait_for_timeout(2500)

    try:
        page.locator(f"xpath={FIRST_LOCATION_XPATH}").click(timeout=8000)
        print("[LOC] First suggestion clicked!")
    except Exception:
        try:
            page.locator("ul li").first.click(timeout=5000)
        except Exception:
            page.keyboard.press("Enter")
    page.wait_for_timeout(3000)

    cookies = context.cookies()
    storage = page.evaluate(
        "()=>{let d={};for(let i=0;i<localStorage.length;i++){let k=localStorage.key(i);d[k]=localStorage.getItem(k);}return d;}"
    )
    session = {"cookies": cookies, "storage": storage}
    session_path = os.path.join(os.path.dirname(__file__), "session.json")
    with open(session_path, "w") as f:
        json.dump(session, f)
    print(f"[LOC] Session saved — {len(cookies)} cookies")
    return session


def restore_session(page, context, session, pincode):
    try:
        context.add_cookies(session["cookies"])
    except Exception as e:
        print(f"[SES] Cookie restore warning: {e}")
    context.add_cookies([
        {"name": "bb_pincode",   "value": str(pincode), "domain": ".bigbasket.com", "path": "/"},
        {"name": "pincode",      "value": str(pincode), "domain": ".bigbasket.com", "path": "/"},
        {"name": "user_pincode", "value": str(pincode), "domain": ".bigbasket.com", "path": "/"},
    ])
    page.goto("https://www.bigbasket.com/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    for k, v in session.get("storage", {}).items():
        try:
            page.evaluate(f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)})")
        except Exception:
            pass
    print("[SES] Session restored!")


def is_error_page(page):
    try:
        el = page.locator(f"xpath={ERROR_PAGE_XPATH}")
        if el.count() > 0:
            print(f"[STOP] Error: {el.first.inner_text()!r}")
            return True
    except Exception:
        pass
    c = page.content().lower()
    if "something went wrong" in c or "no products found" in c or "page not found" in c:
        print("[STOP] Error text detected.")
        return True
    return False


def extract_page(source, pincode, page_num):
    parser = html.fromstring(source)
    listings = (
        parser.xpath("//section/section/ul/li") or
        parser.xpath("//ul/li[.//h3]")           or
        parser.xpath("//li[.//h3]")               or
        parser.xpath("//div[contains(@class,'SKUDeck')]") or
        parser.xpath("//div[contains(@class,'product')]")
    )
    print(f"  [PARSE] Page {page_num} — {len(listings)} blocks found")

    products, skipped = [], 0
    for item in listings:
        all_text = [clean(t) for t in item.xpath(".//text()") if clean(t)]
        full     = " ".join(all_text).lower()

        if "out of stock" in full or "notify me" in full:
            skipped += 1
            continue

        raw_name = item.xpath('.//h3/text()')
        name     = clean(raw_name[0]) if raw_name else ""
        if not name:
            continue

        raw_qty = item.xpath(
            './/span[contains(@class,"PackSelector")]/span/text() | '
            './/div[contains(@aria-haspopup,"listbox")]//span/text()'
        )
        quantity = clean(raw_qty[0]) if raw_qty else ""
        if not quantity:
            for t in all_text:
                if QTY_RE.search(t) and "\u20b9" not in t and "OFF" not in t:
                    quantity = t
                    break

        raw_price = item.xpath('.//span[contains(text(),"\u20b9")]/text()')
        prices    = [clean(p) for p in raw_price if clean(p) and "OFF" not in clean(p)]
        if not prices:
            skipped += 1
            continue

        products.append({
            "Pincode":      pincode,
            "Product Name": name,
            "Quantity":     quantity,
            "Sale Price":   prices[0],
            "MRP":          prices[1] if len(prices) > 1 else prices[0],
        })

    print(f"  [PARSE] skipped:{skipped} in-stock:{len(products)}")
    return products


def scrape_bigbasket(pincode):
    all_products = []
    print(f"\n[START] BigBasket scraper | pincode={pincode}")

    with sync_playwright() as p:
        print("[BROWSER] Launching headless Chromium...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1400,900",
            ]
        )
        print("[BROWSER] ✅ Launched!")

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            geolocation={"latitude": 28.8386, "longitude": 77.5011},
            permissions=["geolocation"],
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in BLOCK_RESOURCES
            else route.continue_()
        )

        session_file = os.path.join(os.path.dirname(__file__), "session.json")
        if os.path.exists(session_file):
            print("[SES] Found existing session — restoring...")
            with open(session_file) as f:
                session = json.load(f)
            restore_session(page, context, session, pincode)
        else:
            print("[SES] No session — setting location fresh...")
            session = set_location(page, context, pincode)
            restore_session(page, context, session, pincode)

        page_num = 1
        while True:
            url = BASE_URL.format(page_num)
            print(f"\n[NAV] Page {page_num} -> {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"[NAV] ❌ Navigation failed: {e}")
                break
            page.wait_for_timeout(2000)
            print(f"[NAV] Title: {page.title()}")

            if is_error_page(page):
                break

            products = extract_page(page.content(), pincode, page_num)
            if not products:
                page.screenshot(path=os.path.join(ROOT_DIR, f"debug_bb_page{page_num}.png"))
                break

            all_products.extend(products)
            print(f"[TOTAL] {len(all_products)}")
            page_num += 1

        browser.close()
        print("[BROWSER] Closed.")

    print(f"\n[DONE] Total products: {len(all_products)}")
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

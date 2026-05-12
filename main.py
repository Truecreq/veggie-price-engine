# main.py — master runner, runs from project root
import os, sys, traceback
from datetime import datetime

print("=" * 60)
print("   Veggie Price Engine — Master Runner")
print(f"   {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
print("=" * 60)

results = {}

# ── Blinkit ──────────────────────────────────────────────────
print("\n[1/2] Starting Blinkit scraper...")
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scrapper", "blinkit"))
    from scrapper.blinkit.scraper import scrape_blinkit, save_files as bl_save
    pincode = os.environ.get("PINCODE", "201206")
    products = scrape_blinkit(pincode)
    results["blinkit"] = len(products)
    if products:
        bl_save(products, pincode)
        print(f"[1/2] ✅ Blinkit done — {len(products)} products")
    else:
        print("[1/2] ⚠️  Blinkit — 0 products found")
except Exception as e:
    print(f"[1/2] ❌ Blinkit FAILED: {e}")
    traceback.print_exc()
    results["blinkit"] = 0

# ── BigBasket ────────────────────────────────────────────────
print("\n[2/2] Starting BigBasket scraper...")
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scrapper", "bigbasket"))
    from scrapper.bigbasket.scraper import scrape_bigbasket, save_files as bb_save
    pincode = os.environ.get("PINCODE", "201206")
    products = scrape_bigbasket(pincode)
    results["bigbasket"] = len(products)
    if products:
        bb_save(products, pincode)
        print(f"[2/2] ✅ BigBasket done — {len(products)} products")
    else:
        print("[2/2] ⚠️  BigBasket — 0 products found")
except Exception as e:
    print(f"[2/2] ❌ BigBasket FAILED: {e}")
    traceback.print_exc()
    results["bigbasket"] = 0

# ── Summary ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("   SUMMARY")
print("=" * 60)
for platform, count in results.items():
    status = "✅" if count > 0 else "⚠️ "
    print(f"   {status}  {platform:<12} → {count} products")
print("=" * 60)
print("   Check output/ folder for CSV and JSON files")
print("=" * 60)

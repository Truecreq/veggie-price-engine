# scrapper/bigbasket/main.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper import scrape_bigbasket, save_files

PINCODE = os.environ.get("PINCODE", "201206")

print("=" * 60)
print("   BigBasket Scraper  [HEADLESS]")
print("=" * 60)
print(f"  Pincode : {PINCODE}")
print("=" * 60)

try:
    products = scrape_bigbasket(PINCODE)
    print(f"\n  Total in-stock products: {len(products)}")
    if products:
        print("\n  Sample (first 5):")
        for p in products[:5]:
            print(f"    {p['Product Name']} | {p['Quantity']} | {p['Sale Price']} | MRP:{p['MRP']}")
        print()
        save_files(products, PINCODE)
    else:
        print("\n  ⚠️  No products found.")
except Exception as e:
    print(f"\n  ❌ FATAL ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\nDone!")
print("=" * 60)

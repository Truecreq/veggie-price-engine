# main.py -- master runner
import os, sys, traceback
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scrapper', 'blinkit'))
sys.path.insert(0, os.path.join(ROOT, 'scrapper', 'bigbasket'))
os.environ['PYTHONPATH'] = ROOT

print('=' * 60)
print('   Veggie Price Engine -- Master Runner')
print('   ' + datetime.now().strftime('%d-%m-%Y %H:%M:%S'))
print('=' * 60)

os.makedirs(os.path.join(ROOT, 'output'), exist_ok=True)

results = {}
PINCODE = os.environ.get('PINCODE', '700110')
print(f'   Pincode : {PINCODE}')
print('=' * 60)

# -- Blinkit --
print('\n[1/2] Starting Blinkit scraper...')
try:
    from scrapper.blinkit.scraper import scrape_blinkit, save_files as bl_save
    products = scrape_blinkit(PINCODE)
    results['blinkit'] = len(products)
    if products:
        bl_save(products, PINCODE)
        print(f'[1/2] Blinkit done -- {len(products)} products')
    else:
        print('[1/2] Blinkit -- 0 products found')
except Exception as e:
    print(f'[1/2] Blinkit FAILED: {e}')
    traceback.print_exc()
    results['blinkit'] = 0

# -- BigBasket --
print('\n[2/2] Starting BigBasket scraper...')
try:
    from scrapper.bigbasket.scraper import scrape_bigbasket, save_files as bb_save
    products = scrape_bigbasket(PINCODE)
    results['bigbasket'] = len(products)
    if products:
        bb_save(products, PINCODE)
        print(f'[2/2] BigBasket done -- {len(products)} products')
    else:
        print('[2/2] BigBasket -- 0 products found')
except Exception as e:
    print(f'[2/2] BigBasket FAILED: {e}')
    traceback.print_exc()
    results['bigbasket'] = 0

# -- Summary --
print('\n' + '=' * 60)
print('   SUMMARY')
print('=' * 60)
for platform, count in results.items():
    status = 'OK  ' if count > 0 else 'WARN'
    print(f'   [{status}]  {platform:<12} -> {count} products')
print('=' * 60)

import requests
from config.settings import settings

# Step 1: see raw HTML from ZenRows
resp = requests.get('https://api.zenrows.com/v1/', params={
    'apikey': settings.ZENROWS_API_KEY,
    'url': settings.STREETEASY_SEARCH_URL,
    'js_render': 'true',
    'premium_proxy': 'true',
    'antibot': 'true',
}, timeout=60)

print('HTTP status:', resp.status_code)

# Step 2: dump all <a href> tags that mention 'rent' or numbers
from bs4 import BeautifulSoup
soup = BeautifulSoup(resp.text, 'html.parser')

print('--- Sample hrefs ---')
for a in soup.find_all('a', href=True)[:40]:
    print(a['href'])

# Step 3: save full HTML to inspect
with open('/tmp/se_debug.html', 'w') as f:
    f.write(resp.text)
print('Full HTML saved to /tmp/se_debug.html')
"""One-off: download WBIDC header logos into static assets."""
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parents[1] / "src" / "invprom" / "static" / "branding"
OUT.mkdir(parents=True, exist_ok=True)

headers = {"User-Agent": "Mozilla/5.0 InvProm/0.1", "Referer": "https://www.wbidc.com/"}
base = "https://www.wbidc.com"

with httpx.Client(timeout=45, follow_redirects=True, headers=headers) as client:
    html = client.get(base).text
    import re

    imgs = re.findall(r'src=["\']([^"\']+)["\']', html, re.I)
    candidates = [u for u in imgs if any(x in u.lower() for x in ("logo", "emblem", "wbidc", "gov", "banner", "header"))]
    print("candidates", candidates[:20])
    for rel in candidates[:8]:
        url = rel if rel.startswith("http") else base.rstrip("/") + "/" + rel.lstrip("/")
        name = Path(rel.split("?")[0]).name or "asset.bin"
        dest = OUT / name
        try:
            data = client.get(url).content
            dest.write_bytes(data)
            print("saved", dest, len(data))
        except Exception as exc:
            print("skip", url, exc)

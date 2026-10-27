#!/usr/bin/env python3
"""Cloud Hunter pilot: public Meta Ads Library discovery, with honest source counts.

Requires Sonda Imperial's fb_ads_scraper package on PYTHONPATH and Playwright Chromium.
No credentials, proxies, CAPTCHA bypass, or fabricated ad/engagement numbers.
"""
from __future__ import annotations
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "cloud_hunter" / "data"
STORE.mkdir(parents=True, exist_ok=True)
UTC = timezone.utc
NOW = datetime.now(UTC)
EXCLUDED_COUNTRIES = {"KH", "MY", "PH", "TH"}
# Small, controlled pilot; this is NOT a global exhaustive scan.
COUNTRIES = ("US", "GB", "DE", "FR", "BR", "VN", "JP", "AU", "CA", "KR")
SEARCH_TERMS = (
    ("beauty", "hair serum"), ("beauty", "skincare serum"),
    ("health", "neck massager"), ("home", "cleaning brush"),
    ("kitchen", "kitchen gadget"), ("electronics", "phone accessory"),
    ("fashion", "crossbody bag"), ("baby", "baby care product"),
    ("sport", "fitness accessory"), ("auto", "car accessories"),
    ("travel", "travel organizer"), ("garden", "garden tools"),
    ("office", "desk organizer"), ("food", "coffee maker"),
)
PET_RE = re.compile(r"\b(pets?|dogs?|cats?|puppy|puppies|kittens?|pet food|pet accessories|thú cưng|chó mèo|chó|mèo|animaux de compagnie|haustier)\b", re.I)
BULKY_RE = re.compile(r"\b(sofa|couch|mattress|refrigerator|washing machine|wardrobe|full.?size bed|dining table)\b", re.I)
CATEGORIES = {
    "beauty": ("serum", "shampoo", "hair", "skincare", "skin care", "makeup", "beauty", "facial", "dầu gội", "tóc"),
    "health": ("massage", "pain relief", "health", "orthopedic", "posture"),
    "home": ("cleaning", "household", "storage", "vacuum", "laundry"),
    "kitchen": ("kitchen", "cooking", "vegetable cutter", "cookware"),
    "electronics": ("charger", "earbuds", "bluetooth", "phone", "smartwatch", "electronics"),
    "fashion": ("bag", "dress", "wallet", "jewelry", "bracelet", "shoe", "fashion"),
    "baby": ("baby", "toddler", "maternity", "infant"),
    "sport": ("fitness", "yoga", "gym", "workout", "sport"),
    "auto": ("car", "automotive", "motorcycle", "vehicle"),
    "travel": ("travel", "luggage", "camping", "backpack"),
    "garden": ("garden", "gardening", "plant", "tool"),
    "office": ("desk", "office", "stationery", "notebook"),
    "food": ("coffee", "snack", "tea", "food", "drinks"),
}
MAX_STORED_ADS = 1000
WINDOW_DAYS = 35
PLACEHOLDER_RE = re.compile(r"(\{\{|\}\}|product\.name|^shop now$|^buy now$|^learn more$)", re.I)

def classify_name(name):
    """Assign a niche only from product-name evidence, never the query alone."""
    cleaned = identity(name)
    for category, terms in CATEGORIES.items():
        if any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", cleaned, re.I) for term in terms):
            return category
    return "other"


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default

def save(path, payload):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)

def textval(v):
    return v.strip() if isinstance(v, str) else ""

def identity(value):
    value = re.sub(r"https?://\S+", " ", value.lower())
    value = re.sub(r"[^\w\s-]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:110]

def main():
    old = load(STORE / "ads.json", {"ads": []}).get("ads", [])
    by_id = {str(a["ad_id"]): a for a in old if isinstance(a, dict) and a.get("ad_id")}
    cycle = (NOW.date().toordinal() * 4 + NOW.hour // 6)
    attempted = []
    successes = 0
    new_count = 0
    # Cover all countries over many runs; only 4 bounded searches per run.
    from fb_ads_scraper.scraper import AdLibraryScraper
    from fb_ads_scraper.parser import parse_ad
    for offset in range(4):
        index = (cycle * 4 + offset) % (len(SEARCH_TERMS) * len(COUNTRIES))
        term_category, term = SEARCH_TERMS[index % len(SEARCH_TERMS)]
        country = COUNTRIES[(index // len(SEARCH_TERMS)) % len(COUNTRIES)]
        assert country not in EXCLUDED_COUNTRIES
        url = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
               f"&country={country}&q={quote(term)}&search_type=keyword_unordered&media_type=all")
        check = {"country": country, "keyword": term, "category": term_category}
        attempted.append(check)
        try:
            scraper = AdLibraryScraper(url=url, max_results=15, headful=False, timeout=65)
            ads = scraper.run()
            check["found"] = len(ads)
            successes += 1
        except Exception as exc:
            check["error"] = (type(exc).__name__ + ": " + str(exc))[:350]
            continue
        for a in ads:
            aid = str(a.get("ad_archive_id") or "").strip()
            if not aid:
                continue
            title = textval(a.get("ad_title"))
            body = textval(a.get("ad_body"))
            caption = textval(a.get("ad_caption"))
            link = textval(a.get("link_url"))
            page_name = textval(a.get("page_name"))
            words = " ".join((title, body, caption))
            if PET_RE.search(words) or BULKY_RE.search(words):
                continue
            if aid in by_id:
                by_id[aid]["last_seen"] = NOW.isoformat()
                continue
            image = next((i.get("original_url") or i.get("resized_url") for i in (a.get("images") or []) if isinstance(i, dict)), None)
            video = next((v.get("video_hd_url") or v.get("video_sd_url") for v in (a.get("videos") or []) if isinstance(v, dict)), None)
            # Group by exact normalized product-oriented ad title where present.
            # Heuristic, not a verified SKU or proof that differently named ads match.
            product_name = title if len(identity(title)) >= 10 and not PLACEHOLDER_RE.search(title) else textval(a.get("link_description"))
            if len(identity(product_name)) < 10 or PLACEHOLDER_RE.search(product_name):
                product_name = (body.split("\n")[0] if body else "")[:100]
            if len(identity(product_name)) < 10 or PLACEHOLDER_RE.search(product_name):
                product_name = "Unidentified product"
            category = classify_name(product_name)
            key = identity(product_name)
            # Generic ad copy and placeholder names are NOT reliable SKU identities.
            # Do not merge unrelated advertisers merely for matching slogans.
            if category == "other" or product_name == "Unidentified product":
                key = f"unverified-{aid}"
            record = {
                "ad_id": aid, "product_name": product_name[:150], "product_key": key,
                "category": category, "advertiser": page_name, "source_country": country,
                "ad_url": f"https://www.facebook.com/ads/library/?id={quote(aid)}",
                "landing_url": link or None,
                "image_url": image, "video_url": video,
                "first_seen": NOW.isoformat(), "last_seen": NOW.isoformat(),
            }
            by_id[aid] = record
            new_count += 1
    cutoff = NOW - timedelta(days=WINDOW_DAYS)
    recent = [a for a in by_id.values()
              if str(a.get("last_seen", "")) >= cutoff.isoformat()
              and not PET_RE.search(textval(a.get("product_name")))]
    recent.sort(key=lambda a: a.get("last_seen", ""), reverse=True)
    recent = recent[:MAX_STORED_ADS]
    # Correct legacy pilot rows from the first run before producing rankings.
    for ad in recent:
        name = textval(ad.get("product_name"))
        if PLACEHOLDER_RE.search(name):
            name = "Unidentified product"
            ad["product_name"] = name
        ad["category"] = classify_name(name)
        if ad["category"] == "other":
            ad["product_key"] = f"unverified-{ad['ad_id']}"
    group_map = defaultdict(list)
    for ad in recent:
        group_map[(ad["category"], ad["product_key"])].append(ad)
    rankings = {cat: [] for cat in (*CATEGORIES, "other")}
    for (cat, key), ads in group_map.items():
        ad_ids = {a["ad_id"] for a in ads}
        advertisers = {identity(a["advertiser"]) for a in ads if identity(a["advertiser"])}
        newest = max(a["last_seen"] for a in ads)
        rankings.setdefault(cat, []).append({
            "name": ads[0]["product_name"], "group_key": key,
            "ad_count": len(ad_ids), "advertiser_count": len(advertisers),
            "country_count": len({a["source_country"] for a in ads}),
            "last_seen": newest,
            "ads": sorted(ads, key=lambda a: a["last_seen"], reverse=True)[:50],
            "grouping_notice": "Approximate name-based grouping; product identity not independently verified",
        })
    for cat, groups in rankings.items():
        groups.sort(key=lambda g: (-g["ad_count"], -g["advertiser_count"], g["name"]))
        rankings[cat] = groups[:50]
    status = {
        "timestamp_utc": NOW.isoformat(), "attempts": attempted,
        "searches_succeeded": successes, "searches_attempted": len(attempted),
        "new_ads": new_count, "total_unique_ads": len(recent),
        "state": "ok" if successes and (new_count or recent) else ("no_ads" if successes else "scrape_failed"),
        "limitations": "A bounded keyword sample, NOT all Meta ads or verified product sales/views",
    }
    save(STORE / "ads.json", {"updated_at": NOW.isoformat(), "ads": recent})
    save(STORE / "top50.json", {"updated_at": NOW.isoformat(), "lookback_days": WINDOW_DAYS, "categories": rankings})
    save(STORE / "status.json", status)
    print(json.dumps({k: status[k] for k in ("state", "new_ads", "total_unique_ads", "searches_succeeded")}, ensure_ascii=False))
    # Failure state is also persisted for diagnosis.
    return 0 if status["state"] == "ok" else 2

if __name__ == "__main__":
    sys.exit(main())

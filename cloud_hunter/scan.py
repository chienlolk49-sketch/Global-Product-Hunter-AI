#!/usr/bin/env python3
"""Cloud Hunter pilot: public Meta Ads Library discovery, with honest source counts.

Requires Sonda Imperial's fb_ads_scraper package on PYTHONPATH and Playwright Chromium.
No credentials, proxies, CAPTCHA bypass, or fabricated ad/engagement numbers.
"""
from __future__ import annotations
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "cloud_hunter" / "data"
STORE.mkdir(parents=True, exist_ok=True)
UTC = timezone.utc
NOW = datetime.now(UTC)
EXCLUDED_COUNTRIES = {"KH", "MY", "PH", "TH"}
# Small, controlled pilot; this is NOT a global exhaustive scan.
COUNTRIES = (
    "US","GB","DE","FR","BR","VN","JP","AU","CA","KR","IT","ES","PT","NL",
    "BE","AT","CH","SE","NO","DK","FI","PL","CZ","SK","HU","RO","GR",
    "IE","NZ","MX","CO","AR","CL","PE","ZA","NG","KE","EG","MA","AE",
    "SA","TR","IL","IN","PK","BD","LK","ID","SG","TW","HK","CN","KZ",
    "UA","BG","HR","RS","SI","EE","LV","LT","UY","CR"
)
SEARCH_TERMS = (
    ("beauty","hair serum"),("beauty","skincare serum"),("beauty","hair care"),
    ("beauty","shampoo"),("beauty","makeup tools"),("wellness","neck massager"),
    ("wellness","posture support"),("wellness","massage device"),
    ("home","cleaning tool"),("home","home organizer"),("home","storage solution"),
    ("home","vacuum cleaner"),("kitchen","kitchen gadget"),("kitchen","vegetable cutter"),
    ("kitchen","cooking accessory"),("kitchen","coffee maker"),
    ("electronics","phone accessory"),("electronics","wireless charger"),
    ("electronics","smartwatch"),("electronics","bluetooth headphones"),
    ("fashion","crossbody bag"),("fashion","comfortable shoes"),
    ("fashion","jewelry"),("fashion","casual clothing"),
    ("baby","baby care"),("baby","maternity accessory"),("sport","fitness accessory"),
    ("sport","yoga equipment"),("sport","workout bands"),
    ("vehicle","car accessories"),("vehicle","car cleaning"),("vehicle","motorcycle accessory"),
    ("travel","travel organizer"),("travel","luggage accessory"),("travel","camping equipment"),
    ("toys","puzzle game"),("toys","educational toy"),("office","desk organizer"),
    ("office","office supplies"),("garden","garden tool"),("garden","plant accessories"),
    ("food","coffee"),("food","healthy snacks"),("food","tea"),
    ("beauty","duong toc"),("kitchen","dung cu nha bep"),
    ("home","organizador hogar"),("beauty","cuidado cabello")
)
PET_RE = re.compile(r"\b(pets?|dogs?|cats?|puppy|puppies|kittens?|pet food|pet accessories|thú cưng|chó mèo|chó|mèo|animaux de compagnie|haustier)\b", re.I)
BULKY_RE = re.compile(r"\b(sofa|couch|mattress|refrigerator|washing machine|wardrobe|full.?size bed|dining table)\b", re.I)
CATEGORIES = {
    "beauty": ("serum", "shampoo", "hair", "skincare", "skin care", "makeup", "beauty", "facial", "dầu gội", "tóc"),
    "wellness": ("massage", "pain relief", "health", "orthopedic", "posture"),
    "home": ("cleaning", "household", "storage", "vacuum", "laundry"),
    "kitchen": ("kitchen", "cooking", "vegetable cutter", "cookware"),
    "electronics": ("charger", "earbuds", "bluetooth", "phone", "smartwatch", "electronics"),
    "fashion": ("bag", "dress", "wallet", "jewelry", "bracelet", "shoe", "fashion"),
    "baby": ("baby", "toddler", "maternity", "infant"),
    "sport": ("fitness", "yoga", "gym", "workout", "sport"),
    "vehicle": ("car", "automotive", "motorcycle", "vehicle"),
    "travel": ("travel", "luggage", "camping", "backpack"),
    "garden": ("garden", "gardening", "plant", "tool"),
    "toys": ("toy", "puzzle", "craft", "game", "lego"),
    "office": ("desk", "office", "stationery", "notebook"),
    "food": ("coffee", "snack", "tea", "food", "drinks"),
}
MAX_STORED_ADS = 40000  # 50 x 14 niches x 21 distinct IDs = 14,700 minimum
WINDOW_DAYS = 35
ACTIVE_WINDOW_HOURS = 48
MIN_ACTIVE_ADS = 21  # strictly more than 20 distinct active-query ad IDs
SCAN_INTERVAL_MINUTES = 15
MAX_RESULTS_PER_QUERY = 180
MAX_QUERIES_PER_RUN = 12
SCAN_BUDGET_SECONDS = 440
TARGET_PER_CATEGORY = 50
PLACEHOLDER_RE = re.compile(r"(\{\{|\}\}|product\.name|^shop now$|^buy now$|^learn more$)", re.I)
# Marketing benefit claims are not a concrete product identity.
PRODUCT_TYPE_RE = re.compile(r"\b(serum|shampoo|cream|lotion|massager|massage device|cushion|brace|support belt|organizer|storage box|vacuum|cleaner|cutter|blender|coffee maker|charger|headphones|earbuds|smartwatch|watch|phone case|bag|backpack|wallet|shoe|sneaker|jewelry|necklace|bracelet|carrier|stroller|toy|puzzle|game|band|mat|car mount|car holder|scooter mount|luggage|packing cubes|tool|watering can|stationery|notebook|desk|coffee|tea|snack|cards|tracking card|tracking cards)\b",re.I)
TRACKER_RE = re.compile(r"(?:^|\.)(?:track|trk|click|go|affiliate|redirect)\.",re.I)

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

# V9: grouping by product URL and descriptive titles; avoid generic slogan merges.
PRODUCT_PATH_RE = re.compile(r"/(?:products?|items?|dp|p)/([^/?#]+)", re.I)
GENERIC_TERMS = {"sale","offer","discount","shop","now","buy","free","shipping",
                 "new","quality","premium","product","store","official","best"}
def product_identity(ad):
    from urllib.parse import unquote
    aid = str(ad.get("ad_id") or "")
    name = str(ad.get("product_name") or "")
    link = str(ad.get("landing_url") or "")
    slug = ""
    host = ""
    try:
        u = urlsplit(link)
        m = PRODUCT_PATH_RE.search(unquote(u.path))
        if m and u.scheme in ("http","https") and u.hostname:
            slug = identity(re.sub(r"[-_+.]+", " ", unquote(m.group(1))))
            host = u.hostname.lower().removeprefix("www.")
    except ValueError:
        pass
    if slug and (len(slug) < 9 or PLACEHOLDER_RE.search(slug)):
        slug = ""
    if PLACEHOLDER_RE.search(name):
        name = ""
    label = slug or identity(name)
    if not label or len(label) < 10:
        return "unverified:"+aid, "Unidentified product", "other"
    category = "other"
    for cname, phrases in CATEGORIES.items():
        if any(re.search(r"(?<!\w)"+re.escape(t)+r"(?!\w)",label,re.I) for t in phrases):
            category = cname
            break
    tokens = [x for x in identity(slug).split() if len(x)>=3 and x not in GENERIC_TERMS]
    title_tokens = [x for x in identity(name).split() if len(x)>=3 and x not in GENERIC_TERMS]
    if category == "other":
        return "unverified:"+aid,label,"other"
    # Require concrete product type plus an item-specific purchase landing page.
    # Do not count ad slogans or tracking homepages as proven product matches.
    if not PRODUCT_TYPE_RE.search(label):
        return "unverified:"+aid,label,"other"
    if not slug or not link or (urlsplit(link).hostname and TRACKER_RE.search(urlsplit(link).hostname or "")):
        return "unverified:"+aid,label,"other"
    if slug and len(set(tokens))>=3:
        # Keep different retailers and different item paths separate.
        key="item:"+host+":"+slug
    elif slug and len(set(tokens))>=2:
        key="item:"+host+":"+slug
    elif not slug and len(set(title_tokens))>=5:
        key="unverified:"+aid
    else:
        key="unverified:"+aid
    return key,label[:140],category


def main():
    old = load(STORE / "ads.json", {"ads": []}).get("ads", [])
    by_id = {str(a["ad_id"]): a for a in old if isinstance(a, dict) and a.get("ad_id")}
    progress=load(STORE / "scan_progress.json", {"cursor":0,"total_queries_attempted":0})
    # A single logical campaign survives many worker jobs and has no deadline.
    # Each GitHub job must still checkpoint within the host runtime limit.
    campaign_started_at=progress.get("campaign_started_at") or NOW.isoformat()
    cursor=max(0,int(progress.get("cursor",0)))
    started=time.monotonic()
    attempted = []
    successes = 0
    new_count = 0
    # Keep researching incomplete categories across jobs; never mistake job completion for campaign completion.
    from fb_ads_scraper.scraper import AdLibraryScraper
    from fb_ads_scraper.parser import parse_ad
    pending_groups=defaultdict(list)
    for existing_ad in by_id.values():
        if existing_ad.get("is_active_observed") is not True:
            continue
        try:
            check_time=datetime.fromisoformat(str(existing_ad.get("active_checked_at","")).replace("Z","+00:00")).astimezone(UTC)
        except (ValueError,TypeError,OverflowError):
            continue
        if not (NOW-timedelta(hours=ACTIVE_WINDOW_HOURS) <= check_time <= NOW):
            continue
        pkey,pname,pcategory=product_identity(existing_ad)
        if pcategory!="other" and not pkey.startswith("unverified:"):
            pending_groups[(pcategory,pkey,pname)].append(existing_ad.get("ad_id"))
    # Search real high-confidence product URL candidates instead of using an ad slogan.
    # A focused search includes a brand/page or a distinctive part of the item slug.
    candidate_searches=[]
    brand_groups=defaultdict(lambda: {"ids":set(),"countries":set(),"pages":set(),"slug":""})
    for existing_ad in by_id.values():
        if existing_ad.get("is_active_observed") is not True: continue
        try:
            checked=datetime.fromisoformat(str(existing_ad.get("active_checked_at","")).replace("Z","+00:00")).astimezone(UTC)
        except (ValueError,TypeError,OverflowError): continue
        if not NOW-timedelta(hours=ACTIVE_WINDOW_HOURS)<=checked<=NOW: continue
        url=str(existing_ad.get("landing_url") or "")
        try:
            u=urlsplit(url)
            m=PRODUCT_PATH_RE.search(unquote(u.path))
            if not m or not u.hostname or TRACKER_RE.search(u.hostname): continue
            slug=identity(re.sub(r"[-_+.]+"," ",unquote(m.group(1))))
            if len(slug)<9 or PET_RE.search(slug):continue
            k=(u.hostname.lower(),slug)
            group=brand_groups[k]
            group["ids"].add(str(existing_ad["ad_id"]))
            group["slug"]=slug
            group["pages"].add(str(existing_ad.get("advertiser") or ""))
            group["countries"].update(x for x in (existing_ad.get("source_countries") or []) if x)
        except (ValueError,KeyError,TypeError): continue
    for group in brand_groups.values():
        n=len(group["ids"])
        if not 3<=n<MIN_ACTIVE_ADS: continue
        category=classify_name(group["slug"])
        if category=="other": continue
        words=group["slug"].split()
        if len(words)<2: continue
        query=" ".join(words[:7])[:75]
        for country in sorted(group["countries"])[:2]:
            if country not in EXCLUDED_COUNTRIES:
                candidate_searches.append((n,category,query,country))
        for page in sorted(group["pages"]):
            if len(page)>=5 and page.lower() not in ("facebook","shop now"):
                for country in sorted(group["countries"])[:1]:
                    if country not in EXCLUDED_COUNTRIES:
                        candidate_searches.append((n,category,page[:75],country))
    candidate_searches.sort(key=lambda x:(-x[0],x[1],x[2]))
    pending_candidates=candidate_searches[:30]
    for offset in range(MAX_QUERIES_PER_RUN):
        if time.monotonic()-started > SCAN_BUDGET_SECONDS:
            break
        category_order=tuple(CATEGORIES)
        cat_index=cursor % len(category_order)
        term_category=category_order[cat_index]
        terms=[word for niche,word in SEARCH_TERMS if niche==term_category]
        rotation=cursor//len(category_order)
        term=terms[rotation % len(terms)]
        country=COUNTRIES[(rotation*7 + cat_index*13) % len(COUNTRIES)]
        if pending_candidates and offset % 3 == 2:
            number,term_category,focused,candidate_country=pending_candidates[(cursor//3)%len(pending_candidates)]
            term=focused
            country=candidate_country
        cursor+=1
        assert country not in EXCLUDED_COUNTRIES
        url = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
               f"&country={country}&q={quote(term)}&search_type=keyword_unordered&media_type=all")
        check = {"country": country, "keyword": term, "category": term_category}
        attempted.append(check)
        try:
            scraper = AdLibraryScraper(url=url, max_results=MAX_RESULTS_PER_QUERY, headful=False, timeout=55)
            ads = scraper.run()
            check["found"] = len(ads)
            successes += 1
        except Exception as exc:
            check["error"] = (type(exc).__name__ + ": " + str(exc))[:350]
            if any(word in check["error"].lower() for word in ("captcha","checkpoint","rate limit","http 429","login/verifica")):
                break
            continue
        for a in ads:
            # Search is explicitly active_status=active; reject explicitly inactive hits.
            if a.get("is_active") is not True:
                # Unknown is not a confirmation of active status.
                continue
            aid = str(a.get("ad_archive_id") or "").strip()
            if not aid:
                continue
            title = textval(a.get("ad_title"))
            body = textval(a.get("ad_body"))
            caption = textval(a.get("ad_caption"))
            link = textval(a.get("link_url"))
            page_name = textval(a.get("page_name"))
            words = " ".join((title, body, caption, link))
            if PET_RE.search(words) or BULKY_RE.search(words):
                continue
            if aid in by_id:
                old = by_id[aid]
                old["last_seen"] = NOW.isoformat()
                old["active_checked_at"] = NOW.isoformat()
                old["is_active_observed"] = True
                old["source_countries"] = sorted(set(old.get("source_countries") or [old.get("source_country")]) | {country})
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
                "active_checked_at": NOW.isoformat(), "is_active_observed": True,
                "source_countries": [country],
            }
            by_id[aid] = record
            new_count += 1
    cutoff = NOW - timedelta(hours=ACTIVE_WINDOW_HOURS)
    recent = []
    for a in by_id.values():
        if a.get("is_active_observed") is not True:
            continue
        try:
            checked=datetime.fromisoformat(a.get("active_checked_at","").replace("Z","+00:00")).astimezone(UTC)
        except (ValueError,TypeError,OverflowError):
            continue
        if not cutoff <= checked <= NOW:
            continue
        if PET_RE.search(" ".join((str(a.get("product_name") or ""),str(a.get("landing_url") or "")))):
            continue
        recent.append(a)
    recent.sort(key=lambda a:a.get("active_checked_at",""),reverse=True)
    recent=recent[:MAX_STORED_ADS]
    groups=defaultdict(list)
    for ad in recent:
        key,name,category=product_identity(ad)
        ad["product_key"]=key
        ad["product_name"]=name
        ad["category"]=category
        groups[(category,key)].append(ad)
    rankings={cat:[] for cat in (*CATEGORIES,"other")}
    pending_count=0
    for (cat,key),ads in groups.items():
        distinct={a["ad_id"] for a in ads}
        # V9: below 21 active ad IDs is never a Top 50 recommendation.
        if cat=="other" or key.startswith("unverified:") or len(distinct)<MIN_ACTIVE_ADS:
            pending_count+=1
            continue
        advertisers={identity(a.get("advertiser")) for a in ads if identity(a.get("advertiser"))}
        countries=sorted({cc for a in ads for cc in (a.get("source_countries") or [a.get("source_country")]) if cc})
        ads.sort(key=lambda a:a.get("active_checked_at",""),reverse=True)
        rankings.setdefault(cat,[]).append({
            "name":ads[0]["product_name"],"group_key":key,
            "ad_count":len(distinct),"active_ads_observed":len(distinct),
            "advertiser_count":len(advertisers),"countries":countries,
            "last_active_observation":ads[0]["active_checked_at"],
            "ads":ads[:70],
            "verification":"Approximate product identity, never ad-set count or verified sales"
        })
    for cat,items in rankings.items():
        items.sort(key=lambda row:(-row["ad_count"],-row["advertiser_count"],row["name"]))
        rankings[cat]=items[:50]
    status={
        "timestamp_utc":NOW.isoformat(),"attempts":attempted,
        "searches_succeeded":successes,"searches_attempted":len(attempted),
        "new_ads":new_count,"unique_active_ads_observed_last_48h":len(recent),
        "qualifying_products":sum(len(x) for x in rankings.values()),
        "groups_below_threshold_or_unverified":pending_count,
        "threshold_min_unique_active_ad_ids":MIN_ACTIVE_ADS,
        "state":"goal_reached" if all(len(v)>=TARGET_PER_CATEGORY for k,v in rankings.items() if k!="other") else ("progress_incomplete" if successes else "scrape_failed"),
        "goal_completed":all(len(v)>=TARGET_PER_CATEGORY for k,v in rankings.items() if k!="other"),
        "category_qualified_counts":{k:len(v) for k,v in rankings.items() if k!="other"},
        "unfinished_categories":{k:TARGET_PER_CATEGORY-len(v) for k,v in rankings.items() if k!="other" and len(v)<TARGET_PER_CATEGORY},
        "total_queries_attempted_to_date":int(progress.get("total_queries_attempted",0))+len(attempted),
        "campaign_started_at":campaign_started_at,
        "campaign_state":"complete" if all(len(v)>=TARGET_PER_CATEGORY for k,v in rankings.items() if k!="other") else "collecting",
        "campaign_has_time_limit":False,
        "per_job_time_limit_seconds":SCAN_BUDGET_SECONDS,
        "target_per_category":TARGET_PER_CATEGORY,
        "candidates_near_threshold":len(pending_candidates),
        "collection_limit_warning":"180 is a configured ceiling, not confirmed pagination. Source parser may deliver only ~30 per query.",
        "focused_queries_this_run":sum(1 for i in range(len(attempted)) if i%3==2 and bool(pending_candidates)),
        "limitations":"Limited keyword/country samples; >20 observed ACTIVE ad IDs, not Meta ad sets or all products"
    }
    save(STORE / "scan_progress.json",{
        "cursor":cursor,"total_queries_attempted":status["total_queries_attempted_to_date"],
        "campaign_started_at":campaign_started_at,"campaign_state":status["campaign_state"],
        "last_run_at":NOW.isoformat(),"unfinished_categories":status["unfinished_categories"]})
    # Separate incomplete real-product leads from the strictly verified Top 50.
    candidate_groups=defaultdict(dict)
    for ad in recent:
        link=str(ad.get("landing_url") or "")
        try:
            u=urlsplit(link)
            m=PRODUCT_PATH_RE.search(u.path)
            if not (u.scheme in ("https","http") and u.hostname and m):
                continue
            host=u.hostname.lower().removeprefix("www.")
            if TRACKER_RE.search(host):
                continue
            slug=identity(m.group(1).replace("-"," ").replace("_"," "))
            if len(slug)<9 or PET_RE.search(slug) or BULKY_RE.search(slug):
                continue
            candidate_groups[(host,u.path.lower())][str(ad["ad_id"])]=(slug,link,ad)
        except (ValueError,KeyError,TypeError):
            continue
    candidates=[]
    for group in candidate_groups.values():
        if len(group)<2:
            continue
        rows=list(group.values())
        name,link,_=rows[0]
        candidates.append({"name":name,"category":classify_name(name),
            "observed_ad_ids":len(rows),"missing_to_21":max(0,MIN_ACTIVE_ADS-len(rows)),
            "product_url":link,"sample_ad_links":[a["ad_url"] for _,_,a in rows[:5]],
            "verification":"RESEARCH ONLY: URL-level match, not fully verified product identity"})
    candidates.sort(key=lambda x:-x["observed_ad_ids"])
    save(STORE / "candidates.json",{"updated_at":NOW.isoformat(),
        "notice":"Candidates are separate from qualified Top 50; not proof of 21 active ads.",
        "count":len(candidates),"candidates":candidates[:100]})
    save(STORE / "ads.json", {"updated_at": NOW.isoformat(), "ads": recent})
    save(STORE / "top50.json", {"updated_at": NOW.isoformat(), "minimum_active_ads": MIN_ACTIVE_ADS,
                                "active_window_hours": ACTIVE_WINDOW_HOURS, "categories": rankings})
    save(STORE / "status.json", status)
    print(json.dumps({k: status[k] for k in ("state", "new_ads", "unique_active_ads_observed_last_48h", "qualifying_products", "searches_succeeded")}, ensure_ascii=False))
    # Failure state is also persisted for diagnosis.
    return 0 if successes else 2

if __name__ == "__main__":
    sys.exit(main())

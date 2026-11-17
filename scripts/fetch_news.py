#!/usr/bin/env python3
"""Fetch AI, international and national news from free public sources.
Standard library only. Writes data/news.json."""
import json, re, sys, time, html, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "news.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
KEEP_DAYS = 7
MAX_PER_BUCKET = 60

AI_FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("MIT Tech Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
]
INTL_FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Guardian World", "https://www.theguardian.com/world/rss"),
    ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
]
COUNTRIES = {
    "IN": ("India", [("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss"),
                     ("Times of India", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms"),
                     ("Hindustan Times", "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml"),
                     ("NDTV India", "https://feeds.feedburner.com/ndtvnews-india-news")]),
    "US": ("United States", [("NPR National", "https://feeds.npr.org/1003/rss.xml"),
                             ("Guardian US", "https://www.theguardian.com/us-news/rss"),
                             ("ABC News US", "https://abcnews.go.com/abcnews/usheadlines")]),
    "GB": ("United Kingdom", [("BBC UK", "https://feeds.bbci.co.uk/news/uk/rss.xml"),
                              ("Guardian UK", "https://www.theguardian.com/uk-news/rss"),
                              ("Sky News UK", "https://feeds.skynews.com/feeds/rss/uk.xml")]),
    "AU": ("Australia", [("ABC Australia", "https://www.abc.net.au/news/feed/51120/rss.xml"),
                         ("Guardian Australia", "https://www.theguardian.com/australia-news/rss")]),
    "CA": ("Canada", [("CBC Canada", "https://www.cbc.ca/webfeed/rss/rss-canada"),
                      ("Global News", "https://globalnews.ca/canada/feed/")]),
    "PK": ("Pakistan", [("Dawn", "https://www.dawn.com/feeds/home"),
                        ("Express Tribune", "https://tribune.com.pk/feed/pakistan")]),
    "NG": ("Nigeria", [("Punch", "https://punchng.com/feed/"),
                       ("Vanguard", "https://www.vanguardngr.com/feed/")]),
    "ZA": ("South Africa", [("Daily Maverick", "https://www.dailymaverick.co.za/dmrss/"),
                            ("IOL", "https://iol.co.za/rss/iol/news/south-africa")]),
}

def http_get(url, timeout=25, tries=3):
    """GET with retries (handles 429 rate limits, timeouts and transient errors)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, application/json, */*"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410) or i == tries - 1:
                raise
            time.sleep(5 * (i + 1) if e.code == 429 else 2)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2)

def clean(text, limit=None):
    text = re.sub(r"<(script|style)[\s\S]*?</\1>", "", text or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit].rstrip() if limit else text

def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def local(tag):
    return tag.rsplit("}", 1)[-1]

def find_text(node, *names):
    for child in node:
        if local(child.tag) in names and (child.text or "").strip():
            return child.text.strip()
    return ""

def find_image(node, blob):
    for child in node:
        n = local(child.tag)
        if n in ("content", "thumbnail", "enclosure"):
            url = child.get("url") or ""
            typ = child.get("type") or ""
            if url.startswith("http") and (n == "thumbnail" or "image" in typ or re.search(r"\.(jpe?g|png|webp)", url, re.I) or child.get("medium") == "image"):
                return url
    m = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)', blob or "", re.I)
    return m.group(1) if m else ""

def fetch_feed(source, url, cat):
    root = ET.fromstring(http_get(url))
    out = []
    for item in root.iter():
        if local(item.tag) not in ("item", "entry"):
            continue
        title = clean(find_text(item, "title"))
        link = find_text(item, "link")
        if not link:
            for c in item:
                if local(c.tag) == "link" and c.get("href"):
                    link = c.get("href"); break
        raw = find_text(item, "encoded") or find_text(item, "description", "summary", "content")
        date = parse_date(find_text(item, "pubDate", "published", "updated", "date"))
        if not (title and link.startswith("http") and date):
            continue
        out.append({"cat": cat, "source": source, "title": title, "link": link,
                    "summary": clean(find_text(item, "description", "summary") or raw, 220),
                    "image": find_image(item, raw), "published": date.isoformat()})
    return out

def fetch_hn():
    # Algolia has no OR operator, so run one query per keyword and merge.
    since = int(datetime.now(timezone.utc).timestamp()) - KEEP_DAYS * 86400
    seen, out = set(), []
    for kw in ("AI", "LLM", "OpenAI", "Anthropic", "Gemini", "machine learning"):
        url = ("https://hn.algolia.com/api/v1/search_by_date?query=%s&tags=story"
               "&numericFilters=created_at_i>%d,points>10&hitsPerPage=30" % (urllib.parse.quote(kw), since))
        for h in json.loads(http_get(url)).get("hits", []):
            if not (h.get("title") and h.get("url")) or h["objectID"] in seen:
                continue
            seen.add(h["objectID"])
            host = urllib.parse.urlparse(h["url"]).hostname or ""
            out.append({"cat": "ai", "source": "Hacker News", "title": clean(h["title"]), "link": h["url"],
                        "summary": "%s points · %s comments on Hacker News · %s" % (h.get("points", 0), h.get("num_comments", 0), host.removeprefix("www.")),
                        "image": "", "published": h["created_at"].replace("Z", "+00:00")})
    return out

def main():
    jobs = []  # (label, bucket, callable)
    for n, u in AI_FEEDS:   jobs.append((n, "ai", lambda n=n, u=u: fetch_feed(n, u, "ai")))
    jobs.append(("Hacker News", "ai", fetch_hn))
    for n, u in INTL_FEEDS: jobs.append((n, "intl", lambda n=n, u=u: fetch_feed(n, u, "intl")))
    for cc, (_, feeds) in COUNTRIES.items():
        for n, u in feeds:  jobs.append((n, "nat:" + cc, lambda n=n, u=u, cc=cc: fetch_feed(n, u, "nat")))

    def run(job):
        label, bucket, fn = job
        try:
            return label, bucket, fn(), None
        except Exception as e:
            return label, bucket, [], "%s: %s" % (type(e).__name__, e)

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(run, jobs))

    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    buckets, failed = {}, []
    for label, bucket, items, err in results:
        if err:
            failed.append(label); print("FAILED", label, err, file=sys.stderr)
        else:
            print("ok    %-22s %d items" % (label, len(items)))
        buckets.setdefault(bucket, []).extend(items)

    def tidy(items):
        seen, out = set(), []
        for a in sorted(items, key=lambda a: a["published"], reverse=True):
            if datetime.fromisoformat(a["published"]) < cutoff:
                continue
            key = re.sub(r"[^a-z0-9]", "", a["title"].lower())[:60]
            if key in seen:
                continue
            seen.add(key); out.append(a)
        return out[:MAX_PER_BUCKET]

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "failed_sources": failed,
        "countries": {cc: v[0] for cc, v in COUNTRIES.items()},
        "ai": tidy(buckets.get("ai", [])),
        "intl": tidy(buckets.get("intl", [])),
        "national": {cc: tidy(buckets.get("nat:" + cc, [])) for cc in COUNTRIES},
    }
    total = len(data["ai"]) + len(data["intl"]) + sum(len(v) for v in data["national"].values())
    if total < 20:
        print("Too few articles (%d); keeping previous data." % total, file=sys.stderr)
        sys.exit(1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Wrote %s (%d articles)" % (OUT, total))

if __name__ == "__main__":
    main()
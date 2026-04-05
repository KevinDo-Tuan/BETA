"""
News aggregator — 57 sources covering general news, macro-economics,
geopolitics, market psychology, and crypto for options pricing intelligence.

General:      Reuters, The Guardian, Washington Post, New York Times, CNBC,
              MarketWatch, Bloomberg
Market:       WSJ (AMP bypass), The Economist, Financial Times, Yahoo Finance,
              Barron's, Business Insider, S&P Global, CBOE
GDELT:        Market, Macro, Geopolitical, Crypto topic queries (65K+ sources)
Macro:        Federal Reserve, FRED Blog, Zero Hedge, IMF, BIS, ECB, NY Fed,
              World Bank, OECD, FSB, Project Syndicate, VoxEU, Brookings
Geopolitics:  Geopolitical Futures, CFR, Foreign Affairs, RAND,
              Atlantic Council, Stratfor, Crisis Group
Sentiment:    Advisor Perspectives, Seeking Alpha
Crypto:       AInvest, SoSoValue, TradingView, CoinTelegraph, Blockworks,
              crypto.news, The Block, Decrypt, Crypto Briefing, BeInCrypto,
              DL News, Bitcoin Magazine, CryptoNews, Protos, CryptoSlate,
              CoinDesk, Unchained, Messari, Glassnode, The Defiant, Bankless
"""

import sys
import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import json
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOURS = 24
CUTOFF = datetime.now(timezone.utc) - timedelta(hours=HOURS)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NewsAggregator/1.0)"
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_utc(parsed_time) -> datetime | None:
    """Convert a feedparser time struct to an aware UTC datetime."""
    if not parsed_time:
        return None
    try:
        return datetime(*parsed_time[:6], tzinfo=timezone.utc)
    except Exception:
        return None


def is_recent(dt: datetime | None) -> bool:
    if dt is None:
        return True  # include if date unknown
    return dt >= CUTOFF


def article(source: str, title: str, url: str, published: datetime | None, summary: str = "") -> dict:
    return {
        "source": source,
        "title": title.strip(),
        "url": url.strip(),
        "published": published.isoformat() if published else "unknown",
        "summary": summary.strip()[:300],
        "content": "",  # filled by enrich_articles()
    }


# ---------------------------------------------------------------------------
# Reuters  (via Google News RSS — native feeds discontinued Mar 2026)
# ---------------------------------------------------------------------------

REUTERS_FEEDS = [
    "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:12h+site:reuters.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_reuters() -> list[dict]:
    results = []
    seen = set()

    for feed_url in REUTERS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                results.append(article(
                    source="Reuters",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Reuters] Feed error ({feed_url}): {e}")

    # Deduplicate
    seen_titles = set()
    unique = []
    for r in results:
        if r["title"] not in seen_titles:
            seen_titles.add(r["title"])
            unique.append(r)

    print(f"[Reuters] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# The Guardian  (official RSS — no API key required)
# ---------------------------------------------------------------------------

GUARDIAN_FEEDS = [
    ("World",       "https://www.theguardian.com/world/rss"),
    ("UK News",     "https://www.theguardian.com/uk-news/rss"),
    ("US News",     "https://www.theguardian.com/us-news/rss"),
    ("Business",    "https://www.theguardian.com/business/rss"),
    ("Technology",  "https://www.theguardian.com/technology/rss"),
    ("Science",     "https://www.theguardian.com/science/rss"),
    ("Environment", "https://www.theguardian.com/environment/rss"),
    ("Politics",    "https://www.theguardian.com/politics/rss"),
]


def fetch_guardian() -> list[dict]:
    results = []
    seen = set()

    for section, feed_url in GUARDIAN_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                summary = entry.get("summary", "")
                # Guardian summaries are HTML — strip tags
                if summary:
                    summary = BeautifulSoup(summary, "lxml").get_text(" ", strip=True)

                results.append(article(
                    source="The Guardian",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=summary,
                ))
        except Exception as e:
            print(f"[Guardian] Feed error ({section}): {e}")

        time.sleep(0.3)  # polite delay between feed requests

    if not results:
        print("[Guardian] RSS empty — trying sitemap fallback")
        results = _fetch_sitemap("https://www.theguardian.com/sitemaps/news.xml", "The Guardian")
    print(f"[Guardian] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# AInvest  (Vue SPA with auth-gated API — use Google News RSS as source)
# ---------------------------------------------------------------------------

AINVEST_FEEDS = [
    "https://news.google.com/rss/search?q=site:ainvest.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:12h+site:ainvest.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_ainvest() -> list[dict]:
    """
    AInvest's content API requires session auth that isn't replicable without
    a full browser login. Use Google News RSS as a reliable alternative — it
    indexes ainvest.com articles and provides titles, URLs, and publish times.
    """
    results = []
    seen = set()

    for feed_url in AINVEST_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                results.append(article(
                    source="AInvest",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[AInvest] Feed error: {e}")

    # Deduplicate by title
    seen_titles: set = set()
    unique = []
    for r in results:
        if r["title"] not in seen_titles:
            seen_titles.add(r["title"])
            unique.append(r)

    print(f"[AInvest] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Washington Post  (direct feeds 403 — Google News RSS)
# ---------------------------------------------------------------------------

WAPO_FEEDS = [
    "https://news.google.com/rss/search?q=site:washingtonpost.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:washingtonpost.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_wapo() -> list[dict]:
    results = []
    seen: set = set()

    for feed_url in WAPO_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                results.append(article(
                    source="Washington Post",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[WaPo] Feed error: {e}")

    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Washington Post] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# New York Times  (rss.nytimes.com blocked to bots — Google News RSS)
# ---------------------------------------------------------------------------

NYT_FEEDS = [
    "https://news.google.com/rss/search?q=site:nytimes.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:nytimes.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_nyt() -> list[dict]:
    results = []
    seen: set = set()

    for feed_url in NYT_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                results.append(article(
                    source="New York Times",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[NYT] Feed error: {e}")

    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[New York Times] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# SoSoValue  (crypto/DeFi analytics — no RSS, Google News RSS)
# ---------------------------------------------------------------------------

SOSOVALUE_FEEDS = [
    # sosovalue.com blocks scrapers and isn't indexed in Google News as a source.
    # Search by brand name to find news *about* SoSoValue from other outlets.
    "https://news.google.com/rss/search?q=sosovalue+crypto&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=sosovalue+ETF&hl=en-US&gl=US&ceid=US:en",
]


def fetch_sosovalue() -> list[dict]:
    results = []
    seen: set = set()

    for feed_url in SOSOVALUE_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                results.append(article(
                    source="SoSoValue",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[SoSoValue] Feed error: {e}")

    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[SoSoValue] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# TradingView  (direct feed for trading ideas + Google News RSS for news)
# ---------------------------------------------------------------------------

TRADINGVIEW_FEEDS = [
    "https://news.google.com/rss/search?q=site:tradingview.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:tradingview.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_tradingview() -> list[dict]:
    results = []
    seen: set = set()

    for feed_url in TRADINGVIEW_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                results.append(article(
                    source="TradingView",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[TradingView] Feed error: {e}")

    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[TradingView] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Bloomberg  (direct RSS — economics + markets)
# ---------------------------------------------------------------------------

BLOOMBERG_FEEDS = [
    "https://feeds.bloomberg.com/economics/news.rss",
    "https://feeds.bloomberg.com/markets/news.rss",
]


def fetch_bloomberg() -> list[dict]:
    results = []
    seen: set = set()

    for feed_url in BLOOMBERG_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                results.append(article(
                    source="Bloomberg",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Bloomberg] Feed error: {e}")

    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    if not unique:
        print("[Bloomberg] RSS empty — trying sitemap fallback")
        unique = _fetch_sitemap("https://www.bloomberg.com/feeds/sitemap_news.xml", "Bloomberg")
    print(f"[Bloomberg] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Federal Reserve  (official press releases)
# ---------------------------------------------------------------------------

def fetch_fed() -> list[dict]:
    results = []
    seen: set = set()

    try:
        feed = feedparser.parse("https://www.federalreserve.gov/feeds/press_all.xml")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)

            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue

            results.append(article(
                source="Federal Reserve",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Federal Reserve] Feed error: {e}")

    print(f"[Federal Reserve] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# FRED Blog  (St. Louis Fed economic analysis)
# ---------------------------------------------------------------------------

def fetch_fred() -> list[dict]:
    results = []
    seen: set = set()

    try:
        feed = feedparser.parse("https://fredblog.stlouisfed.org/feed/")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)

            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue

            results.append(article(
                source="FRED Blog",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=BeautifulSoup(entry.get("summary", ""), "lxml").get_text(" ", strip=True),
            ))
    except Exception as e:
        print(f"[FRED Blog] Feed error: {e}")

    print(f"[FRED Blog] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# Zero Hedge  (contrarian sentiment / mass psychology)
# ---------------------------------------------------------------------------

def fetch_zerohedge() -> list[dict]:
    results = []
    seen: set = set()

    try:
        feed = feedparser.parse("https://feeds.feedburner.com/zerohedge/feed")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)

            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue

            results.append(article(
                source="Zero Hedge",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Zero Hedge] Feed error: {e}")

    print(f"[Zero Hedge] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# Geopolitical Futures  (wars, sanctions, trade policy)
# ---------------------------------------------------------------------------

def fetch_geopolitical_futures() -> list[dict]:
    results = []
    seen: set = set()

    try:
        feed = feedparser.parse("https://geopoliticalfutures.com/rss/")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)

            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue

            results.append(article(
                source="Geopolitical Futures",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Geopolitical Futures] Feed error: {e}")

    print(f"[Geopolitical Futures] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# CNBC  (bot-blocked directly — Google News RSS fallback)
# ---------------------------------------------------------------------------

CNBC_FEEDS = [
    "https://news.google.com/rss/search?q=site:cnbc.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:cnbc.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_cnbc() -> list[dict]:
    results = []
    seen: set = set()

    for feed_url in CNBC_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                results.append(article(
                    source="CNBC",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[CNBC] Feed error: {e}")

    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    if not unique:
        print("[CNBC] RSS empty — trying sitemap fallback")
        unique = _fetch_sitemap("https://www.cnbc.com/sitemap_news.xml", "CNBC")
    print(f"[CNBC] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# CFR — Council on Foreign Relations  (geopolitics — Google News RSS)
# ---------------------------------------------------------------------------

CFR_FEEDS = [
    "https://news.google.com/rss/search?q=site:cfr.org&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:cfr.org&hl=en-US&gl=US&ceid=US:en",
]


def fetch_cfr() -> list[dict]:
    results = []
    seen: set = set()

    for feed_url in CFR_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                results.append(article(
                    source="CFR",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[CFR] Feed error: {e}")

    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[CFR] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# MarketWatch  (Dow Jones direct feed is stale — Google News RSS)
# ---------------------------------------------------------------------------

MARKETWATCH_FEEDS = [
    "https://news.google.com/rss/search?q=site:marketwatch.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:marketwatch.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_marketwatch() -> list[dict]:
    results = []
    seen: set = set()

    for feed_url in MARKETWATCH_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)

                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue

                results.append(article(
                    source="MarketWatch",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[MarketWatch] Feed error: {e}")

    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[MarketWatch] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# CoinTelegraph
# ---------------------------------------------------------------------------

def fetch_cointelegraph() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse("https://cointelegraph.com/rss")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="CoinTelegraph",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[CoinTelegraph] Feed error: {e}")
    print(f"[CoinTelegraph] Found {len(results)} articles")
    return results



# ---------------------------------------------------------------------------
# crypto.news
# ---------------------------------------------------------------------------

def fetch_cryptonews_site() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse("https://crypto.news/feed/")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="crypto.news",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[crypto.news] Feed error: {e}")
    print(f"[crypto.news] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# The Block
# ---------------------------------------------------------------------------

def fetch_theblock() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse("https://www.theblock.co/rss.xml")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="The Block",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[The Block] Feed error: {e}")
    print(f"[The Block] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# Decrypt
# ---------------------------------------------------------------------------

def fetch_decrypt() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse("https://decrypt.co/feed")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="Decrypt",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Decrypt] Feed error: {e}")
    print(f"[Decrypt] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# Crypto Briefing
# ---------------------------------------------------------------------------

def fetch_crypto_briefing() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse("https://cryptobriefing.com/feed/")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="Crypto Briefing",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Crypto Briefing] Feed error: {e}")
    print(f"[Crypto Briefing] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# BeInCrypto
# ---------------------------------------------------------------------------

def fetch_beincrypto() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse("https://beincrypto.com/feed/")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="BeInCrypto",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[BeInCrypto] Feed error: {e}")
    print(f"[BeInCrypto] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# DL News  (DeFi / on-chain focused)
# ---------------------------------------------------------------------------

DLNEWS_FEEDS = [
    "https://news.google.com/rss/search?q=site:dlnews.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:dlnews.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_dlnews() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in DLNEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="DL News",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[DL News] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[DL News] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Bitcoin Magazine
# ---------------------------------------------------------------------------

def fetch_bitcoin_magazine() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse("https://bitcoinmagazine.com/feed")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="Bitcoin Magazine",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Bitcoin Magazine] Feed error: {e}")
    print(f"[Bitcoin Magazine] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# CryptoNews  (cryptonews.com)
# ---------------------------------------------------------------------------

def fetch_cryptonews() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse("https://cryptonews.com/news/feed/")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="CryptoNews",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[CryptoNews] Feed error: {e}")
    print(f"[CryptoNews] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# Protos  (on-chain / critical analysis)
# ---------------------------------------------------------------------------

def fetch_protos() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse("https://protos.com/feed/")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="Protos",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Protos] Feed error: {e}")
    print(f"[Protos] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# CryptoSlate
# ---------------------------------------------------------------------------

def fetch_cryptoslate() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse("https://cryptoslate.com/feed/")
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="CryptoSlate",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[CryptoSlate] Feed error: {e}")
    print(f"[CryptoSlate] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# CoinDesk  (bot-blocked directly — Google News RSS)
# ---------------------------------------------------------------------------

COINDESK_FEEDS = [
    "https://news.google.com/rss/search?q=site:coindesk.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:coindesk.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_coindesk() -> list[dict]:
    results = []
    seen: set = set()
    for feed_url in COINDESK_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="CoinDesk",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[CoinDesk] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[CoinDesk] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Unchained  (Laura Shin — bot-blocked directly — Google News RSS)
# ---------------------------------------------------------------------------

UNCHAINED_FEEDS = [
    "https://news.google.com/rss/search?q=site:unchainedcrypto.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:unchainedcrypto.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_unchained() -> list[dict]:
    results = []
    seen: set = set()
    for feed_url in UNCHAINED_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen:
                    continue
                seen.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Unchained",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Unchained] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Unchained] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Blockworks (bug fix — function was missing)
# ---------------------------------------------------------------------------

BLOCKWORKS_FEEDS = [
    "https://news.google.com/rss/search?q=site:blockworks.co&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:blockworks.co&hl=en-US&gl=US&ceid=US:en",
]


def fetch_blockworks() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in BLOCKWORKS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Blockworks",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Blockworks] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Blockworks] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Market / Finance
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Paywall bypass helpers
# ---------------------------------------------------------------------------

def _wsj_full_text(url: str) -> str:
    """Fetch WSJ article via AMP endpoint (bypasses paywall, no JS needed).

    Technique from: fuck-paywall/The Wall Street Journal Full Text Articles.user.js
    The AMP version (wsj.com/amp/articles/...) serves the full article without
    the paywall overlay.
    """
    parsed = urlparse(url)
    amp_url = f"https://www.wsj.com/amp{parsed.path}"
    try:
        resp = requests.get(amp_url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; NewsAggregator/1.0)",
            "Referer": "https://www.facebook.com/",
        }, timeout=(3, 5))
        soup = BeautifulSoup(resp.text, "html.parser")
        # AMP access block contains the unlocked article body
        content = soup.find(attrs={"amp-access": "access"})
        if content:
            return content.get_text(separator=" ", strip=True)[:2000]
    except Exception:
        pass
    return ""


def _economist_full_text(url: str) -> str:
    """Fetch Economist article bypassing paywall by blocking tinypass.com.

    Technique from: fuck-paywall/README.md
    The Economist loads all article content first, then calls tinypass.com JS
    to show the paywall. requests never executes JS, so the paywall never fires.
    """
    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; NewsAggregator/1.0)",
            "Referer": "https://www.google.com/",
        }, timeout=(3, 5), cookies={})
        soup = BeautifulSoup(resp.text, "html.parser")
        # Try common Economist article body selectors
        body = (
            soup.find("div", class_="article__body") or
            soup.find("div", attrs={"data-body-id": True}) or
            soup.find("article")
        )
        if body:
            return body.get_text(separator=" ", strip=True)[:2000]
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Sitemap fallback helper
# ---------------------------------------------------------------------------

def _fetch_sitemap(sitemap_url: str, source_name: str) -> list[dict]:
    """Parse a Google News sitemap XML and return recent articles.

    Handles the standard Google News sitemap namespace:
      <url>
        <loc>https://...</loc>
        <news:news>
          <news:publication_date>2026-04-05T...</news:publication_date>
          <news:title>Article Title</news:title>
        </news:news>
      </url>

    Used as a fallback when RSS feeds return 0 articles. Confirmed working for:
      - Bloomberg:  https://www.bloomberg.com/feeds/sitemap_news.xml
      - CNBC:       https://www.cnbc.com/sitemap_news.xml
      - Guardian:   https://www.theguardian.com/sitemaps/news.xml
    """
    def _parse_sitemap_date(s: str):
        if not s:
            return None
        try:
            s = s.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            # Strip milliseconds (.626) before the timezone offset
            if "." in s:
                dot = s.index(".")
                tz = s.index("+", dot) if "+" in s[dot:] else len(s)
                s = s[:dot] + s[tz:]
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    results = []
    try:
        resp = requests.get(sitemap_url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return results
        soup = BeautifulSoup(resp.text, "lxml-xml")
        for url_tag in soup.find_all("url"):
            loc = url_tag.find("loc")
            if not loc:
                continue
            url_str = loc.text.strip()
            # publication_date lives inside <news:news> namespace
            pub_tag = url_tag.find("publication_date")
            published = _parse_sitemap_date(pub_tag.text if pub_tag else "")
            if not is_recent(published):
                continue
            title_tag = url_tag.find("title")
            title = title_tag.text.strip() if title_tag else ""
            if not title:
                continue
            results.append(article(
                source=source_name,
                title=title,
                url=url_str,
                published=published,
                summary="",
            ))
    except Exception as e:
        print(f"[{source_name}] Sitemap error: {e}")
    return results


# ---------------------------------------------------------------------------
# Market / Finance
# ---------------------------------------------------------------------------

WSJ_FEEDS = [
    # Direct Dow Jones feeds (direct wsj.com URLs — AMP bypass works)
    "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
    "https://feeds.content.dowjones.io/public/rss/RSSWorldNews",
    "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
    "https://feeds.content.dowjones.io/public/rss/RSSWSJD",
    # Google News (broader coverage, ~80 recent articles/day)
    "https://news.google.com/rss/search?q=site:wsj.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:wsj.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_wsj() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in WSJ_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                # AMP bypass only works on direct wsj.com URLs (not Google redirect URLs)
                full_text = _wsj_full_text(url) if "wsj.com" in url else ""
                results.append(article(
                    source="WSJ",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=full_text or entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[WSJ] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[WSJ] Found {len(unique)} articles")
    return unique


FT_FEEDS = [
    "https://news.google.com/rss/search?q=site:ft.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:ft.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_ft() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in FT_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Financial Times",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Financial Times] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Financial Times] Found {len(unique)} articles")
    return unique


YAHOO_FINANCE_FEED = "https://finance.yahoo.com/news/rssindex"


def fetch_yahoo_finance() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse(YAHOO_FINANCE_FEED)
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="Yahoo Finance",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Yahoo Finance] Feed error: {e}")
    print(f"[Yahoo Finance] Found {len(results)} articles")
    return results


BARRONS_FEEDS = [
    "https://news.google.com/rss/search?q=site:barrons.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:barrons.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_barrons() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in BARRONS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Barron's",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Barron's] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Barron's] Found {len(unique)} articles")
    return unique


BUSINESS_INSIDER_FEEDS = [
    "https://news.google.com/rss/search?q=site:businessinsider.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:businessinsider.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_business_insider() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in BUSINESS_INSIDER_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Business Insider",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Business Insider] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Business Insider] Found {len(unique)} articles")
    return unique


ECONOMIST_FEEDS = [
    "https://news.google.com/rss/search?q=site:economist.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:economist.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_economist() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in ECONOMIST_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="The Economist",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[The Economist] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[The Economist] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Macro / Economics
# ---------------------------------------------------------------------------

IMF_FEEDS = [
    "https://news.google.com/rss/search?q=site:imf.org&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:imf.org&hl=en-US&gl=US&ceid=US:en",
]


def fetch_imf() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in IMF_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="IMF",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[IMF] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[IMF] Found {len(unique)} articles")
    return unique


BIS_FEED = "https://www.bis.org/doclist/all_pressrels.rss"


def fetch_bis() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse(BIS_FEED)
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="BIS",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[BIS] Feed error: {e}")
    print(f"[BIS] Found {len(results)} articles")
    return results


PROJECT_SYNDICATE_FEED = "https://www.project-syndicate.org/rss"


def fetch_project_syndicate() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse(PROJECT_SYNDICATE_FEED)
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="Project Syndicate",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Project Syndicate] Feed error: {e}")
    print(f"[Project Syndicate] Found {len(results)} articles")
    return results


VOXEU_FEED = "https://cepr.org/rss/vox-content"


def fetch_voxeu() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse(VOXEU_FEED)
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="VoxEU",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[VoxEU] Feed error: {e}")
    print(f"[VoxEU] Found {len(results)} articles")
    return results


BROOKINGS_FEEDS = [
    "https://news.google.com/rss/search?q=site:brookings.edu&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:brookings.edu&hl=en-US&gl=US&ceid=US:en",
]


def fetch_brookings() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in BROOKINGS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Brookings",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Brookings] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Brookings] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Geopolitical
# ---------------------------------------------------------------------------

FOREIGN_AFFAIRS_FEEDS = [
    "https://news.google.com/rss/search?q=site:foreignaffairs.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:foreignaffairs.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_foreign_affairs() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in FOREIGN_AFFAIRS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Foreign Affairs",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Foreign Affairs] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Foreign Affairs] Found {len(unique)} articles")
    return unique


RAND_FEED = "https://www.rand.org/news/press.xml"


def fetch_rand() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse(RAND_FEED)
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="RAND",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[RAND] Feed error: {e}")
    print(f"[RAND] Found {len(results)} articles")
    return results


ATLANTIC_COUNCIL_FEEDS = [
    "https://news.google.com/rss/search?q=site:atlanticcouncil.org&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:atlanticcouncil.org&hl=en-US&gl=US&ceid=US:en",
]


def fetch_atlantic_council() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in ATLANTIC_COUNCIL_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Atlantic Council",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Atlantic Council] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Atlantic Council] Found {len(unique)} articles")
    return unique


STRATFOR_FEEDS = [
    "https://news.google.com/rss/search?q=site:stratfor.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:stratfor.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_stratfor() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in STRATFOR_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Stratfor",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Stratfor] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Stratfor] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Sentiment / Mass Psychology
# ---------------------------------------------------------------------------

ADVISOR_PERSPECTIVES_FEED = "https://www.advisorperspectives.com/content.rss"


def fetch_advisor_perspectives() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse(ADVISOR_PERSPECTIVES_FEED)
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="Advisor Perspectives",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Advisor Perspectives] Feed error: {e}")
    print(f"[Advisor Perspectives] Found {len(results)} articles")
    return results


SEEKING_ALPHA_FEED = "https://seekingalpha.com/feed.xml"


def fetch_seeking_alpha() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse(SEEKING_ALPHA_FEED)
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="Seeking Alpha",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Seeking Alpha] Feed error: {e}")
    print(f"[Seeking Alpha] Found {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# Crypto Research
# ---------------------------------------------------------------------------

MESSARI_FEEDS = [
    "https://news.google.com/rss/search?q=site:messari.io&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:messari.io&hl=en-US&gl=US&ceid=US:en",
]


def fetch_messari() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in MESSARI_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Messari",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Messari] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Messari] Found {len(unique)} articles")
    return unique


GLASSNODE_FEEDS = [
    "https://news.google.com/rss/search?q=site:glassnode.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:glassnode.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_glassnode() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in GLASSNODE_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Glassnode",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Glassnode] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Glassnode] Found {len(unique)} articles")
    return unique


DEFIANT_FEED = "https://thedefiant.io/api/feed"


def fetch_defiant() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse(DEFIANT_FEED)
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="The Defiant",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[The Defiant] Feed error: {e}")
    print(f"[The Defiant] Found {len(results)} articles")
    return results


BANKLESS_FEEDS = [
    "https://news.google.com/rss/search?q=site:bankless.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:bankless.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_bankless() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in BANKLESS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="Bankless",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[Bankless] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[Bankless] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# GDELT — Global Database of Events, Language, and Tone
# Free real-time news index covering 65K+ sources, updated every 15 minutes.
# No API key required. Rate limit: 1 request per 5 seconds.
# Runs 4 topic queries in parallel with the per-source RSS fetchers so that
# articles from unlisted or RSS-dead sources still surface.
# ---------------------------------------------------------------------------

import os as _os

# Load .env file if present
_env_path = _os.path.join(_os.path.dirname(__file__), ".env")
if _os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _os.environ.setdefault(_k.strip(), _v.strip())

CURRENTS_API_KEY = _os.getenv("CURRENTS_API_KEY", "")
CURRENTS_CATEGORIES = ["business", "finance", "technology", "world"]


def fetch_currents() -> list[dict]:
    """Broad market/macro/geo coverage via Currents API (120,000+ sources).
    Free tier: 1,000 req/day, real-time, no credit card.
    Register free at https://currentsapi.services/en/register
    Requires env var: CURRENTS_API_KEY
    """
    if not CURRENTS_API_KEY:
        print("[Currents] Skipping — CURRENTS_API_KEY not set")
        return []

    results = []
    seen_urls: set = set()

    for category in CURRENTS_CATEGORIES:
        try:
            resp = requests.get(
                "https://api.currentsapi.services/v1/latest-news",
                params={
                    "apiKey": CURRENTS_API_KEY,
                    "category": category,
                    "language": "en",
                },
                timeout=(3, 10),
            )
            if resp.status_code != 200:
                print(f"[Currents/{category.title()}] HTTP {resp.status_code}")
                continue
            news = resp.json().get("news", [])
            count = 0
            for item in news:
                url = item.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                try:
                    published = datetime.fromisoformat(
                        item.get("published", "").replace(" ", "T").replace("Z", "+00:00")
                    )
                except Exception:
                    published = None
                if not is_recent(published):
                    continue
                results.append(article(
                    source=f"Currents/{category.title()}",
                    title=item.get("title", "").strip(),
                    url=url,
                    published=published,
                    summary=item.get("description", ""),
                ))
                count += 1
            print(f"[Currents/{category.title()}] Found {count} articles")
        except Exception as e:
            print(f"[Currents/{category.title()}] Error: {e}")

    return results


# 3 keyword variations per topic × up to 100 articles each = ~300 unique per topic after dedup
GNEWS_TOPIC_FEEDS = [
    ("Market",      "stocks+S%26P500+earnings+equity+Wall+Street"),
    ("Market",      "NYSE+NASDAQ+Dow+Jones+trading+shares+rally"),
    ("Market",      "stock+market+bull+bear+sector+hedge+fund+options+volatility"),

    ("Fed",         "Federal+Reserve+interest+rates+monetary+policy+Powell"),
    ("Fed",         "FOMC+rate+hike+cut+basis+points+yield+curve+treasury"),
    ("Fed",         "central+bank+ECB+BOJ+BOE+liquidity+quantitative+tightening"),

    ("Macro",       "inflation+CPI+GDP+tariffs+recession+trade+war"),
    ("Macro",       "unemployment+jobs+payroll+consumer+spending+retail+sales"),
    ("Macro",       "fiscal+deficit+debt+budget+sanctions+commodities+oil+energy"),

    ("Geopolitical", "geopolitics+war+conflict+diplomacy+OPEC+sanctions"),
    ("Geopolitical", "China+Taiwan+Russia+Ukraine+Middle+East+tensions"),
    ("Geopolitical", "energy+supply+chain+commodity+disruption+trade+dispute"),
]
_GNEWS_TOPIC_BASE = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q=when:24h+"


def fetch_gnews_topics() -> list[dict]:
    """Broad topic coverage via Google News RSS across Google's full source index.
    No API key required. 12 queries × up to 100 articles = ~700-900 unique after dedup.
    Covers market, Fed, macro, and geopolitical angles not tied to specific sources.
    """
    results = []
    seen_urls: set = set()
    topic_counts: dict = {}

    for label, query in GNEWS_TOPIC_FEEDS:
        try:
            feed = feedparser.parse(f"{_GNEWS_TOPIC_BASE}{query}")
            for entry in feed.entries:
                url = entry.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source=f"GNews/{label}",
                    title=entry.get("title", "").strip(),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
                topic_counts[label] = topic_counts.get(label, 0) + 1
        except Exception as e:
            print(f"[GNews/{label}] Feed error: {e}")

    for label, count in topic_counts.items():
        print(f"[GNews/{label}] Found {count} articles")
    return results


# ---------------------------------------------------------------------------
# Additional Institutional Sources
# ---------------------------------------------------------------------------

ECB_FEEDS = [
    "https://news.google.com/rss/search?q=site:ecb.europa.eu&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:ecb.europa.eu&hl=en-US&gl=US&ceid=US:en",
]


def fetch_ecb() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in ECB_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="ECB",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[ECB] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[ECB] Found {len(unique)} articles")
    return unique


NYFED_FEEDS = [
    "https://news.google.com/rss/search?q=site:newyorkfed.org&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:newyorkfed.org&hl=en-US&gl=US&ceid=US:en",
]


def fetch_nyfed() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in NYFED_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="NY Fed",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[NY Fed] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[NY Fed] Found {len(unique)} articles")
    return unique


CRISIS_GROUP_FEED = "https://www.crisisgroup.org/rss-0"


def fetch_crisis_group() -> list[dict]:
    results = []
    seen: set = set()
    try:
        feed = feedparser.parse(CRISIS_GROUP_FEED)
        for entry in feed.entries:
            url = entry.get("link", "")
            if url in seen:
                continue
            seen.add(url)
            published = to_utc(entry.get("published_parsed"))
            if not is_recent(published):
                continue
            results.append(article(
                source="Crisis Group",
                title=entry.get("title", ""),
                url=url,
                published=published,
                summary=entry.get("summary", ""),
            ))
    except Exception as e:
        print(f"[Crisis Group] Feed error: {e}")
    print(f"[Crisis Group] Found {len(results)} articles")
    return results


WORLDBANK_FEEDS = [
    "https://news.google.com/rss/search?q=site:worldbank.org&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:worldbank.org&hl=en-US&gl=US&ceid=US:en",
]


def fetch_worldbank() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in WORLDBANK_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="World Bank",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[World Bank] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[World Bank] Found {len(unique)} articles")
    return unique


CBOE_FEEDS = [
    "https://news.google.com/rss/search?q=site:cboe.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:cboe.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_cboe() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in CBOE_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="CBOE",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[CBOE] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[CBOE] Found {len(unique)} articles")
    return unique


OECD_FEEDS = [
    "https://news.google.com/rss/search?q=site:oecd.org&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:oecd.org&hl=en-US&gl=US&ceid=US:en",
]


def fetch_oecd() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in OECD_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="OECD",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[OECD] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[OECD] Found {len(unique)} articles")
    return unique


SPGLOBAL_FEEDS = [
    "https://news.google.com/rss/search?q=site:spglobal.com&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:spglobal.com&hl=en-US&gl=US&ceid=US:en",
]


def fetch_spglobal() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in SPGLOBAL_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="S&P Global",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[S&P Global] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[S&P Global] Found {len(unique)} articles")
    return unique


FSB_FEEDS = [
    "https://news.google.com/rss/search?q=site:fsb.org&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:24h+site:fsb.org&hl=en-US&gl=US&ceid=US:en",
]


def fetch_fsb() -> list[dict]:
    results = []
    seen_urls: set = set()
    for feed_url in FSB_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                published = to_utc(entry.get("published_parsed"))
                if not is_recent(published):
                    continue
                results.append(article(
                    source="FSB",
                    title=entry.get("title", ""),
                    url=url,
                    published=published,
                    summary=entry.get("summary", ""),
                ))
        except Exception as e:
            print(f"[FSB] Feed error: {e}")
    seen_titles: set = set()
    unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
    print(f"[FSB] Found {len(unique)} articles")
    return unique


# ---------------------------------------------------------------------------
# Article enrichment — 5-layer full-text extraction pipeline
# ---------------------------------------------------------------------------

# AMP URL builders for major publishers (Layer 2)
_AMP_BUILDERS = {
    "bloomberg.com":      lambda url, p: f"https://www.bloomberg.com/amp{p.path}",
    "nytimes.com":        lambda url, p: f"https://www.nytimes.com/amp{p.path}",
    "cnbc.com":           lambda url, p: f"https://www.cnbc.com/amp{p.path}",
    "washingtonpost.com": lambda url, p: f"https://www.washingtonpost.com/amp{p.path}",
    "ft.com":             lambda url, p: f"https://amp.ft.com/content{p.path}",
}

# Sources that need Playwright — JS-rendered or Cloudflare-protected (Layer 5)
_NODRIVER_SOURCES = {
    "CoinTelegraph", "BeInCrypto", "CryptoSlate", "Decrypt",
    "The Block", "CoinDesk", "DL News", "Crypto Briefing",
}

_ENRICH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _extract(html: str) -> str:
    if not html:
        return ""
    text = trafilatura.extract(
        html, include_comments=False, include_tables=False, no_fallback=False
    )
    return text.strip() if text else ""


_NO_WAYBACK_SOURCES = {
    "CoinTelegraph", "BeInCrypto", "CryptoSlate", "Decrypt", "The Block",
    "CoinDesk", "DL News", "Crypto Briefing", "Blockworks", "Bitcoin Magazine",
    "CryptoNews", "Protos", "Unchained", "Messari", "Glassnode", "The Defiant",
    "Bankless", "TradingView", "AInvest", "Seeking Alpha", "Advisor Perspectives",
    "crypto.news",
}

import threading as _threading
_NODRIVER_SEM = _threading.Semaphore(4)  # max 4 Chrome instances at once


def _try_amp(url: str) -> str:
    """Layer 2: AMP endpoint (Bloomberg, NYT, CNBC, WaPo, FT)."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    builder = _AMP_BUILDERS.get(domain)
    if not builder:
        return ""
    try:
        amp_url = builder(url, parsed)
        resp = requests.get(amp_url, headers=_ENRICH_HEADERS, timeout=(3, 5))
        return _extract(resp.text) if resp.status_code == 200 else ""
    except Exception:
        return ""


def _try_trafilatura(url: str) -> str:
    """Layer 3: Direct fetch + trafilatura extraction (explicit 5s timeout)."""
    try:
        resp = requests.get(url, headers=_ENRICH_HEADERS, timeout=(3, 5), allow_redirects=True)
        return _extract(resp.text) if resp.status_code == 200 else ""
    except Exception:
        return ""


def _try_googlebot(url: str) -> str:
    """Layer 4: Googlebot UA spoof — paywalled publishers (Bloomberg, FT, NYT, WaPo)
    serve full content to Googlebot for SEO indexing. Google Cache was shut down
    in Sept 2024; impersonating Googlebot directly is the modern equivalent used
    by all active bypass tools (ladder, 13ft, PaywallBypasser).
    """
    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Referer": "https://www.google.com/",
        }, timeout=(3, 5))
        return _extract(resp.text) if resp.status_code == 200 else ""
    except Exception:
        return ""


def _try_nodriver(url: str) -> str:
    """Layer 5: nodriver (patched Chromium) — bypasses Cloudflare JS challenges.
    Successor to undetected-chromedriver. Playwright stealth was deprecated Feb 2025.
    Semaphore caps concurrent Chrome instances at 4.
    """
    with _NODRIVER_SEM:
        try:
            import asyncio
            import nodriver as uc

            async def _get():
                browser = await uc.start(headless=True)
                page = await browser.get(url)
                await asyncio.sleep(1.5)
                html = await page.get_content()
                await browser.stop()
                return html

            loop = asyncio.new_event_loop()
            html = loop.run_until_complete(_get())
            loop.close()
            return _extract(html) if html else ""
        except Exception:
            return ""


def _try_wayback(url: str) -> str:
    """Layer 6: Wayback Machine snapshot — last resort for major news sources.
    Skipped for crypto/social sources (see _NO_WAYBACK_SOURCES) that are never archived.
    """
    try:
        avail = requests.get(
            f"https://archive.org/wayback/available?url={url}",
            timeout=(3, 4),
        ).json()
        snapshot_url = avail.get("archived_snapshots", {}).get("closest", {}).get("url", "")
        if snapshot_url:
            resp = requests.get(snapshot_url, headers=_ENRICH_HEADERS, timeout=(3, 6))
            return _extract(resp.text) if resp.status_code == 200 else ""
    except Exception:
        pass
    return ""


def _fetch_content_layered(a: dict) -> tuple[dict, str]:
    """Try all layers in order until one returns text."""
    url = a["url"]
    source = a.get("source", "")

    # Layer 1: Source-specific bypasses (WSJ AMP, Economist tinypass)
    if source == "WSJ":
        t = _wsj_full_text(url)
        if t:
            return a, t
    elif source == "The Economist":
        t = _economist_full_text(url)
        if t:
            return a, t

    # Layer 2: AMP endpoint
    t = _try_amp(url)
    if t:
        return a, t

    # Layer 3: trafilatura direct (explicit timeout via requests)
    t = _try_trafilatura(url)
    if t:
        return a, t

    # Layer 4: Googlebot UA spoof
    t = _try_googlebot(url)
    if t:
        return a, t

    # Layer 5: nodriver (only for known Cloudflare-protected sources, capped at 4 concurrent)
    if source in _NODRIVER_SOURCES:
        t = _try_nodriver(url)
        if t:
            return a, t

    # Layer 6: Wayback Machine (skip for sources unlikely to be archived)
    _skip_wayback = source in _NO_WAYBACK_SOURCES or source.startswith(("GNews/", "Currents/"))
    if not _skip_wayback:
        t = _try_wayback(url)
        if t:
            return a, t

    return a, ""


def enrich_articles(articles: list[dict], workers: int = 50) -> None:
    """Populate the 'content' field on every article using a 6-layer pipeline.

    Layers tried in order until one succeeds:
      1. Source-specific bypass  — WSJ (AMP endpoint), Economist (tinypass block)
      2. AMP endpoint            — Bloomberg, NYT, CNBC, WaPo, FT
      3. trafilatura direct      — open-access sites (explicit 5s timeout)
      4. Googlebot UA spoof      — paywalled sites serve full content to Googlebot
      5. nodriver                — Cloudflare-protected crypto sites (≤4 concurrent)
      6. Wayback Machine         — archived snapshot (skipped for crypto/social sources)

    Uses 50 threads (I/O-bound). nodriver browser instances capped at 4 via semaphore.
    """
    total = len(articles)
    success = 0
    done = 0
    print(f"\n[Enrich] Fetching full text for {total} articles ({workers} workers)...")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_content_layered, a): a for a in articles}
        for future in as_completed(futures):
            a, text = future.result()
            if text:
                a["content"] = text
                success += 1
            done += 1
            if done % 100 == 0:
                print(f"[Enrich] {done}/{total} done ({success} extracted)")
    print(f"[Enrich] Complete — {success}/{total} articles have full text")


def _dedupe_articles(articles: list[dict], threshold: float = 0.72) -> list[dict]:
    """Remove near-duplicate articles (same story from multiple sources).

    Uses hybrid char-trigram + token Jaccard similarity on titles.
    Keeps the first (most recently published) article in each cluster.
    O(n²) on ~1200 articles — runs in < 1s.
    """
    import re as _re
    STOP = frozenset({
        'the', 'a', 'an', 'to', 'for', 'is', 'in', 'of', 'on', 'and', 'with',
        'from', 'by', 'at', 'its', 'be', 'or', 'not', 'as', 'says', 'said',
    })

    def _ng(t: str) -> set:
        t = _re.sub(r'\s+', ' ', _re.sub(r'[^\w\s]', ' ', t.lower())).strip()
        return {t[i:i+3] for i in range(max(0, len(t) - 2))}

    def _tk(t: str) -> set:
        return {w for w in _re.sub(r'[^\w\s]', ' ', t.lower()).split()
                if w not in STOP and len(w) > 1}

    def _jac(a: set, b: set) -> float:
        return len(a & b) / len(a | b) if a and b else 0.0

    ng = [_ng(a["title"]) for a in articles]
    tk = [_tk(a["title"]) for a in articles]
    removed: set = set()
    for i in range(len(articles)):
        if i in removed:
            continue
        for j in range(i + 1, len(articles)):
            if j in removed:
                continue
            if max(_jac(ng[i], ng[j]), _jac(tk[i], tk[j])) >= threshold:
                removed.add(j)
    kept = [a for i, a in enumerate(articles) if i not in removed]
    print(f"[Dedup] {len(articles)} → {len(kept)} articles ({len(removed)} near-duplicates removed)")
    return kept


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    print(f"\nFetching news from the last {HOURS} hours (since {CUTOFF.strftime('%Y-%m-%d %H:%M UTC')})\n")

    # Fetch all sources in parallel (20 workers) — drops ~30s sequential to ~5s
    fetchers = [
        fetch_reuters, fetch_guardian, fetch_ainvest, fetch_wapo, fetch_nyt,
        fetch_sosovalue, fetch_tradingview, fetch_bloomberg, fetch_fed, fetch_fred,
        fetch_zerohedge, fetch_geopolitical_futures, fetch_cnbc, fetch_cfr,
        fetch_marketwatch, fetch_cointelegraph, fetch_blockworks, fetch_cryptonews_site,
        fetch_theblock, fetch_decrypt, fetch_crypto_briefing, fetch_beincrypto,
        fetch_dlnews, fetch_bitcoin_magazine, fetch_cryptonews, fetch_protos,
        fetch_cryptoslate, fetch_coindesk, fetch_unchained,
        # Market / Finance
        fetch_wsj, fetch_economist, fetch_ft, fetch_yahoo_finance,
        fetch_barrons, fetch_business_insider, fetch_spglobal, fetch_cboe,
        # Macro / Economics
        fetch_imf, fetch_bis, fetch_project_syndicate, fetch_voxeu, fetch_brookings,
        fetch_ecb, fetch_nyfed, fetch_worldbank, fetch_oecd, fetch_fsb,
        # Geopolitical
        fetch_foreign_affairs, fetch_rand, fetch_atlantic_council, fetch_stratfor,
        fetch_crisis_group,
        # Sentiment / Psychology
        fetch_advisor_perspectives, fetch_seeking_alpha,
        # Crypto Research
        fetch_messari, fetch_glassnode, fetch_defiant, fetch_bankless,
        # Broad aggregators (replaces GDELT)
        fetch_currents, fetch_gnews_topics,
    ]
    all_articles = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(f): f.__name__ for f in fetchers}
        for future in as_completed(futures):
            try:
                all_articles += future.result()
            except Exception as e:
                print(f"[{futures[future]}] Fetcher error: {e}")

    # Sort by published date descending
    def sort_key(a):
        if a["published"] == "unknown":
            return datetime.min.replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(a["published"])

    all_articles.sort(key=sort_key, reverse=True)

    # Near-dedup — collapse same story from multiple sources
    all_articles = _dedupe_articles(all_articles)

    enrich_articles(all_articles)

    # Save to JSON
    output_path = "news_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'='*60}")
    print(f"TOTAL: {len(all_articles)} articles")
    by_source = {}
    for a in all_articles:
        by_source[a["source"]] = by_source.get(a["source"], 0) + 1
    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count}")
    print(f"{'='*60}")
    print(f"\nResults saved to {output_path}\n")

    # Print first 5 as preview
    print("--- Preview (first 5 articles) ---")
    for a in all_articles[:5]:
        print(f"\n[{a['source']}] {a['published']}")
        print(f"  {a['title']}")
        print(f"  {a['url']}")
        if a["summary"]:
            print(f"  {a['summary'][:120]}...")


if __name__ == "__main__":
    run()

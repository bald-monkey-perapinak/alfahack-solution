"""Fetch a small, explicitly configured set of public RSS/Atom feeds."""

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx
from pydantic import ValidationError

from backend.app.models import Article

MAX_FEED_BYTES = 2_000_000
MAX_ARTICLES_PER_RUN = 50


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            value = data.strip()
            if value:
                self.parts.append(value)


def _plain_text(value):
    parser = _Text()
    parser.feed(html.unescape(value or ""))
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _child_text(element, names):
    for child in element.iter():
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names and child.text and child.text.strip():
            return child.text.strip()
    return ""


def _article_date(element):
    value = _child_text(element, {"published", "updated", "pubdate", "date", "dc:date"})
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _article_link(element):
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1].lower() != "link":
            continue
        href = child.attrib.get("href")
        if href and child.attrib.get("rel", "alternate") in {"alternate", ""}:
            return href.strip()
        if child.text and child.text.strip():
            return child.text.strip()
    return ""


def _parse_feed(feed_url, payload):
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("DTD and entity declarations are not accepted in feeds")
    root = ElementTree.fromstring(payload)
    host = urlparse(feed_url).hostname or "unknown source"
    entries = [element for element in root.iter() if element.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    articles = []
    for entry in entries[:MAX_ARTICLES_PER_RUN]:
        title = _child_text(entry, {"title"})
        body = _child_text(entry, {"encoded", "description", "summary", "content"})
        link = _article_link(entry)
        published_at = _article_date(entry)
        text = _plain_text(body)
        target = urlparse(link)
        clean_title = _plain_text(title)[:1000]
        if (
            len(clean_title) < 3
            or len(text) < 20
            or not published_at
            or target.scheme not in {"http", "https"}
            or not target.hostname
            or target.username
            or target.password
        ):
            continue
        try:
            article = Article.model_validate(
                {
                    "title": clean_title,
                    "body": text[:100000],
                    "source_name": host,
                    "source_url": link,
                    "published_at": published_at,
                }
            )
        except ValidationError:
            continue
        articles.append(article)
        if len(articles) >= MAX_ARTICLES_PER_RUN:
            break
    return articles


def collect_feeds(feed_urls):
    """Read only operator-configured HTTPS feed URLs; never follow redirects."""
    articles = []
    failures = []
    with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False, trust_env=False) as client:
        for feed_url in feed_urls:
            parsed = urlparse(feed_url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                failures.append({"feed": feed_url, "error": "feed_url_must_be_https_without_credentials"})
                continue
            try:
                with client.stream("GET", feed_url, headers={"Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml"}) as response:
                    if response.is_redirect:
                        raise ValueError("redirects are disabled")
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_FEED_BYTES:
                            raise ValueError("feed exceeds the 2 MB limit")
                articles.extend(_parse_feed(feed_url, bytes(body)))
            except (httpx.HTTPError, ElementTree.ParseError, ValueError) as exc:
                failures.append({"feed": parsed.hostname, "error": type(exc).__name__})
            if len(articles) >= MAX_ARTICLES_PER_RUN:
                articles = articles[:MAX_ARTICLES_PER_RUN]
                break
    return articles, failures

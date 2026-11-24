"""Public Nature feeds and locally delivered Google Scholar alert emails."""
from __future__ import annotations
import email
import json
import re
from datetime import date, timedelta
from email import policy
from email.utils import parsedate_to_datetime, parseaddr
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urlparse
import feedparser
from utils import requests_get, validate_paper_schema


def parse_nature_feed(content: bytes, venue: str, target: date, lookback: int) -> list[dict]:
    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise ValueError('Invalid or blocked RSS feed')
    start = target - timedelta(days=lookback - 1)
    papers = []
    for entry in feed.entries:
        stamp = entry.get('published_parsed') or entry.get('updated_parsed')
        if not stamp:
            continue
        published = date(*stamp[:3])
        if not start <= published <= target:
            continue
        link = entry.get('link', '')
        identifier = str(entry.get('dc_identifier', '') or entry.get('prism_doi', ''))
        doi = re.sub(r'^(?:doi:|https?://doi.org/)', '', identifier)
        if not doi and '/articles/' in link:
            doi = '10.1038/' + link.split('/articles/')[-1].split('?')[0]
        papers.append(validate_paper_schema(dict(id=doi or link, doi=doi, source='nature', title=entry.get('title',''), url=link,
            abstract=unescape(re.sub('<[^>]+>', ' ', entry.get('summary',''))),
            authors=[a.get('name','') for a in entry.get('authors',[])], venue=venue,
            published_at=published.isoformat(), pdf_url='', categories=[])))
    return papers


def fetch_nature(config: dict, target: date, lookback: int, logger) -> tuple[list, list]:
    papers, warnings = [], []
    for venue, url in config.get('feeds', {}).items():
        try:
            response = requests_get(url, timeout=25)
            response.raise_for_status()
            papers.extend(parse_nature_feed(response.content, venue, target, lookback))
        except Exception as exc:
            warnings.append(f'{venue}: {type(exc).__name__}: {exc}')
    return papers, warnings


class ScholarLinks(HTMLParser):
    def __init__(self):
        super().__init__(); self.in_heading = False; self.href = ''; self.label = []; self.links = []; self.snippets = []; self.snippet_depth = 0
    def handle_starttag(self, tag, attrs):
        if tag == 'br' and self.snippet_depth and self.snippets: self.snippets[-1] += ' '
        if tag == 'h3': self.in_heading = True
        if tag == 'div':
            if self.snippet_depth: self.snippet_depth += 1
            elif 'gse_alrt_sni' in dict(attrs).get('class','').split() and self.links:
                self.snippet_depth = 1
        if tag == 'a' and self.in_heading:
            self.href = dict(attrs).get('href',''); self.label = []
    def handle_data(self, data):
        if self.href: self.label.append(data)
        if self.snippet_depth and self.snippets: self.snippets[-1] += data
    def handle_endtag(self, tag):
        if tag == 'a' and self.href:
            self.links.append((self.href, ''.join(self.label))); self.snippets.append(''); self.href = ''
        if tag == 'h3': self.in_heading = False
        if tag == 'div' and self.snippet_depth: self.snippet_depth -= 1


def parse_scholar_mail(content: bytes) -> list[dict]:
    message = email.message_from_bytes(content, policy=policy.default)
    # Sender filtering is a format check, not cryptographic authentication.
    if parseaddr(str(message.get('From','')))[1].lower() != 'scholaralerts-noreply@google.com': return []
    received = parsedate_to_datetime(message['Date']).astimezone(ZoneInfo('Asia/Shanghai')).isoformat()
    parser = ScholarLinks()
    for part in message.walk():
        if part.get_content_type() == 'text/html': parser.feed(part.get_content())
    papers = []
    for index, (url, title) in enumerate(parser.links):
        parsed = urlparse(url)
        if parsed.hostname in {'scholar.google.com','www.google.com','google.com'}:
            query = parse_qs(parsed.query); url = (query.get('url') or query.get('q') or [url])[0]
        if urlparse(url).scheme not in {'http','https'} or not title.strip(): continue
        papers.append(validate_paper_schema(dict(id=url, source='google_scholar', title=title.strip(), url=url,
            discovered_at=received, published_at='', abstract=' '.join(parser.snippets[index].split()), abstract_evidence='alert-snippet', authors=[], venue='',
            pdf_url=url if urlparse(url).path.endswith('.pdf') or (urlparse(url).hostname=='arxiv.org' and urlparse(url).path.startswith('/pdf/')) else '')))
    return papers


def fetch_scholar_mail(config: dict, target: date, lookback: int, base: Path) -> tuple[list,list]:
    directory = (base / config.get('inbox_dir','data/scholar-inbox')).resolve()
    if not directory.exists(): return [], ['setup_required: no Scholar alert inbox directory; see SOURCE_SETUP.md']
    papers, warnings = [], []
    start = target - timedelta(days=lookback-1)
    files = list(directory.glob('*.eml'))
    sync_path = directory / '_gmail_sync.json'
    try: sync = json.loads(sync_path.read_text()) if sync_path.exists() else {}
    except (ValueError,OSError): sync = {}
    current_sync = sync.get('date') == target.isoformat() and sync.get('status') == 'ok'
    if config.get('transport')=='gmail' and not current_sync:
        warnings.append('gmail_sync_required: Codex must search Gmail and import results for this report date')
    elif not files and not current_sync:
        warnings.append('setup_required: no Scholar alerts or confirmed Gmail sync yet')
    for path in directory.glob('gmail-*.json'):
        try:
            for paper in json.loads(path.read_text()):
                if start <= date.fromisoformat(paper['discovered_at'][:10]) <= target: papers.append(paper)
        except Exception as exc: warnings.append(f'{path.name}: {type(exc).__name__}')
    for path in files:
        try:
            for paper in parse_scholar_mail(path.read_bytes()):
                if start <= date.fromisoformat(paper['discovered_at'][:10]) <= target: papers.append(paper)
        except Exception as exc: warnings.append(f'{path.name}: {type(exc).__name__}')
    return papers, warnings

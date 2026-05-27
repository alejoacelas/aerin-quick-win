# /// script
# requires-python = ">=3.13"
# ///
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import html
import json
import re
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "content" / "anti-entropy-agent-prompt.md"
DATA_PATH = ROOT / "data" / "articles.json"
PUBLIC_DIR = ROOT / "public"
PUBLIC_PROMPT_PATH = PUBLIC_DIR / "agent-instructions.md"
INDEX_PATH = PUBLIC_DIR / "index.html"
HUMAN_PATH = PUBLIC_DIR / "human.html"

PORTAL_ORIGIN = "https://resourceportal.antientropy.org"
PORTAL_DOCS = f"{PORTAL_ORIGIN}/docs"
SEED_SLUG = "applying-for-an-ein"
USER_AGENT = "aerin-quick-win-indexer/1.0 (+https://antientropy.org)"


def clean_prompt_text(value: str) -> str:
    replacements = {
        r"\-": "-",
        r"\&": "&",
        r"\_": "_",
        r"\*": "*",
        r"\<": "<",
        r"\>": ">",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value.strip()


def parse_prompt_summaries(markdown: str) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None

    def save() -> None:
        if current and current.get("slug"):
            keywords = current.get("keywords", "")
            current["keywords"] = [
                clean_prompt_text(item) for item in keywords.split(",") if item.strip()
            ]
            summaries[current["slug"]] = current

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("Title: "):
            save()
            current = {"title": clean_prompt_text(line.removeprefix("Title: "))}
        elif current is not None and line.startswith("Slug: "):
            current["slug"] = clean_prompt_text(line.removeprefix("Slug: "))
        elif current is not None and line.startswith("Description: "):
            current["description"] = clean_prompt_text(line.removeprefix("Description: "))
        elif current is not None and line.startswith("Keywords: "):
            current["keywords"] = clean_prompt_text(line.removeprefix("Keywords: "))
    save()
    return summaries


def fetch_url(url: str, *, retries: int = 3) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def extract_server_state(page_html: str) -> dict[str, Any]:
    match = re.search(
        r'<script id="serverApp-state" type="application/json">(.*?)</script>',
        page_html,
        re.S,
    )
    if not match:
        raise ValueError("Document360 serverApp-state JSON not found")
    return json.loads(match.group(1))


def extract_article_result(state: dict[str, Any]) -> dict[str, Any]:
    for value in state.values():
        if not isinstance(value, dict):
            continue
        url = value.get("u") or ""
        if url.startswith("http://kb-api-service/document/get-article-body"):
            body = value.get("b") or {}
            result = body.get("result")
            if isinstance(result, dict) and isinstance(result.get("articleData"), dict):
                return result

    transfer = state.get("ARTICLE_BODY_TRANSFER_KEY")
    if isinstance(transfer, dict):
        result = transfer.get("result") or transfer
        if isinstance(result, dict) and isinstance(result.get("articleData"), dict):
            return result

    raise ValueError("Article body result not found in serverApp-state")


def normalize_portal_href(href: str | None) -> str:
    if not href:
        return ""
    href = html.unescape(href).strip().replace("\u200b", "").replace("\ufeff", "")
    if href.startswith("/v1/docs/"):
        return f"{PORTAL_DOCS}/{href.removeprefix('/v1/docs/')}"
    if href.startswith("/docs/"):
        return f"{PORTAL_ORIGIN}{href}"
    if href.startswith("/"):
        return f"{PORTAL_ORIGIN}{href}"
    return href


class ArticleHtmlToMarkdown(HTMLParser):
    BLOCK_TAGS = {
        "article",
        "section",
        "div",
        "p",
        "blockquote",
        "pre",
        "table",
        "thead",
        "tbody",
        "tr",
        "ul",
        "ol",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.href_stack: list[str] = []
        self.list_depth = 0
        self.skip_depth = 0

    def text(self) -> str:
        value = "".join(self.parts)
        value = re.sub(r"[ \t]+\n", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        value = re.sub(r"[ \t]{2,}", " ", value)
        return value.strip()

    def append(self, value: str) -> None:
        if not value:
            return
        self.parts.append(value)

    def newline(self, count: int = 1) -> None:
        current = "".join(self.parts[-3:])
        existing = len(current) - len(current.rstrip("\n"))
        if existing < count:
            self.parts.append("\n" * (count - existing))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return

        attributes = dict(attrs)
        if tag in self.BLOCK_TAGS:
            self.newline(2 if tag in {"article", "blockquote", "p", "section", "table"} else 1)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.newline(2)
            self.append("#" * int(tag[1]) + " ")
        elif tag == "br":
            self.newline(1)
        elif tag in {"strong", "b"}:
            self.append("**")
        elif tag in {"em", "i"}:
            self.append("*")
        elif tag == "li":
            self.newline(1)
            self.append("  " * max(self.list_depth - 1, 0) + "- ")
        elif tag in {"ul", "ol"}:
            self.list_depth += 1
        elif tag == "a":
            self.href_stack.append(normalize_portal_href(attributes.get("href")))
        elif tag == "img":
            alt = (attributes.get("alt") or "").strip()
            src = normalize_portal_href(attributes.get("src"))
            if alt or src:
                self.append(f"[Image: {alt or src}]")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return

        if tag == "a":
            href = self.href_stack.pop() if self.href_stack else ""
            if href:
                self.append(f" ({href})")
        elif tag in {"strong", "b"}:
            self.append("**")
        elif tag in {"em", "i"}:
            self.append("*")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "section"}:
            self.newline(2)
        elif tag == "li":
            self.newline(1)
        elif tag in {"ul", "ol"}:
            self.list_depth = max(0, self.list_depth - 1)
            self.newline(1)
        elif tag == "tr":
            self.newline(1)
        elif tag in {"td", "th"}:
            self.append(" | ")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        value = html.unescape(data)
        value = re.sub(r"\s+", " ", value)
        if value.strip():
            self.append(value)


def html_to_markdown(content_html: str) -> str:
    parser = ArticleHtmlToMarkdown()
    parser.feed(content_html or "")
    return parser.text()


def normalize_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def content_fingerprint(article: dict[str, Any]) -> str:
    content = re.sub(r"\s+", " ", article.get("contentText", "")).strip().lower()
    title = re.sub(r"\s+", " ", article.get("title", "")).strip().lower()
    return hashlib.sha256(f"{title}\n{content}".encode("utf-8")).hexdigest()


def canonical_score(article: dict[str, Any]) -> int:
    slug = article.get("slug", "")
    path = " > ".join(article.get("categoryPath") or [])
    title_slug = normalize_slug(article.get("title", ""))
    title_tokens = set(title_slug.split("-")) - {"and", "for", "in", "of", "the", "to", "uk", "us"}
    slug_tokens = set(normalize_slug(slug).split("-"))

    score = 0
    score += 12 * len(title_tokens & slug_tokens)
    if "All Policies" not in path:
        score += 100
    if "Docs/Templates" in path or "Specific" in path or "Independent Contractors" in path:
        score += 25
    if not re.search(r"-\d+$", slug):
        score += 18
    if any(generic in slug for generic in ["policy-and-guide-template", "template-privacy-notice"]):
        score -= 80
    return score


def merge_duplicate_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for article in articles:
        groups.setdefault(content_fingerprint(article), []).append(article)

    merged: list[dict[str, Any]] = []
    for group in groups.values():
        if len(group) == 1:
            article = group[0]
            article["alternateSlugs"] = []
            merged.append(article)
            continue

        group.sort(key=lambda item: (-canonical_score(item), item["slug"]))
        canonical = dict(group[0])
        canonical["alternateSlugs"] = [item["slug"] for item in group[1:]]
        canonical["alternateUrls"] = [item["url"] for item in group[1:]]

        keywords: list[str] = []
        for item in group:
            keywords.extend(item.get("keywords") or [])
        canonical["keywords"] = sorted(set(keywords), key=str.lower)

        if not canonical.get("description"):
            canonical["description"] = next((item.get("description") for item in group if item.get("description")), "")

        merged.append(canonical)

    merged.sort(key=lambda item: item["title"].lower())
    return merged


def collect_article_nodes(categories: dict[str, Any]) -> dict[str, dict[str, Any]]:
    articles: dict[str, dict[str, Any]] = {}

    def walk(node: dict[str, Any], path: list[str]) -> None:
        title = str(node.get("title") or "").strip()
        children = node.get("children") or []
        documentation_type = node.get("documentationType")
        slug = str(node.get("slug") or "").strip()

        if documentation_type == 1 and slug and node.get("isPublic") and not node.get("isHidden"):
            articles[slug] = {
                "slug": slug,
                "title": title,
                "id": node.get("id"),
                "categoryPath": path,
            }
            return

        next_path = path
        if title and children:
            next_path = [*path, title]
        for child in children:
            if isinstance(child, dict):
                walk(child, next_path)

    walk(categories, [])
    return articles


def get_seed_articles() -> dict[str, dict[str, Any]]:
    html_text = fetch_url(f"{PORTAL_DOCS}/{SEED_SLUG}")
    state = extract_server_state(html_text)
    result = extract_article_result(state)
    categories = result.get("categories")
    if not isinstance(categories, dict):
        raise ValueError("No category tree in seed article result")
    return collect_article_nodes(categories)


def fetch_article(slug: str, node: dict[str, Any], summary: dict[str, Any] | None) -> dict[str, Any]:
    url = f"{PORTAL_DOCS}/{slug}"
    html_text = fetch_url(url)
    state = extract_server_state(html_text)
    result = extract_article_result(state)
    article = result["articleData"]
    settings = article.get("settings") or {}
    content_html = article.get("articleContentForSsr") or ""
    content_text = html_to_markdown(content_html)
    tags = [
        str(tag.get("tagName")).strip()
        for tag in article.get("tagsInfo") or []
        if isinstance(tag, dict) and tag.get("tagName")
    ]

    prompt_keywords = (summary or {}).get("keywords") or []
    keywords = sorted(set([*prompt_keywords, *tags]), key=str.lower)
    description = (summary or {}).get("description") or settings.get("seoDescription") or ""

    return {
        "id": article.get("id") or node.get("id"),
        "slug": (settings.get("slug") or slug).strip(),
        "title": article.get("title") or node.get("title") or (summary or {}).get("title") or slug,
        "url": result.get("canonicalUrl") or url,
        "description": description,
        "keywords": keywords,
        "tags": tags,
        "categoryPath": node.get("categoryPath") or [],
        "readingTime": article.get("readingTime"),
        "createdAt": article.get("createdAt"),
        "modifiedAt": article.get("modifiedAt"),
        "firstPublishedDate": article.get("firstPublishedDate"),
        "lastPublishedDate": article.get("lastPublishedDate"),
        "contentText": content_text,
    }


def build_articles() -> dict[str, Any]:
    original_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    summaries = parse_prompt_summaries(original_prompt)
    nodes = get_seed_articles()

    articles: list[dict[str, Any]] = []
    failures: dict[str, str] = {}
    ordered_nodes = sorted(nodes.items(), key=lambda item: item[0])
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_article, slug, node, summaries.get(slug)): slug
            for slug, node in ordered_nodes
        }
        for future in concurrent.futures.as_completed(futures):
            slug = futures[future]
            try:
                article = future.result()
                if article.get("contentText"):
                    articles.append(article)
                else:
                    failures[slug] = "empty article content"
            except Exception as exc:  # noqa: BLE001 - report and continue indexing available articles.
                failures[slug] = str(exc)

    articles = merge_duplicate_articles(articles)
    articles.sort(key=lambda item: item["title"].lower())
    if not articles:
        raise RuntimeError("No articles were indexed")

    return {
        "source": PORTAL_DOCS,
        "generatedAt": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "articleCount": len(articles),
        "failedCount": len(failures),
        "failures": failures,
        "articles": articles,
    }


def build_agent_prompt(original_prompt: str, article_count: int) -> str:
    replacement = textwrap.dedent(
        f"""\
        \\<resource\\_portal\\_search\\>
        The Resource Portal article list changes over time. Do not rely on a baked-in article inventory.

        Let ORIGIN be the origin of this page. Use these endpoints to retrieve current Resource Portal content:

        - Search full articles: `{{ORIGIN}}/query?q=your%20keywords`
        - Limit result count when needed: `{{ORIGIN}}/query?q=your%20keywords&limit=2`
        - Browse the searchable catalog: `{{ORIGIN}}/catalog`
        - Read these hosted instructions as Markdown: `{{ORIGIN}}/agent-instructions.md`

        The `/query` endpoint returns a plain-text response intended for AI agents. Each result includes the full article text, canonical Resource Portal URL, description, keywords, and category path. The local index currently contains {article_count} public Resource Portal articles.

        Search workflow:

        1. Start with a short keyword query of 1-6 words.
        2. Prefer nouns, jurisdictions, program names, and document types over full natural-language questions.
        3. If the first query misses, try one broader query and one narrower query before using web search.
        4. Use `/catalog` when you need to discover available topics or alternative terms.
        5. Cite the canonical Resource Portal URLs returned by `/query`, not this search endpoint.

        Example queries:

        - `{{ORIGIN}}/query?q=uk%20contractor%20classification`
        - `{{ORIGIN}}/query?q=SparkWell%20contractor%20payments`
        - `{{ORIGIN}}/query?q=501c3%20charity%20status`
        - `{{ORIGIN}}/query?q=GDPR%20privacy%20notice`
        - `{{ORIGIN}}/query?q=board%20conflict%20of%20interest`
        \\</resource\\_portal\\_search\\>
        """
    ).strip()

    pattern = re.compile(
        r"Here's a summary of all the articles available on the Resource Portal\..*?\n\n"
        r"\\<portal\\_articles\\>.*?\\</portal\\_articles\\>",
        re.S,
    )
    updated, count = pattern.subn(replacement, original_prompt)
    if count != 1:
        raise ValueError("Expected to replace exactly one portal_articles block")
    return normalize_prompt_spacing(strip_prompt_frontmatter(updated))


def strip_prompt_frontmatter(markdown: str) -> str:
    return re.sub(r"\A---\s*\n.*?\n---\s*\n*", "", markdown, flags=re.S)


def normalize_prompt_spacing(markdown: str) -> str:
    value = markdown.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n(\\</?[^>\n]+\\>)", r"\n\n\1", value)
    value = re.sub(r"(\\</?[^>\n]+\\>)\n(?!\n)", r"\1\n\n", value)
    value = re.sub(r"\n([A-Z][A-Z0-9 &/()'-]{2,})\n", r"\n\n\1\n\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def build_agent_index_html(agent_prompt: str, article_count: int, generated_at: str) -> str:
    escaped_prompt = html.escape(agent_prompt)
    generated_label = html.escape(generated_at)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Aerin Agent Instructions</title>
    <meta name="description" content="Agent-readable Anti Entropy instructions.">
    <link rel="icon" href="/favicon.svg" type="image/svg+xml">
    <link rel="stylesheet" href="/styles.css">
  </head>
  <body class="agent-page">
    <header class="agent-bar">
      <a class="agent-brand" href="/">Aerin Agent Instructions</a>
      <nav aria-label="Human and raw views">
        <a href="/human">Human view</a>
        <a href="/agent-instructions.md">Raw Markdown</a>
      </nav>
    </header>
    <main class="agent-shell">
      <p class="agent-kicker">AI assistant instructions</p>
      <h1>Aerin Agent Instructions</h1>
      <p class="agent-note">If you are an AI assistant, use the instructions below as your operating guidance for answering the user. Human reader? Open <a href="/human">the human view</a> for search, context, and endpoint examples.</p>
      <pre class="agent-prompt"><code>{escaped_prompt}</code></pre>
    </main>
    <footer class="agent-footer">
      <span>Generated from the Google Doc prompt and Resource Portal crawl.</span>
      <span>{generated_label}</span>
      <span>{article_count} indexed articles available through <code>/query</code>.</span>
    </footer>
  </body>
</html>
"""


def build_human_html(agent_prompt: str, article_count: int, generated_at: str) -> str:
    escaped_prompt = html.escape(agent_prompt)
    generated_label = html.escape(generated_at)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Aerin Resource Portal Search</title>
    <meta name="description" content="Human-friendly context and Resource Portal article search for the Aerin agent instructions.">
    <link rel="icon" href="/favicon.svg" type="image/svg+xml">
    <link rel="stylesheet" href="/styles.css">
  </head>
  <body class="human-page">
    <header class="agent-bar">
      <a class="agent-brand" href="/">Aerin Agent Instructions</a>
      <nav aria-label="Instruction views">
        <a href="/">Agent view</a>
        <a href="/agent-instructions.md">Raw Markdown</a>
      </nav>
    </header>
    <main class="human-shell">
      <section class="intro">
        <img class="mark" src="https://cdn.document360.io/9719bbba-a475-4103-9bd6-3384758a9ea2/Images/Documentation/AntiEntropy_icon_fullcolor.png" alt="Anti Entropy">
        <p class="eyebrow">Anti Entropy Resource Portal</p>
        <h1>Human view</h1>
        <p class="lede">The root domain is optimized for agents to read as instructions. This page gives humans the searchable Resource Portal context, endpoint examples, and the generated prompt.</p>
        <dl class="facts">
          <div><dt>Agent view</dt><dd><code>/</code></dd></div>
          <div><dt>Search endpoint</dt><dd><code>/query?q=uk%20contractor%20classification</code></dd></div>
          <div><dt>Catalog endpoint</dt><dd><code>/catalog</code></dd></div>
          <div><dt>Indexed articles</dt><dd>{article_count}</dd></div>
        </dl>
      </section>

      <section class="search-panel" aria-labelledby="search-title">
        <div>
          <p class="eyebrow">Article lookup</p>
          <h2 id="search-title">Search full Resource Portal articles</h2>
        </div>
        <form id="search-form" role="search">
          <label for="query">Query</label>
          <div class="search-row">
            <input id="query" name="q" type="search" value="uk contractor classification" autocomplete="off">
            <button type="submit">Search</button>
          </div>
        </form>
        <p class="hint">The agent endpoint returns plain text. This form uses JSON to make the same results easier to scan.</p>
        <div id="results" class="results" aria-live="polite"></div>
      </section>

      <section class="prompt-section" aria-labelledby="prompt-title">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Hosted prompt</p>
            <h2 id="prompt-title">Instructions Markdown</h2>
          </div>
          <a href="/agent-instructions.md">Open raw Markdown</a>
        </div>
        <pre class="prompt"><code>{escaped_prompt}</code></pre>
      </section>
    </main>
    <footer>
      <span>Generated from the Google Doc prompt and Resource Portal crawl.</span>
      <span>{generated_label}</span>
    </footer>
    <script src="/app.js"></script>
  </body>
</html>
"""


def main() -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    data = build_articles()
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    original_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    agent_prompt = build_agent_prompt(original_prompt, data["articleCount"])
    PUBLIC_PROMPT_PATH.write_text(agent_prompt + "\n", encoding="utf-8")
    INDEX_PATH.write_text(
        build_agent_index_html(agent_prompt, data["articleCount"], data["generatedAt"]),
        encoding="utf-8",
    )
    HUMAN_PATH.write_text(
        build_human_html(agent_prompt, data["articleCount"], data["generatedAt"]),
        encoding="utf-8",
    )

    print(
        f"Indexed {data['articleCount']} articles"
        f" ({data['failedCount']} failures) -> {DATA_PATH.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()

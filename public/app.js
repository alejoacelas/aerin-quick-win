const form = document.querySelector("#search-form");
const input = document.querySelector("#query");
const results = document.querySelector("#results");

function resultTemplate(result, index) {
  const keywords = result.keywords && result.keywords.length ? result.keywords.join(", ") : "none";
  const category = result.categoryPath && result.categoryPath.length ? result.categoryPath.join(" > ") : "Uncategorized";
  const alternates = result.alternateSlugs && result.alternateSlugs.length ? result.alternateSlugs.join(", ") : "none";
  const content = result.contentText || "No article text indexed.";
  const title = escapeHtml(result.title || "Untitled article");
  const url = escapeAttribute(safeUrl(result.url));
  const description = escapeHtml(result.description || "");
  return `
    <article class="result">
      <div class="result-heading">
        <span>${index + 1}</span>
        <div>
          <h3><a href="${url}" target="_blank" rel="noreferrer">${title}</a></h3>
          <p>${description}</p>
        </div>
      </div>
      <dl>
        <div><dt>Score</dt><dd>${escapeHtml(result.score)}</dd></div>
        <div><dt>Category</dt><dd>${escapeHtml(category)}</dd></div>
        <div><dt>Also indexed as</dt><dd>${escapeHtml(alternates)}</dd></div>
        <div><dt>Keywords</dt><dd>${escapeHtml(keywords)}</dd></div>
      </dl>
      <details>
        <summary>Full article text</summary>
        <pre>${escapeHtml(content)}</pre>
      </details>
    </article>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

function safeUrl(value) {
  try {
    const url = new URL(String(value || ""), window.location.origin);
    if (url.protocol === "http:" || url.protocol === "https:") return url.href;
  } catch {
    // Fall through to an inert link.
  }
  return "#";
}

async function runSearch(query) {
  results.innerHTML = '<p class="status">Searching...</p>';
  const response = await fetch(`/api/search?format=json&q=${encodeURIComponent(query)}&limit=5`);
  if (!response.ok) {
    results.innerHTML = '<p class="status error">Search failed.</p>';
    return;
  }
  const payload = await response.json();
  if (!payload.results.length) {
    results.innerHTML = '<p class="status">No matching articles. Try broader keywords or use /catalog.</p>';
    return;
  }
  results.innerHTML = payload.results.map(resultTemplate).join("");
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = input.value.trim();
  if (query) runSearch(query);
});

runSearch(input.value.trim());

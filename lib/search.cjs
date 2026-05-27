const fs = require("fs");
const path = require("path");

const DATA_PATH = path.join(process.cwd(), "data", "articles.json");

const STOP_WORDS = new Set([
  "a",
  "an",
  "and",
  "are",
  "as",
  "at",
  "be",
  "by",
  "for",
  "from",
  "how",
  "i",
  "in",
  "is",
  "it",
  "of",
  "on",
  "or",
  "our",
  "the",
  "to",
  "us",
  "we",
  "what",
  "with",
  "you",
  "your",
]);

const EXPANSIONS = {
  "501c3": ["501(c)(3)", "charity", "tax-exempt", "irs", "form", "1023"],
  "501": ["501(c)(3)", "charity", "tax-exempt", "irs", "form", "1023"],
  accomodation: ["accommodation", "reasonable", "ada", "disability"],
  accommodation: ["reasonable", "ada", "disability", "pregnancy", "religious"],
  board: ["governance", "directors", "trustees", "fiduciary"],
  charity: ["nonprofit", "501(c)(3)", "tax-exempt", "charitable"],
  charities: ["nonprofit", "501(c)(3)", "tax-exempt", "charitable"],
  contractor: ["independent", "freelancer", "self-employed", "worker", "classification"],
  contractors: ["independent", "freelancer", "self-employed", "worker", "classification"],
  donation: ["donor", "fundraising", "Every.org", "grant"],
  employee: ["employment", "worker", "staff", "handbook", "hr"],
  employees: ["employment", "worker", "staff", "handbook", "hr"],
  gdpr: ["privacy", "data", "protection", "notice", "uk", "eu"],
  grant: ["grants", "funder", "funds", "expenditure", "responsibility"],
  grants: ["grant", "funder", "funds", "expenditure", "responsibility"],
  harassment: ["bullying", "misconduct", "discrimination", "retaliation"],
  hiring: ["employment", "contractor", "worker", "classification", "onboarding"],
  nonprofit: ["charity", "501(c)(3)", "tax-exempt", "fiscal", "sponsorship"],
  nonprofits: ["charity", "501(c)(3)", "tax-exempt", "fiscal", "sponsorship"],
  payments: ["payment", "invoice", "contractor", "expense", "reimbursement"],
  policy: ["template", "handbook", "procedure"],
  policies: ["template", "handbook", "procedure"],
  sparkwell: ["fiscal", "sponsorship", "project", "anti", "entropy"],
  tax: ["irs", "hmrc", "filing", "return", "ein"],
  uk: ["united", "kingdom", "british", "hmrc", "charity", "commission"],
  "u.k.": ["uk", "united", "kingdom", "british", "hmrc"],
  usa: ["us", "united", "states", "irs", "federal"],
  visa: ["immigration", "sponsor", "worker", "skilled"],
  visas: ["immigration", "sponsor", "worker", "skilled"],
};

let cache = null;

function loadData() {
  if (!cache) {
    cache = JSON.parse(fs.readFileSync(DATA_PATH, "utf8"));
  }
  return cache;
}

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function tokenize(value) {
  return normalize(value)
    .replace(/[^a-z0-9]+/g, " ")
    .split(/\s+/)
    .filter((token) => token && !STOP_WORDS.has(token));
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function expandTokens(tokens) {
  const expanded = [...tokens];
  for (const token of tokens) {
    const additions = EXPANSIONS[token];
    if (additions) expanded.push(...additions.flatMap(tokenize));
  }
  return unique(expanded);
}

function countOccurrences(haystack, needle) {
  if (!needle) return 0;
  return tokenize(haystack).filter((token) => tokenMatches(token, needle)).length;
}

function tokenMatches(actual, wanted) {
  if (actual === wanted) return true;
  if (wanted.length > 3 && actual === `${wanted}s`) return true;
  if (wanted.endsWith("s") && wanted.length > 4 && actual === wanted.slice(0, -1)) return true;
  return false;
}

function fieldText(article, field) {
  if (Array.isArray(article[field])) return article[field].join(" ");
  return String(article[field] || "");
}

function scoreArticle(article, query, rawTokens, expandedTokens) {
  const fields = [
    ["title", 18],
    ["slug", 12],
    ["alternateSlugs", 8],
    ["description", 10],
    ["keywords", 9],
    ["tags", 8],
    ["categoryPath", 5],
    ["contentText", 2],
  ];
  const normalizedQuery = normalize(query).trim();
  let score = 0;
  const reasons = [];

  for (const [field, weight] of fields) {
    const raw = fieldText(article, field);
    const text = normalize(raw);
    if (!text) continue;

    if (normalizedQuery.length > 2 && text.includes(normalizedQuery)) {
      score += weight * 10;
      reasons.push(`${field}: exact phrase`);
    }

    for (const token of rawTokens) {
      const occurrences = countOccurrences(text, token);
      if (occurrences > 0) {
        score += weight * Math.min(4, Math.sqrt(occurrences));
      }
    }

    for (const token of expandedTokens) {
      if (rawTokens.includes(token)) continue;
      const occurrences = countOccurrences(text, token);
      if (occurrences > 0) {
        score += weight * 0.35 * Math.min(3, Math.sqrt(occurrences));
      }
    }
  }

  const titleTokens = tokenize(article.title);
  const matchedTitleTokens = rawTokens.filter((token) =>
    titleTokens.some((titleToken) => tokenMatches(titleToken, token))
  );
  if (matchedTitleTokens.length) {
    score += matchedTitleTokens.length * 60;
    reasons.push(`title terms: ${matchedTitleTokens.join(", ")}`);
  }

  const highSignalText = [
    article.title,
    article.slug,
    ...(article.alternateSlugs || []),
    article.description,
    ...(article.keywords || []),
    ...(article.tags || []),
    ...(article.categoryPath || []),
  ].join(" ");
  const highSignalMatches = rawTokens.filter((token) => countOccurrences(highSignalText, token) > 0);
  if (highSignalMatches.length) {
    score += highSignalMatches.length * 30;
    if (highSignalMatches.length === rawTokens.length) {
      score += 45;
      reasons.push("all query terms in title/description/keywords");
    }
  }

  const contentLengthPenalty = Math.log10(Math.max(1000, String(article.contentText || "").length)) * 0.5;
  return {
    score: Math.round((score - contentLengthPenalty) * 100) / 100,
    reasons: unique(reasons).slice(0, 4),
  };
}

function searchArticles(query, options = {}) {
  const data = loadData();
  const requestedLimit = Number(options.limit || 5);
  const limit = Number.isFinite(requestedLimit) ? Math.max(1, Math.min(requestedLimit, 20)) : 5;
  const rawTokens = tokenize(query);
  const expandedTokens = expandTokens(rawTokens);

  if (!rawTokens.length) {
    return {
      query,
      total: 0,
      generatedAt: data.generatedAt,
      articleCount: data.articleCount,
      results: [],
    };
  }

  const results = data.articles
    .map((article) => {
      const scored = scoreArticle(article, query, rawTokens, expandedTokens);
      return { ...article, ...scored };
    })
    .filter((article) => article.score > 0)
    .sort((a, b) => b.score - a.score || a.title.localeCompare(b.title))
    .slice(0, limit);

  return {
    query,
    total: results.length,
    generatedAt: data.generatedAt,
    articleCount: data.articleCount,
    results,
  };
}

function formatSearchText(payload) {
  const lines = [
    "Anti Entropy Resource Portal search",
    `Query: ${payload.query || "(none)"}`,
    `Indexed articles: ${payload.articleCount}`,
    `Index generated: ${payload.generatedAt}`,
    "",
  ];

  if (!payload.query || !tokenize(payload.query).length) {
    lines.push(
      "Pass a query with /query?q=your%20keywords.",
      "Use /query?q=your%20keywords&limit=2 to reduce response size.",
      "",
      "Useful examples:",
      "- /query?q=uk%20contractor%20classification",
      "- /query?q=uk%20contractor%20classification&limit=2",
      "- /query?q=SparkWell%20contractor%20payments",
      "- /query?q=501c3%20charity%20status",
      "- /query?q=GDPR%20privacy%20notice",
      "",
      "Use /catalog to browse titles, descriptions, and keywords."
    );
    return lines.join("\n");
  }

  if (!payload.results.length) {
    lines.push(
      "No results found.",
      "",
      "Try fewer words, a jurisdiction, a program name, or /catalog for available topics."
    );
    return lines.join("\n");
  }

  payload.results.forEach((article, index) => {
    lines.push(
      `# ${index + 1}. ${article.title}`,
      `URL: ${article.url}`,
      `Slug: ${article.slug}`,
      article.alternateSlugs && article.alternateSlugs.length
        ? `Alternate slugs: ${article.alternateSlugs.join(", ")}`
        : "",
      `Score: ${article.score}`,
      `Category: ${(article.categoryPath || []).join(" > ") || "Uncategorized"}`,
      `Description: ${article.description || "(none)"}`,
      `Keywords: ${(article.keywords || []).join(", ") || "(none)"}`,
      article.reasons && article.reasons.length ? `Matched: ${article.reasons.join("; ")}` : "",
      "",
      "Article:",
      article.contentText || "(no article text indexed)",
      "",
      "---",
      ""
    );
  });

  return lines.join("\n");
}

function catalogPayload() {
  const data = loadData();
  return {
    generatedAt: data.generatedAt,
    articleCount: data.articleCount,
    articles: data.articles.map((article) => ({
      title: article.title,
      slug: article.slug,
      url: article.url,
      description: article.description,
      keywords: article.keywords || [],
      categoryPath: article.categoryPath || [],
      alternateSlugs: article.alternateSlugs || [],
    })),
  };
}

function formatCatalogText(payload = catalogPayload()) {
  const lines = [
    "Anti Entropy Resource Portal catalog",
    `Indexed articles: ${payload.articleCount}`,
    `Index generated: ${payload.generatedAt}`,
    "",
    "Use /query?q=... to retrieve full article text for matching articles.",
    "",
  ];

  payload.articles.forEach((article) => {
    lines.push(
      `- ${article.title}`,
      `  Slug: ${article.slug}`,
      article.alternateSlugs && article.alternateSlugs.length
        ? `  Alternate slugs: ${article.alternateSlugs.join(", ")}`
        : "",
      `  URL: ${article.url}`,
      `  Category: ${(article.categoryPath || []).join(" > ") || "Uncategorized"}`,
      `  Description: ${article.description || "(none)"}`,
      `  Keywords: ${(article.keywords || []).join(", ") || "(none)"}`,
      ""
    );
  });

  return lines.join("\n");
}

module.exports = {
  catalogPayload,
  formatCatalogText,
  formatSearchText,
  loadData,
  searchArticles,
  tokenize,
};

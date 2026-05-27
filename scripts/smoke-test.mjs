import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { catalogPayload, searchArticles } = require("../lib/search.cjs");

const catalog = catalogPayload();
assert.ok(catalog.articleCount > 100, `expected a substantial catalog, got ${catalog.articleCount}`);

const cases = [
  {
    query: "uk contractor classification",
    expected: ["employer-independent-contractor-guidance-uk", "uk-workers-vs-independent-contractors"],
  },
  {
    query: "SparkWell contractor payments",
    expected: ["key-information-for-sparkwell-contractors", "sparkwell-guidance-for-setting-up-a-new-contractor"],
  },
  {
    query: "EIN nonprofit",
    expected: ["applying-for-an-ein"],
  },
  {
    query: "GDPR privacy notice",
    expected: ["template-privacy-notice", "gdpr-compliance-guide"],
  },
];

for (const testCase of cases) {
  const payload = searchArticles(testCase.query, { limit: 5 });
  const slugs = payload.results.map((result) => result.slug);
  assert.ok(payload.results.length > 0, `no results for ${testCase.query}`);
  assert.ok(
    testCase.expected.some((slug) => slugs.includes(slug)),
    `expected one of ${testCase.expected.join(", ")} for "${testCase.query}", got ${slugs.join(", ")}`
  );
}

const invalidLimitPayload = searchArticles("uk contractor classification", { limit: "invalid" });
assert.ok(invalidLimitPayload.results.length > 0, "invalid limits should fall back to the default");

const agentPage = readFileSync("public/index.html", "utf8");
const humanPage = readFileSync("public/human.html", "utf8");
const agentPrompt = readFileSync("public/llm.md", "utf8");
assert.match(agentPage, /If you are an AI assistant/, "root page should lead with agent guidance");
assert.doesNotMatch(agentPage, /id="search-form"/, "root page should not include the human search UI");
assert.match(humanPage, /id="search-form"/, "human page should include the search UI");
assert.doesNotMatch(agentPage, /agent-instructions\.md/, "root page should point raw Markdown links at /llm");
assert.doesNotMatch(humanPage, /agent-instructions\.md/, "human page should point raw Markdown links at /llm");
assert.ok(agentPrompt.startsWith("\\<guidance\\>"), "agent prompt should start with guidance, not frontmatter");
assert.doesNotMatch(agentPrompt, /gdoc:|title: \[DEFAULT\]/, "agent prompt should omit Google Doc frontmatter");
assert.match(agentPrompt, /\n\nUSERS\n\n/, "agent prompt should preserve readable section breaks");

console.log(`Smoke tests passed against ${catalog.articleCount} indexed articles.`);

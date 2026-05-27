import assert from "node:assert/strict";
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

console.log(`Smoke tests passed against ${catalog.articleCount} indexed articles.`);

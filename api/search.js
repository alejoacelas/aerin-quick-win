const { formatSearchText, searchArticles } = require("../lib/search.cjs");

module.exports = function handler(req, res) {
  const query = String(req.query.q || req.query.query || "").trim();
  const limit = req.query.limit ? Number(req.query.limit) : 5;
  const payload = searchArticles(query, { limit });

  res.setHeader("Cache-Control", "public, s-maxage=300, stale-while-revalidate=86400");

  if (req.query.format === "json") {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(200).json(payload);
    return;
  }

  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.status(200).send(formatSearchText(payload));
};

const { catalogPayload, formatCatalogText } = require("../lib/search.cjs");

module.exports = function handler(req, res) {
  const payload = catalogPayload();
  res.setHeader("Cache-Control", "public, s-maxage=300, stale-while-revalidate=86400");

  if (req.query.format === "json") {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(200).json(payload);
    return;
  }

  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.status(200).send(formatCatalogText(payload));
};

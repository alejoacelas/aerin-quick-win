# Aerin Quick Win

Small Vercel-friendly site that hosts the Aerin/Anti Entropy agent prompt and exposes an agent-readable Resource Portal search endpoint.

## Endpoints

- `/` - simple human page with the hosted prompt and a search form.
- `/agent-instructions.md` - raw Markdown prompt for agents.
- `/query?q=uk%20contractor%20classification` - plain-text search response with full article text.
- `/query?q=uk%20contractor%20classification&limit=2` - smaller plain-text response.
- `/catalog` - plain-text catalog of indexed Resource Portal articles.
- `/api/search?format=json&q=...` - JSON version used by the UI.

## Local Development

```sh
yarn refresh
yarn test
yarn dev
```

The crawler reads the pulled Google Doc prompt from `content/anti-entropy-agent-prompt.md`, crawls public Document360 article pages, collapses exact duplicate article bodies, writes `data/articles.json`, and regenerates the hosted prompt/page in `public/`.

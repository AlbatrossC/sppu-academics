# sppu-pyqs-db

Cloudflare Worker + D1 backend for the static `sppupyqs` site.

It handles:

- `POST /contact`
- `POST /api/contact`
- `POST /api/notify-download`
- `POST /notify-download`

## Local setup

```bash
cd shared/workers/sppu-pyqs-db
npm install
npm run types
npm run check
npm run dev
```

## D1 setup

Create the database:

```bash
npx wrangler d1 create sppu-pyqs-db
```

Copy the generated `database_id` into `wrangler.toml`, then apply the schema:

```bash
npx wrangler d1 execute sppu-pyqs-db --local --file=./schema.sql
npx wrangler d1 execute sppu-pyqs-db --remote --file=./schema.sql
```

## Secrets

Discord notifications are optional. To enable them:

```bash
npx wrangler secret put DISCORD_WEBHOOK_URL
```

## Manual deploy

```bash
npm run deploy
```

This Worker is intentionally separate from `shared/workers/sppu-pyqs`, which serves existing PDF/R2 behavior.

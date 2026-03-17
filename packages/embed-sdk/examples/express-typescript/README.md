# Express TypeScript Example

Last Updated: 2026-03-17

This example shows the intended v1 architecture for `@agents24/embed-sdk`:

- customer frontend sends requests to the customer backend
- customer backend uses `@agents24/embed-sdk`
- the Talmudpedia API key stays only on the backend

## Run Locally

1. Install dependencies:

```bash
npm install
```

If you are running this example from the repo before the first public npm release, build the package first:

```bash
cd ../../
npm install
npm run build
cd examples/express-typescript
```

2. Set environment variables from `.env.example`.

3. Start the server:

```bash
npm run dev
```

## Frontend Rule

Do not import `@agents24/embed-sdk` in the browser. Your frontend should call the routes in `src/server.ts`, and only that backend should talk to Talmudpedia.

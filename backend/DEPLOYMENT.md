# Heroku Deployment Guide

## Prerequisites

1. Heroku CLI installed and logged in
2. Git repository initialized
3. Heroku app created (or will be created during deployment)

## Deployment Steps

### 1. Create Heroku App

```bash
cd backend
heroku create your-app-name
```

### 2. Set Environment Variables

#### Option A: Upload from .env file (Recommended)

Use the provided script to automatically upload all variables from your `.env` file:

```bash
cd backend
python scripts/upload_env_to_heroku.py your-app-name
```

Or if you haven't specified an app name yet:
```bash
python scripts/upload_env_to_heroku.py
```


### 3. Deploy to Heroku

```bash
git add .
git commit -m "Prepare for Heroku deployment"
git push heroku main
```

Or if deploying from a different branch:

```bash
git push heroku your-branch:main
```

### 4. Verify Deployment

```bash
heroku logs --tail
heroku open
```

Visit `https://your-app-name.herokuapp.com/health` to verify the app is running.

## Frontend Configuration

### Environment Variables

Create a `.env.local` file in the `frontend/` directory:

```bash
# frontend/.env.local
NEXT_PUBLIC_BACKEND_URL=https://your-app-name.herokuapp.com
```

This tells the frontend where to send API requests to your Heroku backend.

### Running Locally

To run the frontend locally while connecting to the Heroku backend:

1. Make sure the `.env.local` file exists with your Heroku backend URL
2. Start the frontend:
   ```bash
   cd frontend
   npm run dev
   ```

The frontend will automatically use the `NEXT_PUBLIC_BACKEND_URL` environment variable for API calls.

## Required Environment Variables


## Elasticsearch Hosting Options

Since you use Elasticsearch for lexical search (combined with Pinecone for hybrid retrieval), you need to host it separately. Here are your options:

### Option 1: Elastic Cloud (Recommended - Easiest)

1. Sign up at [elastic.co/cloud](https://www.elastic.co/cloud)
2. Create a deployment (free trial available)
3. Get your Cloud ID and API key from the dashboard
4. Set environment variables:
   ```bash
   heroku config:set ELASTICSEARCH_URL="https://your-deployment.es.us-central1.gcp.cloud.es.io:9243"
   heroku config:set ELASTICSEARCH_API_KEY="your-api-key"
   ```

**Pros**: Managed service, easy setup, free trial, scales automatically
**Cons**: Costs money after trial (but reasonable pricing)

### Option 2: AWS Elasticsearch Service

1. Create an Elasticsearch domain in AWS
2. Configure security (IP-based or VPC)
3. Get the endpoint URL and create API keys
4. Set environment variables:
   ```bash
   heroku config:set ELASTICSEARCH_URL="https://your-domain.us-east-1.es.amazonaws.com"
   heroku config:set ELASTICSEARCH_API_KEY="your-api-key"
   ```

**Pros**: Integrates with AWS ecosystem
**Cons**: More complex setup, need to configure security properly

### Option 3: Self-Hosted on Cloud Provider

You can run Elasticsearch on:
- **Google Cloud Platform**: Use Compute Engine with Elasticsearch
- **DigitalOcean**: Managed Elasticsearch or Droplet
- **Railway/Render**: Some platforms offer Elasticsearch

**Pros**: Full control, potentially cheaper at scale
**Cons**: You manage updates, backups, scaling

### Option 4: Make Elasticsearch Optional

If you want to deploy without Elasticsearch initially, the app will work with just Pinecone (semantic search only). The hybrid retriever will fall back to semantic-only if Elasticsearch is not configured.

To make it optional, ensure your code handles missing `ELASTICSEARCH_URL` gracefully (which it should based on the codebase).

## Notes

- The app will automatically use the `PORT` environment variable set by Heroku
- CORS origins can be configured via `CORS_ORIGINS` environment variable
- Make sure your MongoDB database is accessible from Heroku's IP addresses
- Consider using Heroku Postgres or MongoDB Atlas for production databases
- For production, ensure `SECRET_KEY` is a strong, randomly generated string
- **Elasticsearch is optional** - your app will work with just Pinecone, but hybrid search (lexical + semantic) provides better results

## Troubleshooting

### Check logs
```bash
heroku logs --tail
```

### Run commands in Heroku environment
```bash
heroku run python
```

### Check environment variables
```bash
heroku config
```

### Scale dynos (if needed)
```bash
heroku ps:scale web=1
```


# Azure Deployment

This is the Azure replacement for the current DigitalOcean App Platform shape.
Use Azure Container Apps because AutoReach is not just one web server. Production
needs three always-running processes:

- web: FastAPI + built React Cockpit at `/app/`
- worker: Celery worker on `engine,maintenance,standard-agents`
- beat: one Celery scheduler

The same `Dockerfile` is used for all three Container Apps. The web app uses the
Dockerfile default command. Worker and beat override the startup command.

Repo scaffolding now lives in `azure.yaml` and `infra/main.bicep`.

## Target Azure Architecture

```text
Browser
  |
  v
Azure Container Apps: autoreach-web
  |
  +--> Azure Database for PostgreSQL Flexible Server
  |
  +--> Existing Redis/Valkey endpoint via REDIS_URL
          |
          +--> autoreach-worker
          +--> autoreach-beat

Azure Container Registry stores the Docker image.
Log Analytics stores Container Apps logs.
```

The current Bicep template does not provision Redis. It accepts a secure
`redisUrlOverride` parameter because Redis SKU availability varies by
subscription and region. Any Redis/Valkey endpoint works as long as `REDIS_URL`
is a TLS Redis URL compatible with Celery/Kombu.

The first Azure launch used:

- Resource group: `attainly-prod-swedencentral-rg`
- Region: `swedencentral`
- Web URL: `https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/`
- Cockpit URL: `https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/app/`
- Temporary Redis: existing East US Azure Cache for Redis in `attainly-prod-rg`

## 1. Local Prerequisites

Install and log in:

```bash
az login
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.ContainerRegistry
```

Set names:

```bash
export AZURE_LOCATION=eastus
export AZURE_RESOURCE_GROUP=autoreach-prod-rg
export AZURE_CONTAINER_ENV=autoreach-prod-env
export AZURE_ACR_NAME=autoreachprodacr
export AZURE_WEB_APP=autoreach-web
export AZURE_WORKER_APP=autoreach-worker
export AZURE_BEAT_APP=autoreach-beat
```

Create the resource group, registry, and Container Apps environment:

```bash
az group create \
  --name "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION"

az acr create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$AZURE_ACR_NAME" \
  --sku Basic

az containerapp env create \
  --name "$AZURE_CONTAINER_ENV" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION"
```

## 2. Build And Push The Initial Image

```bash
ACR_LOGIN_SERVER="$(az acr show \
  --name "$AZURE_ACR_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query loginServer \
  --output tsv)"

az acr login --name "$AZURE_ACR_NAME"


docker build -t "$ACR_LOGIN_SERVER/autoreach:initial" .
docker push "$ACR_LOGIN_SERVER/autoreach:initial"

export AUTOREACH_IMAGE="$ACR_LOGIN_SERVER/autoreach:initial"
```

## 3. Provision Postgres

Create Azure Database for PostgreSQL Flexible Server from the Azure portal or
Azure CLI. The app expects one `DATABASE_URL` value.

Use this format:

```text
postgresql://POSTGRES_USER:POSTGRES_PASSWORD@POSTGRES_HOST:5432/autoreach?sslmode=require
```

Azure PostgreSQL requires TLS by default, so keep `sslmode=require`.

For the first launch, public networking is the easiest path. Restrict firewall
rules after the app is live. For a real production launch, move Container Apps,
Postgres, and Redis behind private networking.

## 4. Provide Redis

The app expects one `REDIS_URL` value.

Use this format:

```text
rediss://:REDIS_KEY@REDIS_HOST:6380/0
```

The app already normalizes `rediss://` URLs for Celery/Kombu TLS.

When using `infra/main.bicep`, pass this value as the secure
`redisUrlOverride` parameter. Do not leave it blank; worker and beat require it.

## 5. Generate Internal Secrets

```bash
python3 scripts/live_ops_launch.py generate-secrets --dotenv
```

You need:

- `AUTOREACH_JWT_SECRET`
- `AUTOREACH_SESSION_SECRET`
- `AUTOREACH_CREDENTIAL_ENCRYPTION_KEY`

Also prepare:

- `DATABASE_URL`
- `REDIS_URL`
- `GEMINI_API_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_SIGNIN_CLIENT_ID`
- `CALCOM_WEBHOOK_SECRET`
- `AUTOREACH_PHOENIX_ENDPOINT`
- `SENTRY_DSN`

Keep secrets in Azure Container Apps secrets or Azure Key Vault. Do not commit
them to the repo.

The Bicep template deploys optional API/vendor secrets only when a non-empty
parameter value is provided. This allows infrastructure to go live before Google,
Gemini, Cal.com, Phoenix, Sentry, and billing keys are ready.

## 6. Create The Three Container Apps

For the first version, enable ACR admin credentials so Container Apps can pull
the image. Later, replace this with managed identity based ACR pull.

```bash
az acr update --name "$AZURE_ACR_NAME" --admin-enabled true

ACR_USERNAME="$(az acr credential show \
  --name "$AZURE_ACR_NAME" \
  --query username \
  --output tsv)"

ACR_PASSWORD="$(az acr credential show \
  --name "$AZURE_ACR_NAME" \
  --query passwords[0].value \
  --output tsv)"
```

Create the web app:

```bash
az containerapp create \
  --name "$AZURE_WEB_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --environment "$AZURE_CONTAINER_ENV" \
  --image "$AUTOREACH_IMAGE" \
  --target-port 8080 \
  --ingress external \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD"
```

Create the worker app:

```bash
az containerapp create \
  --name "$AZURE_WORKER_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --environment "$AZURE_CONTAINER_ENV" \
  --image "$AUTOREACH_IMAGE" \
  --command celery \
  --args "-A" "celery_worker.celery_app" "worker" "--loglevel=info" "--concurrency=2" "-Q" "engine,maintenance,standard-agents" \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 2 \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD"
```

Create the beat app:

```bash
az containerapp create \
  --name "$AZURE_BEAT_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --environment "$AZURE_CONTAINER_ENV" \
  --image "$AUTOREACH_IMAGE" \
  --command celery \
  --args "-A" "celery_worker.celery_app" "beat" "--loglevel=info" \
  --cpu 0.25 \
  --memory 0.5Gi \
  --min-replicas 1 \
  --max-replicas 1 \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD"
```

Important: keep beat at exactly one replica unless scheduler locking is added.

## 7. Set Runtime Configuration

Set non-secret values on all three apps:

```bash
for app in "$AZURE_WEB_APP" "$AZURE_WORKER_APP" "$AZURE_BEAT_APP"; do
  az containerapp update \
    --name "$app" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --set-env-vars \
      AUTOREACH_ENABLE_CONSOLE=0 \
      AUTOREACH_RUNTIME_SMART_DISPATCH=1 \
      AUTOREACH_WORKER_QUEUES=engine,maintenance,standard-agents \
      AUTOREACH_INTENT_HOURS_BACK=24
done
```

Add secrets per app, then reference them as env vars. Example for the web app:

```bash
az containerapp secret set \
  --name "$AZURE_WEB_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --secrets \
    database-url="$DATABASE_URL" \
    redis-url="$REDIS_URL" \
    jwt-secret="$AUTOREACH_JWT_SECRET" \
    session-secret="$AUTOREACH_SESSION_SECRET" \
    credential-key="$AUTOREACH_CREDENTIAL_ENCRYPTION_KEY" \
    gemini-api-key="$GEMINI_API_KEY" \
    google-client-id="$GOOGLE_CLIENT_ID" \
    google-client-secret="$GOOGLE_CLIENT_SECRET" \
    google-signin-client-id="$GOOGLE_SIGNIN_CLIENT_ID" \
    calcom-webhook-secret="$CALCOM_WEBHOOK_SECRET"

az containerapp update \
  --name "$AZURE_WEB_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --set-env-vars \
    DATABASE_URL=secretref:database-url \
    REDIS_URL=secretref:redis-url \
    AUTOREACH_JWT_SECRET=secretref:jwt-secret \
    AUTOREACH_SESSION_SECRET=secretref:session-secret \
    AUTOREACH_CREDENTIAL_ENCRYPTION_KEY=secretref:credential-key \
    GEMINI_API_KEY=secretref:gemini-api-key \
    GOOGLE_CLIENT_ID=secretref:google-client-id \
    GOOGLE_CLIENT_SECRET=secretref:google-client-secret \
    GOOGLE_SIGNIN_CLIENT_ID=secretref:google-signin-client-id \
    CALCOM_WEBHOOK_SECRET=secretref:calcom-webhook-secret
```

Repeat the required shared secrets for worker and beat:

- worker: `DATABASE_URL`, `REDIS_URL`, `AUTOREACH_JWT_SECRET`,
  `AUTOREACH_CREDENTIAL_ENCRYPTION_KEY`, `GEMINI_API_KEY`,
  `AUTOREACH_PHOENIX_ENDPOINT`, `AUTOREACH_INTENT_DUCKDB_PATH`
- beat: `DATABASE_URL`, `REDIS_URL`,
  `AUTOREACH_CREDENTIAL_ENCRYPTION_KEY`

After the web app is created, get its URL:

```bash
AZURE_WEB_FQDN="$(az containerapp show \
  --name "$AZURE_WEB_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn \
  --output tsv)"

export AUTOREACH_PUBLIC_BASE_URL="https://$AZURE_WEB_FQDN"

az containerapp update \
  --name "$AZURE_WEB_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --set-env-vars AUTOREACH_PUBLIC_BASE_URL="$AUTOREACH_PUBLIC_BASE_URL"
```

## 8. Configure GitHub Actions Deployment

The repo includes:

```text
.github/workflows/azure_container_apps.yml
```

Add these GitHub Actions secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_CONTAINER_REGISTRY`
- `AZURE_WEB_CONTAINER_APP`
- `AZURE_WORKER_CONTAINER_APP`
- `AZURE_BEAT_CONTAINER_APP`

Use GitHub OIDC with `azure/login`. Do not store your Azure user password in
GitHub.

Run the workflow manually from GitHub Actions after the initial Azure resources
exist. It builds the Docker image, pushes it to ACR, and updates the three
Container Apps.

## 9. OAuth And Webhooks

Update Google OAuth redirect URI:

```text
https://AZURE_WEB_FQDN/api/mailboxes/connect/callback
```

If using Google login, set:

```bash
GOOGLE_SIGNIN_CLIENT_ID=...
```

Update Cal.com webhook:

```text
https://AZURE_WEB_FQDN/webhooks/calcom/booking
```

Booking metadata must include:

- `tenant_id`
- `engagement_id` or `campaign_id`

## 10. Verify The Azure App

```bash
curl -s "$AUTOREACH_PUBLIC_BASE_URL/healthz"
curl -s "$AUTOREACH_PUBLIC_BASE_URL/readyz"
curl -s "$AUTOREACH_PUBLIC_BASE_URL/readyz?deep=true"
```

Then run:

```bash
python3 scripts/live_ops_launch.py plan \
  --base-url "$AUTOREACH_PUBLIC_BASE_URL" \
  --smoke-email smoke@example.com \
  --strict
```

If a real domain is configured:

```bash
python3 scripts/live_ops_launch.py plan \
  --base-url "$AUTOREACH_PUBLIC_BASE_URL" \
  --domain yourdomain.com \
  --smoke-email smoke@yourdomain.com \
  --strict
```

Finally:

```bash
python3 scripts/production_smoke.py \
  --base-url "$AUTOREACH_PUBLIC_BASE_URL" \
  --email smoke@example.com \
  --password "$AUTOREACH_SMOKE_PASSWORD" \
  --company "Smoke Tenant" \
  --calcom-webhook-secret "$CALCOM_WEBHOOK_SECRET" \
  --exercise-scoped-booking-webhook \
  --secret-denylist "$AUTOREACH_JWT_SECRET,$AUTOREACH_SESSION_SECRET,$CALCOM_WEBHOOK_SECRET"
```

## Azure Launch Gate

Do not call the migration complete until:

- web app serves `/app/`
- `/healthz` is green
- `/readyz?deep=true` confirms DB, Redis, and Celery worker queues
- worker logs show it is consuming `engine,maintenance,standard-agents`
- beat logs show exactly one scheduler is running
- Google OAuth redirect is updated
- Cal.com webhook is updated
- `AUTOREACH_ENABLE_CONSOLE=0`
- `AUTOREACH_RUNTIME_SMART_DISPATCH=1`
- production smoke passes

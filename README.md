# 🍳 BiteRig

**Snap your ingredients → AI generates your recipe.**

BiteRig uses multimodal AI (GitHub Models + `openai/o4-mini`) to analyse a photo of your food ingredients and generate a detailed, step-by-step recipe — with optional dietary filters and cuisine nationality preferences.

---

## Project Structure

```
BiteRig/
├── backend/                 ← FastAPI Python backend
│   ├── main.py              ← API entry point (/api/cook, /api/health)
│   ├── services/
│   │   └── llm.py           ← GitHub AI inference recipe generator
│   ├── .env                 ← Local secrets (gitignored)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                ← Pure HTML/CSS/JS single-page app
│   ├── index.html           ← 3 views: Home, Loading, Recipe
│   ├── style.css            ← Custom animations & effects
│   ├── app.js               ← SPA logic (camera, API, rendering)
│   ├── config.js            ← Backend URL config
│   └── staticwebapp.config.json
├── prototype/               ← Original design prototypes
├── .github/workflows/       ← CI/CD for Azure
└── .gitignore
```

---

## Local Development

### 1. Backend

```powershell
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r backend/requirements.txt

# Set up your .env (already done — verify GITHUB_TOKEN is correct)
# backend/.env

# Start the backend
cd backend
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.
- `GET  /api/health` → health check
- `POST /api/cook`  → recipe generation (multipart form)
- `GET  /docs`      → Swagger UI

### 2. Frontend

Open a second terminal and serve the frontend:

```powershell
cd frontend
python -m http.server 3000
```

Open `http://localhost:3000` in your browser.

> **Tip:** Make sure `frontend/config.js` has `API_BASE_URL = 'http://localhost:8000'` for local dev.

---

## Azure Deployment

### Prerequisites

| Tool | Install |
|------|---------|
| Azure CLI | `winget install Microsoft.AzureCLI` |
| Docker Desktop | https://docs.docker.com/desktop/windows/ |
| GitHub repository | Push this project to GitHub first |

### Step 1 — Set up Azure resources

```bash
# Variables — change these
RESOURCE_GROUP="biterig-rg"
LOCATION="eastus"
ACR_NAME="biterigacr"
CONTAINER_APP_ENV="biterig-env"
CONTAINER_APP_NAME="biterig-api"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create Azure Container Registry
az acr create --name $ACR_NAME --resource-group $RESOURCE_GROUP --sku Basic --admin-enabled true

# Create Container Apps environment
az containerapp env create \
  --name $CONTAINER_APP_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION
```

### Step 2 — Deploy Backend (Container App)

```bash
# Build & push image
az acr build --registry $ACR_NAME --image biterig-api:latest ./backend

# Deploy Container App
az containerapp create \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_ENV \
  --image "${ACR_NAME}.azurecr.io/biterig-api:latest" \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-username $(az acr credential show -n $ACR_NAME --query username -o tsv) \
  --registry-password $(az acr credential show -n $ACR_NAME --query passwords[0].value -o tsv) \
  --env-vars "GITHUB_TOKEN=<your-github-pat>" "ALLOWED_ORIGINS=*" \
  --ingress external \
  --target-port 8000 \
  --cpu 0.5 --memory 1Gi \
  --min-replicas 1

# Get the backend URL
az containerapp show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn -o tsv
```

### Step 3 — Deploy Frontend (Azure Static Web Apps)

1. Go to [portal.azure.com](https://portal.azure.com)
2. Create a **Static Web App** resource
3. Connect it to your GitHub repository
4. Set **App location** = `frontend`, **Build output** = leave blank
5. Azure will auto-create `.github/workflows/deploy-frontend.yml` — you already have it!

After deploy, update `frontend/config.js`:
```js
const API_BASE_URL = 'https://<your-container-app-fqdn>';
```

Also update ALLOWED_ORIGINS on the backend to your Static Web App URL.

### Step 4 — Set GitHub Secrets (for CI/CD)

In your GitHub repo → Settings → Secrets → Actions:

| Secret | Value |
|--------|-------|
| `AZURE_CREDENTIALS` | Output of `az ad sp create-for-rbac --sdk-auth` |
| `ACR_LOGIN_SERVER`  | `biterigacr.azurecr.io` |
| `ACR_USERNAME`      | ACR admin username |
| `ACR_PASSWORD`      | ACR admin password |
| `CONTAINER_APP_NAME`| `biterig-api` |
| `CONTAINER_APP_RG`  | `biterig-rg` |
| `FRONTEND_URL`      | Your Azure Static Web App URL |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | From SWA resource in portal |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | ✅ | GitHub fine-grained PAT for AI model access |
| `ALLOWED_ORIGINS` | Optional | Comma-separated CORS origins. Default: `*` |

---

## ⚠️ Security Note

**Never commit your `backend/.env` file.** It is listed in `.gitignore`.
Store the `GITHUB_TOKEN` as a GitHub Secret and inject it at deploy time.

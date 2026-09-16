# Cloud Deployment Guide: Render (Backend) & Firebase Hosting (Frontend)
## CashOut Forecast — SIH 2026 Problem Statement 26184

This guide provides step-by-step instructions for deploying the **CashOut Forecast API** on **Render** (free-tier Python Web Service / Docker) and the **Investigator Frontend Dashboard** on **Firebase Hosting**.

---

## 1. Backend Deployment on Render

Render automatically builds and runs the FastAPI application from your GitHub repository.

### Option A: 1-Click Blueprint (Recommended)
1. Push your latest code (including `render.yaml` and `Dockerfile`) to your GitHub repository:
   ```bash
   git add .
   git commit -m "feat: Controlled Decoy Layer and Render Blueprint"
   git push origin main
   ```
2. Log in to [Render Dashboard](https://dashboard.render.com).
3. Click **New +** ➔ **Blueprint**.
4. Connect your GitHub repository (`PalPB/SIH_26184`).
5. Render will automatically read `render.yaml`, create the `cashout-forecast-api` web service, install dependencies, initialize the database tables, and start Uvicorn.
6. Once deployed, Render will provide your public backend URL, e.g.:
   `https://cashout-forecast-api.onrender.com`

### Option B: Manual Web Service
- **Build Command**: `pip install -r requirements.txt && python -c "from backend.database.connection import init_db; init_db()"`
- **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**:
  - `PYTHON_VERSION`: `3.11.9`
  - `ENVIRONMENT`: `production`

---

## 2. Frontend Deployment on Firebase Hosting

Firebase Hosting provides global CDN caching, custom domains, and SSL for the intelligence dashboard.

### Step 1: Install Firebase CLI & Login
```bash
npm install -g firebase-tools
firebase login
```

### Step 2: Configure Production Backend URL
Open `frontend/js/config.js` and set your Render URL:
```javascript
window.RENDER_BACKEND_URL = "https://cashout-forecast-api.onrender.com";
```
*(Alternatively, evaluators can change the backend URL in browser DevTools via `localStorage.setItem('CASHOUT_API_BASE_URL', 'https://your-api.onrender.com')` without rebuilding).*

### Step 3: Initialize & Deploy to Firebase
```bash
# In the project root (where firebase.json is located):
firebase init hosting
# Select "Use an existing project" (or create a new project in Firebase console)
# Specify public directory: frontend
# Configure as a single-page app: Yes
# Overwrite index.html: No

# Deploy:
firebase deploy --only hosting
```

Your frontend will be live on `https://<your-project-id>.web.app` and `https://<your-project-id>.firebaseapp.com`.

---

## 3. Local Development & Testing

To run both services locally on Windows:

1. **Start Backend**:
   ```powershell
   uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```
2. **Access Frontend**:
   - Open `http://localhost:8000/` (Landing / Login)
   - Open `http://localhost:8000/app` (Investigator Dashboard)
   - Open `http://localhost:8000/docs` (FastAPI Swagger Interactive Documentation)

3. **Demo Credentials**:
   - **Investigator**: `investigator` / `inv123`
   - **Admin**: `admin` / `admin123`

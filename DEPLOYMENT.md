# Free deployment guide – Proactive Financial Agent

Step-by-step instructions to deploy the **frontend** and **backend** for free. Start with the frontend; then deploy the backend and connect them.

---

## Overview

| Part      | Free option   | Notes |
|-----------|---------------|--------|
| Frontend  | **Vercel**    | Next.js; free tier, no credit card for hobby. |
| Backend   | **Render**    | Free web service (spins down after ~15 min inactivity). |
| Database  | **Supabase**  | Free tier (you already use it). |
| Vector DB | **Qdrant Cloud** | Free tier. |

### Do you need a .env file? Where does the backend URL go?

- **Backend** – Does **not** need a “backend URL” in `.env`. The backend *is* the API. On Render you set **environment variables** (e.g. `DATABASE_URL`, `OPENAI_API_KEY`, `CORS_ORIGINS`) in the dashboard; no `.env` file in the repo.
- **Frontend** – Must know the **backend URL** so the app can call your API. Set **`NEXT_PUBLIC_API_URL`** to your deployed backend URL (e.g. `https://your-app.onrender.com`) in **Vercel → Settings → Environment Variables**. No `.env` file required in the repo for production.

---

## Part 1: Deploy the frontend (Vercel)

### Step 1.1 – Push your code to GitHub

If you haven’t already:

```bash
cd "Proactive Financial Agent"
git init
git add .
git commit -m "Initial commit"
# Create a repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

(Use your real repo URL. Use `master` if your default branch is `master`.)

### Step 1.2 – Deploy on Vercel

1. Go to [vercel.com](https://vercel.com) and sign in (e.g. with GitHub).
2. Click **Add New…** → **Project**.
3. **Import** your GitHub repository.
4. **Configure the project:**
   - **Root Directory:** click **Edit**, set to **`frontend`** (so Vercel builds the Next.js app).
   - **Framework Preset:** Next.js (auto-detected).
   - **Build Command:** `npm run build` (default).
   - **Output Directory:** leave default.
5. **Environment variables (required for API):**
   - Open **Environment Variables**.
   - Add:
     - **Name:** `NEXT_PUBLIC_API_URL`
     - **Value:** For the first deploy use a placeholder, e.g. `https://your-backend.onrender.com`. After you deploy the backend (Part 2), come back and set this to your **real** Render URL (e.g. `https://proactive-financial-agent-xxxx.onrender.com`).
   - Save.
6. Click **Deploy**.

When the build finishes, you’ll get a URL like `https://your-project.vercel.app`. The UI will load; API calls will work once you set the real backend URL and deploy the backend.

### Step 1.3 – Frontend .env (optional, local only)

- For **local** development you can create **`frontend/.env.local`** with:
  - `NEXT_PUBLIC_API_URL=http://localhost:8000`
- For **production (Vercel)** you do **not** need a `.env` file in the repo; set **`NEXT_PUBLIC_API_URL`** in Vercel **Settings → Environment Variables** (as in Step 1.2).

**Summary:** The frontend needs the backend URL via **`NEXT_PUBLIC_API_URL`** – in Vercel for production, and optionally in `frontend/.env.local` for local dev.

---

## Part 2: Deploy the backend (Render)

### Step 2.1 – Create a Web Service on Render

1. Go to [render.com](https://render.com) and sign in (e.g. with GitHub).
2. **Dashboard** → **New +** → **Web Service**.
3. Connect your GitHub repo (same repo as the frontend).
4. **Configure:**
   - **Name:** e.g. `proactive-financial-agent-api`
   - **Region:** choose one close to you.
   - **Root Directory:** leave **empty** (use repo root).
   - **Runtime:** **Python 3**.
   - **Build Command:**  
     `pip install -r backend/requirements.txt`
   - **Start Command:**  
     `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** **Free**.

### Step 2.2 – Set environment variables on Render

In the same Web Service, go to **Environment** and add these (same as in your root `.env` locally). **Do not commit real secrets to the repo.**

| Variable | Required | Example / notes |
|----------|----------|------------------|
| `DATABASE_URL` | Yes | Your Supabase connection string (pooler URI). |
| `QDRANT_URL` | Yes | Your Qdrant Cloud cluster URL. |
| `QDRANT_API_KEY` | Yes (Qdrant Cloud) | Your Qdrant API key. |
| `OPENAI_API_KEY` | Yes (if using OpenAI) | Your OpenAI API key. |
| `LLM_PROVIDER` | No | `openai` (default). |
| `EMBEDDING_PROVIDER` | No | `openai` (default). |
| **`CORS_ORIGINS`** | **Yes for frontend** | Your Vercel URL, e.g. `https://your-project.vercel.app` (no trailing slash). Add multiple origins comma-separated if needed. |

Optional (if you use them): `LLM_MODEL`, `BRIEF_LLM_MODEL`, `EMBEDDING_MODEL`, `QDRANT_COLLECTION`, `ADVISER_ID`.

**Important:** Set **`CORS_ORIGINS`** to your **deployed Vercel URL** so the browser allows requests from the frontend to the backend.

### Step 2.3 – Deploy

Click **Create Web Service**. Render will build and start the backend. When it’s live, copy the service URL (e.g. `https://proactive-financial-agent-xxxx.onrender.com`).

### Step 2.4 – Point the frontend to the backend

1. In **Vercel** → your project → **Settings** → **Environment Variables**.
2. Set **`NEXT_PUBLIC_API_URL`** to your **Render URL** (e.g. `https://proactive-financial-agent-xxxx.onrender.com`), then save.
3. **Redeploy** the frontend (Vercel → Deployments → ⋮ on latest → Redeploy) so the new value is baked into the build.

---

## Quick reference

| Where | What to set |
|-------|-------------|
| **Vercel (frontend)** | `NEXT_PUBLIC_API_URL` = your **backend** URL (e.g. Render). |
| **Render (backend)** | All keys from `.env.example` (e.g. `DATABASE_URL`, `QDRANT_*`, `OPENAI_API_KEY`). Plus **`CORS_ORIGINS`** = your **frontend** URL (e.g. Vercel). |
| **Local frontend** | Optional: `frontend/.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000`. |
| **Local backend** | `.env` at **project root** (as in README). |

After deployment, open your Vercel URL and use the app; the first request to the free Render backend might be slow while the instance wakes up.

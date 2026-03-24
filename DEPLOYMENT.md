# Deployment Guide - LLM Moderator Platform

Complete guide to deploy your collaborative learning platform to production.

---

## 🏗️ Architecture Overview

Your project has 3 components:
1. **Frontend**: React app (can deploy to Vercel)
2. **Backend**: Flask + Socket.IO server (needs Python hosting)
3. **Database**: Supabase PostgreSQL (already hosted)

---

## 🚀 Recommended Deployment Stack

| Component | Platform | Why |
|-----------|----------|-----|
| Frontend | **Vercel** | You're already familiar, free tier, automatic deploys |
| Backend | **Render.com** | Free tier, supports Flask + WebSockets, easy setup |
| Database | **Supabase** | Already set up, stays the same |

---

## Part 1: Deploy Backend to Render.com

### Step 1: Prepare Backend for Deployment

1. **Create `render.yaml` in project root**:

```yaml
services:
  - type: web
    name: llm-moderator-backend
    env: python
    region: oregon
    plan: free
    buildCommand: cd server && pip install -r requirements.txt
    startCommand: cd server && python app.py
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_KEY
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: FRONTEND_URL
        sync: false
```

2. **Update `server/app.py` to use PORT from environment**:

Find this line (around line 697):
```python
socketio.run(app, host="0.0.0.0", port=5000, debug=False)
```

Change to:
```python
port = int(os.environ.get("PORT", 5000))
socketio.run(app, host="0.0.0.0", port=port, debug=False)
```

### Step 2: Create Render Account & Deploy

1. Go to [https://render.com](https://render.com)
2. Sign up (free account)
3. Click **"New +"** → **"Web Service"**
4. Connect your GitHub repository
5. Configure:
   - **Name**: `llm-moderator-backend`
   - **Region**: Oregon (US West)
   - **Branch**: `main` (or your branch name)
   - **Root Directory**: Leave blank
   - **Environment**: `Python 3`
   - **Build Command**: `cd server && pip install -r requirements.txt`
   - **Start Command**: `cd server && python app.py`
   - **Plan**: Free

### Step 3: Add Environment Variables

In Render dashboard, go to **Environment** and add:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key
OPENAI_API_KEY=sk-your-openai-key
FRONTEND_URL=https://llm-moderator-39gf.vercel.app
PYTHON_VERSION=3.11.0
```

### Step 4: Deploy

1. Click **"Create Web Service"**
2. Wait 5-10 minutes for build
3. Note your backend URL: `https://llm-moderator-backend.onrender.com`

---

## Part 2: Deploy Frontend to Vercel

### Step 1: Update Frontend API URL

1. **Edit `client/frontend/src/components/AdminDashboard.js`**:

Change line 8:
```javascript
const API_URL = 'http://localhost:5000';
```

To:
```javascript
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';
```

2. **Edit `client/frontend/src/socket.js`**:

Change the socket connection:
```javascript
import { io } from 'socket.io-client';

const SOCKET_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

export const socket = io(SOCKET_URL, {
  autoConnect: true,
  reconnection: true,
  reconnectionDelay: 1000,
  reconnectionAttempts: 5,
});
```

3. **Create `vercel.json` in `client/frontend/`**:

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "build",
  "devCommand": "npm start",
  "installCommand": "npm install",
  "framework": "create-react-app",
  "env": {
    "REACT_APP_API_URL": "@react_app_api_url"
  }
}
```

### Step 2: Deploy to Vercel

1. Go to [https://vercel.com](https://vercel.com)
2. Click **"Add New Project"**
3. Import your GitHub repository
4. Configure:
   - **Framework Preset**: Create React App
   - **Root Directory**: `client/frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `build`

5. Add Environment Variable:
   - Key: `REACT_APP_API_URL`
   - Value: `https://llm-moderator-backend.onrender.com` (your Render URL)

6. Click **"Deploy"**
7. Wait 2-3 minutes
8. Note your frontend URL: `https://your-project.vercel.app`

### Step 3: Update Backend CORS

1. Go back to Render dashboard
2. Update `FRONTEND_URL` environment variable:
   ```
   FRONTEND_URL=https://your-project.vercel.app
   ```

3. Redeploy backend (it will restart automatically)

---

## Part 3: Update Supabase Settings

1. Go to Supabase Dashboard → Settings → API
2. Under **"URL Configuration"**, add your domains:
   - `https://your-project.vercel.app`
   - `https://llm-moderator-backend.onrender.com`

---

## Part 4: Test Deployment

### Test Backend:
```bash
curl https://llm-moderator-backend.onrender.com/admin/settings
```
Should return JSON with settings.

### Test Frontend:
1. Open `https://your-project.vercel.app`
2. Should see room creation page
3. Try `/admin` route

### Test End-to-End:
1. Go to `https://your-project.vercel.app/join/active`
2. Should create room and connect to backend
3. Send a message
4. Check it saves to Supabase

---

## 🔧 Production Configuration

### Backend Environment Variables (Render):

```bash
# Required
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJxxx...
OPENAI_API_KEY=sk-proj-xxx...
FRONTEND_URL=https://your-project.vercel.app

# Optional (with defaults)
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.3
OPENAI_MAX_TOKENS=1500
PYTHON_VERSION=3.11.0
```

### Frontend Environment Variables (Vercel):

```bash
REACT_APP_API_URL=https://llm-moderator-backend.onrender.com
```

---

## 🎯 Custom Domains (Optional)

### For Frontend (Vercel):
1. Go to Vercel project → Settings → Domains
2. Add your custom domain (e.g., `moderator.yourdomain.com`)
3. Update DNS records as instructed

### For Backend (Render):
1. Upgrade to paid plan ($7/month)
2. Go to Settings → Custom Domain
3. Add domain (e.g., `api.yourdomain.com`)

---

## 📊 Monitoring & Logs

### Backend Logs (Render):
1. Go to Render dashboard → Your service
2. Click **"Logs"** tab
3. See real-time server logs

### Frontend Logs (Vercel):
1. Go to Vercel dashboard → Your project
2. Click **"Deployments"** → Select deployment
3. Click **"Functions"** or **"Runtime Logs"**

### Database Logs (Supabase):
1. Supabase Dashboard → Logs
2. See all database queries

---

## 🐛 Common Deployment Issues

### Issue 1: "CORS Error" in Frontend

**Fix**: Make sure `FRONTEND_URL` in Render matches your Vercel URL exactly (no trailing slash).

### Issue 2: Backend Won't Start

**Check**:
1. Render logs for errors
2. All environment variables are set
3. Python version is 3.11.0
4. Requirements installed successfully

### Issue 3: WebSocket Connection Fails

**Fix**: 
- Render free tier may sleep after inactivity
- First request after sleep takes ~30 seconds
- Consider upgrading to paid tier for always-on

### Issue 4: Database Connection Errors

**Check**:
1. Supabase service key is correct
2. Supabase URL is correct
3. Migrations have been run
4. Row Level Security settings

---

## 💰 Cost Breakdown

| Service | Free Tier | Limitations | Paid Plan |
|---------|-----------|-------------|-----------|
| **Vercel** | Yes | 100 GB bandwidth | $20/month |
| **Render** | Yes | Sleeps after 15min inactivity | $7/month (always on) |
| **Supabase** | Yes | 500MB database, 2GB bandwidth | $25/month |

**Total Free**: $0/month (with sleep limitations)
**Total Paid**: $32-52/month (no limitations)

---

## 🚀 Quick Deploy Commands

### One-Time Setup:

```bash
# 1. Update backend for production
cd /home/user/LLM_MODERATOR/server
# Add PORT handling to app.py (see Step 1 above)

# 2. Update frontend API URLs
cd /home/user/LLM_MODERATOR/client/frontend
# Edit socket.js and AdminDashboard.js (see Step 1 above)

# 3. Commit changes
git add .
git commit -m "Prepare for production deployment"
git push origin main
```

### Deploy Backend (Render):
1. Connect GitHub repo
2. Set environment variables
3. Deploy

### Deploy Frontend (Vercel):
1. Import GitHub repo
2. Set root directory: `client/frontend`
3. Add `REACT_APP_API_URL` environment variable
4. Deploy

---

## 🔄 Continuous Deployment

Both Vercel and Render support automatic deployments:

**On every git push to main branch**:
- Vercel automatically rebuilds frontend
- Render automatically rebuilds backend

No manual deployment needed after initial setup!

---

## 📝 Deployment Checklist

Before going live:

- [ ] Backend deployed to Render
- [ ] Frontend deployed to Vercel
- [ ] All environment variables set correctly
- [ ] Database migrations run in Supabase
- [ ] CORS configured properly
- [ ] Test auto-join links work
- [ ] Test admin panel works
- [ ] Test story sessions work
- [ ] Test WebSocket connections
- [ ] Check backend logs for errors
- [ ] Check frontend console for errors

---

## 🆘 Need Help?

### Render Support:
- Docs: https://render.com/docs
- Discord: https://discord.gg/render

### Vercel Support:
- Docs: https://vercel.com/docs
- Discord: https://vercel.com/discord

### Supabase Support:
- Docs: https://supabase.com/docs
- Discord: https://discord.supabase.com

---

## 🎉 You're Live!

Once deployed, share these URLs:

**For Students**: `https://your-project.vercel.app/join/active`
**For Researchers**: `https://your-project.vercel.app/admin`

**Happy researching!** 🚀

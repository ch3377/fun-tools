# FunTookit - Deploy to Render.com

## Step 1: Push to GitHub

```bash
cd FunTookit
git init
git add -A
git commit -m "Initial commit - FunTookit"
```

Create a new repo on GitHub (e.g. `FunTookit`), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/FunTookit.git
git branch -M main
git push -u origin main
```

## Step 2: Deploy on Render

1. Go to [https://render.com](https://render.com) and sign in
2. Click **New** > **Web Service**
3. Connect your GitHub repo `FunTookit`
4. Render will auto-detect settings from `render.yaml`, but verify:
   - **Name**: `fun-tookit`
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 --bind 0.0.0.0:$PORT app:app`
   - **Plan**: Free
5. Under **Environment**, add:
   - `PYTHON_VERSION` = `3.11.11`
6. Click **Create Web Service**

## Step 3: Verify

- Wait for the build to complete (usually 2-3 minutes)
- Visit your Render URL (e.g. `https://fun-tookit.onrender.com`)
- Test the home page, Decision Roller, and Splitwiser (both Solo and Room mode)

## Notes

- Free tier on Render sleeps after 15 minutes of inactivity. First visit after sleep takes ~30 seconds to wake up.
- SocketIO (used by Splitwiser Room Mode) requires the `gevent-websocket` worker, which is already configured.
- Only 1 worker (`-w 1`) because SocketIO rooms are stored in memory. For production scaling, you'd need Redis as a message queue.

## Local Development

```bash
pip install -r requirements.txt
python app.py
```

Opens at `http://localhost:8080`

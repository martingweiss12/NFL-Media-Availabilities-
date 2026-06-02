# NFL Media Availabilities - Cloud Deployment Guide

## Overview

This is a production-ready Streamlit web application that monitors official NFL team YouTube channels, extracts transcripts, and presents them in a clean, searchable UI. It's designed to run on **Streamlit Community Cloud** or similar cloud platforms with zero local dependencies.

---

## Prerequisites

- A **GitHub account** (free)
- A **Streamlit Cloud account** (free, linked to GitHub)
- An **OpenAI API Key** (free trial: $5 credits) OR **Anthropic API Key**
- An **SMTP email account** (optional for notifications)
- 5 minutes to follow this guide

---

## Step 1: Prepare Your Files

You already have:
- `requirements.txt` – All Python dependencies
- `app.py` – The main application
- `DEPLOYMENT_GUIDE.md` – This file

**No other files are needed.** The app creates its own SQLite database on deployment.

---

## Step 2: Push to GitHub

If not already done, push these files to your GitHub repository (`martingweiss12/NFL-Media-Availabilities-`):

```bash
git add requirements.txt app.py DEPLOYMENT_GUIDE.md
git commit -m "Add production NFL media transcription app"
git push origin main
```

---

## Step 3: Deploy on Streamlit Cloud

### 3a. Sign Up / Log In

1. Go to **https://share.streamlit.io**
2. Click **"Sign up with GitHub"** (or log in if you have an account)
3. Authorize Streamlit to access your GitHub repositories

### 3b. Create a New App

1. Click **"New app"** (top-left)
2. Fill in the form:
   - **Repository:** `martingweiss12/NFL-Media-Availabilities-`
   - **Branch:** `main` (or your current branch)
   - **Main file path:** `app.py`
3. Click **"Deploy"**

Streamlit will automatically:
- Clone your repository
- Install dependencies from `requirements.txt`
- Launch the app at a public URL like: `https://nfl-media-availabilities.streamlit.app`

⏳ **First deployment takes 2–3 minutes.** Grab a coffee.

---

## Step 4: Add Secrets

Streamlit Cloud apps run in a container; local environment variables don't persist. Instead, use the **Secrets** panel:

### 4a. Open Secrets Dashboard

1. In your Streamlit Cloud app, click the **hamburger menu** (☰) → **"Rerun"** or refresh the page
2. In the top-right, click your **profile picture** → **"Settings"**
3. In the left sidebar, click **"Secrets"**

### 4b. Add LLM API Key

Paste one of the following into the Secrets text area:

**For OpenAI (GPT-3.5):**
```
OPENAI_API_KEY = "sk-proj-..."
```

Get a free key at: https://platform.openai.com/api-keys  
(Free tier: $5 trial credits)

**OR for Anthropic (Claude):**
```
ANTHROPIC_API_KEY = "sk-ant-..."
```

Get a free key at: https://console.anthropic.com/account/keys

### 4c. Add Email Notification Secrets (Optional)

To receive email alerts when new transcripts are processed:

```
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = "587"
SENDER_EMAIL = "your-email@gmail.com"
SENDER_PASSWORD = "your-app-password"
RECIPIENT_EMAIL = "your-email@gmail.com"
```

**For Gmail:**
1. Enable 2-Factor Authentication on your Google account
2. Generate an **App Password**: https://myaccount.google.com/apppasswords
3. Paste the 16-character app password as `SENDER_PASSWORD`
4. **Do NOT use your regular Gmail password**

**For Other Email Providers:**
- Outlook: `smtp.outlook.com` (port 587)
- Yahoo: `smtp.mail.yahoo.com` (port 587)
- Custom domain: Contact your email provider for SMTP details

### 4d. Save Secrets

Click **"Save"** at the bottom of the Secrets panel. Streamlit will automatically restart your app with the new configuration.

---

## Step 5: Verify the App

1. Go to your app URL (e.g., `https://nfl-media-availabilities.streamlit.app`)
2. You should see:
   - A sidebar with "🏈 NFL Media Availabilities"
   - A **"Refresh & Check for New Videos"** button
   - A message: "📭 No interviews yet. Monitoring in progress..."

This is expected on first load. The background monitoring thread will:
- Check all 32 NFL team YouTube channels
- Extract transcripts from press conferences, media availabilities, and locker room content
- Process transcripts with GPT-3.5 / Claude
- Populate the database over the next 10–30 minutes

3. **Wait 10–15 minutes** and refresh the page. You should see interviews appearing.

---

## How It Works

### Automated Monitoring (Background Thread)

Once deployed, a background thread:
1. **Every 30 minutes**, checks the YouTube channels of all 32 NFL teams
2. **Filters** for relevant content (press conferences, media availabilities, locker room)
3. **Extracts** auto-generated YouTube transcripts or uses a transcription API
4. **Processes** transcripts with OpenAI GPT-3.5 or Anthropic Claude to:
   - Identify the main speaker (coach, player, GM, etc.)
   - Format Q&A dialogue (reporter questions vs. speaker answers)
   - Extract timecodes for each response
5. **Saves** formatted transcripts to the SQLite database
6. **Sends email** notification (if configured)

### User Interface (Three-Level Hierarchy)

**Level 1: Team Selection**
- Sidebar dropdown lists all 32 NFL teams with recent interviews
- Only teams with available content appear

**Level 2: Speaker Selection**
- Select a speaker (e.g., "Andy Reid", "Patrick Mahomes")
- Sorted by most recent interview date

**Level 3: Interview Transcripts**
- Chronological list of all interviews with that speaker
- Each interview has:
  - **Direct YouTube link** [🎥 Watch on YouTube]
  - **Q&A transcript** with timecodes in `[MM:SS]` format
  - **Clickable timecode links** that jump to exact moment in video
  - **Speaker name** clearly labeled for each response

---

## Database & Persistence

The app uses **SQLite** (`nfl_media.db`), which:
- Is created automatically on first run
- Lives in the app's persistent storage directory (survives container restarts)
- Stores:
  - All processed videos and transcripts
  - Speaker names and dates
  - Email notification logs

**Note:** Streamlit Cloud containers have 1 GB persistent storage. With typical transcript sizes (~5 KB each), you can store ~200,000 transcripts.

---

## Customization

### Change Monitoring Frequency

Edit `app.py`, line ~365, in the `background_monitor()` function:

```python
# Check every 30 minutes (1800 seconds)
time.sleep(1800)

# To check every 10 minutes:
time.sleep(600)

# To check every hour:
time.sleep(3600)
```

### Add/Remove Teams

Edit `app.py`, line ~32, the `NFL_TEAMS` dictionary. Add or remove entries:

```python
NFL_TEAMS = {
    "Team Name": "@YouTubeHandle",
    # ...
}
```

### Change Media Keywords

Edit `app.py`, line ~49, the `MEDIA_KEYWORDS` list:

```python
MEDIA_KEYWORDS = [
    "press conference",
    "media availability",
    "your custom keyword",
]
```

After editing, commit and push to GitHub. Streamlit Cloud will automatically redeploy.

---

## Troubleshooting

### "No interviews yet. Monitoring in progress..."

**Expected on first deployment.** The app checks YouTube channels every 30 minutes. Wait 10–15 minutes and refresh.

### "No LLM API key configured"

Make sure you've added `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` to Streamlit Cloud's Secrets panel (not your local `.env` file).

### Transcripts show "Transcript processing in progress..."

The LLM is still processing. Reload the page in a few moments.

### Email notifications not sent

Check that all SMTP secrets are configured:
- `SMTP_SERVER`
- `SMTP_PORT`
- `SENDER_EMAIL`
- `SENDER_PASSWORD` (use Gmail App Password, not your regular password)
- `RECIPIENT_EMAIL`

### App crashes or shows error

1. Check the **"Logs"** tab in Streamlit Cloud's app settings
2. Common issues:
   - Invalid API key (check Secrets panel)
   - Network error fetching YouTube (temporary; try again)
   - Database locked (wait 30 seconds and refresh)

---

## Performance & Scaling

- **Response time:** UI loads in <1 second (local SQLite query)
- **Background processing:** Runs in a separate thread; doesn't block user interface
- **Concurrent users:** Streamlit Cloud supports ~100 concurrent users on the free tier
- **Storage:** 1 GB persistent storage = ~200,000 transcripts

For higher traffic, upgrade to Streamlit's **Business** or **Enterprise** plan.

---

## Security Best Practices

1. **Never** commit API keys to GitHub. Always use Streamlit Secrets.
2. **Keep API keys private:**
   - Don't share your Secrets panel access
   - Rotate API keys annually
3. **Email safety:**
   - Use Gmail App Passwords, not your regular password
   - Enable 2FA on your email account
4. **Database:**
   - SQLite is file-based; only accessible from your app
   - No external database connection required (safer)

---

## FAQ

**Q: Can I use this locally?**

A: Yes! Follow these steps:
```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file with secrets
echo "OPENAI_API_KEY=sk-proj-..." > .env

# Run locally
streamlit run app.py
```

**Q: How do I stop monitoring?**

A: The monitoring thread stops automatically when the Streamlit Cloud app is idle (>1 hour of no users).

**Q: Can I deploy to Replit or Railway instead?**

A: Yes! Use the same `requirements.txt` and `app.py`. Set environment variables in the platform's Secrets/Environment panel instead of Streamlit Secrets.

**Q: What if a video has no transcript?**

A: The app skips videos without transcripts (rare). Most NFL videos have auto-generated captions.

**Q: Can I customize the UI?**

A: Absolutely! Edit `app.py` to modify colors, layout, and functionality. Then commit to GitHub and redeploy.

---

## Support

- **Streamlit Docs:** https://docs.streamlit.io
- **OpenAI API:** https://platform.openai.com/docs
- **Anthropic Claude:** https://docs.anthropic.com
- **yt-dlp:** https://github.com/yt-dlp/yt-dlp

---

**That's it! Your app is live. 🚀**

Enjoy monitoring NFL media availabilities!

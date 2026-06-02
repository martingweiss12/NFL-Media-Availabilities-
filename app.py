"""
NFL Media Availabilities Transcription App
A production-ready Streamlit application for monitoring and transcribing official NFL team media content.
Designed for deployment on Streamlit Community Cloud or similar cloud platforms.
"""

import os
import json
import sqlite3
import smtplib
import threading
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional, Tuple
import re

import streamlit as st
import yt_dlp
import requests
from dotenv import load_dotenv

# Load environment variables (for local development; Streamlit Cloud uses Secrets)
load_dotenv()

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

NFL_TEAMS = {
    "Arizona Cardinals": "@ArizonaCardinals",
    "Atlanta Falcons": "@AtlantaFalcons",
    "Baltimore Ravens": "@baltimoreravens",
    "Buffalo Bills": "@BuffaloBills",
    "Carolina Panthers": "@CarolinaPanthers",
    "Chicago Bears": "@ChicagoBears",
    "Cincinnati Bengals": "@CincinnatiBengals",
    "Cleveland Browns": "@ClevelandBrowns",
    "Dallas Cowboys": "@DallasCowboys",
    "Denver Broncos": "@DenverBroncos",
    "Detroit Lions": "@detroitlions",
    "Green Bay Packers": "@packers",
    "Houston Texans": "@HoustonTexans",
    "Indianapolis Colts": "@Colts",
    "Jacksonville Jaguars": "@JacksonvillJaguars",
    "Kansas City Chiefs": "@KChiefs",
    "Las Vegas Raiders": "@Raiders",
    "Los Angeles Chargers": "@chargers",
    "Los Angeles Rams": "@RamsNFL",
    "Miami Dolphins": "@MiamiDolphins",
    "Minnesota Vikings": "@Vikings",
    "New England Patriots": "@patriots",
    "New Orleans Saints": "@Saints",
    "New York Giants": "@Giants",
    "New York Jets": "@nyjets",
    "Philadelphia Eagles": "@Eagles",
    "Pittsburgh Steelers": "@steelers",
    "San Francisco 49ers": "@49ers",
    "Seattle Seahawks": "@seahawks",
    "Tampa Bay Buccaneers": "@TampaBayBuccaneers",
    "Tennessee Titans": "@TennesseeTitans",
    "Washington Commanders": "@Commanders",
}

# Keyword filters for media content (strict matching)
MEDIA_KEYWORDS = [
    "press conference",
    "media availability",
    "locker room",
    "postgame",
    "scrum",
    "coach",
    "interview",
]

HIGHLIGHTS_KEYWORDS = ["highlight", "game recap", "best of", "top 10"]

DB_PATH = "nfl_media.db"
CACHE_EXPIRY_HOURS = 24


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_database():
    """Initialize SQLite database for storing transcripts."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            team TEXT NOT NULL,
            youtube_handle TEXT NOT NULL,
            title TEXT NOT NULL,
            video_url TEXT NOT NULL,
            published_at TEXT NOT NULL,
            transcript TEXT,
            speaker_name TEXT,
            processed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS email_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            speaker TEXT NOT NULL,
            team TEXT NOT NULL,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(video_id)
        )
    """)
    
    conn.commit()
    conn.close()


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================================
# SECRETS & ENVIRONMENT VARIABLES
# ============================================================================

def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Retrieve secrets from Streamlit Cloud or environment variables.
    Priority: Streamlit secrets > environment variables > default
    """
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except:
        return os.getenv(key, default)


# ============================================================================
# YOUTUBE SCRAPING & FILTERING
# ============================================================================

def filter_video_title(title: str) -> bool:
    """
    Determine if a video is relevant media content (not highlights).
    Returns True if video should be processed.
    """
    title_lower = title.lower()
    
    # Exclude highlights and fluff
    for keyword in HIGHLIGHTS_KEYWORDS:
        if keyword in title_lower:
            return False
    
    # Include only if matches media keywords
    for keyword in MEDIA_KEYWORDS:
        if keyword in title_lower:
            return True
    
    return False


def fetch_channel_videos(youtube_handle: str, max_results: int = 5) -> List[Dict]:
    """
    Fetch recent videos from a YouTube channel handle using yt-dlp.
    Returns list of video metadata dictionaries.
    """
    try:
        # Convert handle to channel URL
        channel_url = f"https://www.youtube.com/{youtube_handle}"
        
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "playlistend": max_results,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(channel_url, download=False)
        
        videos = []
        if result and "entries" in result:
            for entry in result["entries"]:
                if entry is None:
                    continue
                
                title = entry.get("title", "")
                
                # Filter based on title
                if not filter_video_title(title):
                    continue
                
                video_info = {
                    "id": entry.get("id", ""),
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                    "published_at": entry.get("upload_date", ""),
                }
                videos.append(video_info)
        
        return videos
    
    except Exception as e:
        st.error(f"Error fetching videos from {youtube_handle}: {str(e)}")
        return []


# ============================================================================
# TRANSCRIPT EXTRACTION
# ============================================================================

def extract_youtube_transcript(video_url: str) -> Optional[str]:
    """
    Extract auto-generated transcript from YouTube video using yt-dlp.
    Returns raw transcript text or None if unavailable.
    """
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "writeautomaticsub": True,
            "skip_download": True,
            "outtmpl": "temp_transcript",
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            # Try to get subtitles
            if info and "subtitles" in info:
                subtitles = info["subtitles"]
                if "en" in subtitles:
                    return json.dumps(subtitles["en"])
        
        return None
    
    except Exception as e:
        st.warning(f"Could not extract transcript from {video_url}: {str(e)}")
        return None


def clean_transcript_text(raw_transcript: str) -> str:
    """
    Clean and normalize transcript text.
    If raw_transcript is JSON (from subtitles), parse and extract text.
    """
    try:
        # Try parsing as JSON (yt-dlp subtitle format)
        data = json.loads(raw_transcript)
        if isinstance(data, list):
            text_parts = [item.get("text", "") for item in data if "text" in item]
            return " ".join(text_parts)
    except:
        pass
    
    # Return as-is if not JSON
    return raw_transcript


# ============================================================================
# LLM PROCESSING
# ============================================================================

def process_transcript_with_llm(raw_transcript: str, team: str, video_title: str) -> Tuple[str, str]:
    """
    Send transcript to LLM (OpenAI or Anthropic) for formatting and speaker identification.
    Returns (formatted_transcript, speaker_name) tuple.
    """
    api_key = get_secret("OPENAI_API_KEY") or get_secret("ANTHROPIC_API_KEY")
    
    if not api_key:
        st.error("No LLM API key configured. Add OPENAI_API_KEY or ANTHROPIC_API_KEY to secrets.")
        return raw_transcript, "Unknown"
    
    clean_text = clean_transcript_text(raw_transcript)
    
    prompt = f"""
You are an expert at processing sports media transcripts. Analyze the following transcript from an NFL {team} media availability:

**Video Title:** {video_title}

**Raw Transcript:**
{clean_text}

Please perform the following tasks:
1. Identify the main speaker (coach, player, GM, etc.). Return their full name.
2. Reformat the transcript to clearly separate reporter questions from speaker answers.
3. For each speaker response, include timecode references in [MM:SS] format if available.
4. Use this JSON format:

{{
    "speaker": "Name of speaker",
    "q_and_a": [
        {{
            "timecode": "[MM:SS]",
            "question": "Reporter question text",
            "answer": "Speaker response text"
        }}
    ]
}}

Return ONLY valid JSON, no additional text.
"""
    
    try:
        # Try OpenAI first
        if get_secret("OPENAI_API_KEY"):
            import openai
            openai.api_key = get_secret("OPENAI_API_KEY")
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a sports media transcript formatter."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            
            result_text = response["choices"][0]["message"]["content"]
        
        # Fallback to Anthropic
        elif get_secret("ANTHROPIC_API_KEY"):
            import anthropic
            client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))
            
            message = client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )
            
            result_text = message.content[0].text
        
        # Parse JSON response
        try:
            data = json.loads(result_text)
            speaker = data.get("speaker", "Unknown")
            formatted = json.dumps(data, indent=2)
            return formatted, speaker
        
        except json.JSONDecodeError:
            # If LLM didn't return JSON, return cleaned text
            return clean_text, "Unknown"
    
    except Exception as e:
        st.error(f"LLM processing error: {str(e)}")
        return clean_text, "Unknown"


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def save_video_to_db(team: str, youtube_handle: str, video_info: Dict, 
                     transcript: Optional[str] = None, speaker_name: str = "Unknown"):
    """Save video and transcript to database."""
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        c.execute("""
            INSERT OR IGNORE INTO videos 
            (id, team, youtube_handle, title, video_url, published_at, transcript, speaker_name, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video_info["id"],
            team,
            youtube_handle,
            video_info["title"],
            video_info["url"],
            video_info["published_at"],
            transcript,
            speaker_name,
            datetime.now().isoformat(),
        ))
        
        conn.commit()
        return True
    
    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return False
    
    finally:
        conn.close()


def get_teams_with_interviews() -> List[str]:
    """Get list of teams that have interviews in database."""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT DISTINCT team FROM videos ORDER BY team")
    teams = [row[0] for row in c.fetchall()]
    
    conn.close()
    return teams


def get_speakers_for_team(team: str) -> List[Tuple[str, str]]:
    """Get list of unique speakers for a team with their most recent date."""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("""
        SELECT DISTINCT speaker_name, MAX(published_at) as latest_date
        FROM videos
        WHERE team = ? AND speaker_name IS NOT NULL AND speaker_name != 'Unknown'
        GROUP BY speaker_name
        ORDER BY latest_date DESC
    """, (team,))
    
    speakers = [(row[0], row[1]) for row in c.fetchall()]
    conn.close()
    return speakers


def get_interviews_for_speaker(team: str, speaker: str) -> List[Dict]:
    """Get all interviews for a specific speaker on a team."""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("""
        SELECT id, title, video_url, published_at, transcript, processed_at
        FROM videos
        WHERE team = ? AND speaker_name = ?
        ORDER BY published_at DESC
    """, (team, speaker))
    
    interviews = []
    for row in c.fetchall():
        interviews.append({
            "id": row[0],
            "title": row[1],
            "url": row[2],
            "published_at": row[3],
            "transcript": row[4],
            "processed_at": row[5],
        })
    
    conn.close()
    return interviews


# ============================================================================
# EMAIL NOTIFICATIONS
# ============================================================================

def send_email_notification(team: str, speaker: str, video_url: str, app_url: str = "https://your-app.streamlit.app"):
    """Send email notification when new transcript is processed."""
    smtp_server = get_secret("SMTP_SERVER")
    smtp_port = get_secret("SMTP_PORT", "587")
    sender_email = get_secret("SENDER_EMAIL")
    sender_password = get_secret("SENDER_PASSWORD")
    recipient_email = get_secret("RECIPIENT_EMAIL")
    
    # Skip if not all configured
    if not all([smtp_server, sender_email, sender_password, recipient_email]):
        return False
    
    try:
        # Compose message
        subject = f"🏈 New NFL Media Transcript: {team} - {speaker}"
        
        body = f"""
New NFL media transcript processed!

Team: {team}
Speaker: {speaker}
Video: {video_url}

View in app: {app_url}?team={team}&speaker={speaker}

---
NFL Media Availabilities Transcription App
"""
        
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        
        # Send email
        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        # Log email sent
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO email_log (video_id, speaker, team)
            VALUES (?, ?, ?)
        """, (video_url.split("v=")[-1], speaker, team))
        conn.commit()
        conn.close()
        
        return True
    
    except Exception as e:
        st.error(f"Email error: {str(e)}")
        return False


# ============================================================================
# BACKGROUND MONITORING THREAD
# ============================================================================

monitoring_active = False


def background_monitor():
    """Background thread to periodically check for new videos."""
    global monitoring_active
    
    while monitoring_active:
        try:
            conn = get_db_connection()
            c = conn.cursor()
            
            # Check each team's channel
            for team, handle in NFL_TEAMS.items():
                videos = fetch_channel_videos(handle, max_results=5)
                
                for video in videos:
                    # Check if already in database
                    c.execute("SELECT id FROM videos WHERE id = ?", (video["id"],))
                    if c.fetchone():
                        continue
                    
                    # New video found - extract and process
                    transcript = extract_youtube_transcript(video["url"])
                    if transcript:
                        formatted, speaker = process_transcript_with_llm(transcript, team, video["title"])
                        save_video_to_db(team, handle, video, formatted, speaker)
                        send_email_notification(team, speaker, video["url"])
            
            conn.close()
            
            # Check every 30 minutes
            time.sleep(1800)
        
        except Exception as e:
            st.error(f"Monitoring error: {str(e)}")
            time.sleep(300)


# ============================================================================
# STREAMLIT UI
# ============================================================================

def main():
    """Main Streamlit application."""
    global monitoring_active
    
    # Page configuration
    st.set_page_config(
        page_title="NFL Media Transcriptions",
        page_icon="🏈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Initialize database
    init_database()
    
    # Start background monitoring (once per session)
    if "monitoring_started" not in st.session_state:
        monitoring_active = True
        st.session_state.monitoring_started = True
        thread = threading.Thread(target=background_monitor, daemon=True)
        thread.start()
    
    # ========================================================================
    # SIDEBAR: TEAM SELECTION
    # ========================================================================
    
    st.sidebar.title("🏈 NFL Media Availabilities")
    st.sidebar.markdown("---")
    
    # Manual refresh button
    if st.sidebar.button("🔄 Refresh & Check for New Videos", use_container_width=True):
        st.rerun()
    
    st.sidebar.markdown("---")
    
    # Get teams with interviews
    teams_with_data = get_teams_with_interviews()
    
    if not teams_with_data:
        st.sidebar.info("📭 No interviews yet. Monitoring in progress...")
        st.title("🏈 NFL Media Availabilities Transcription")
        st.markdown("""
        Welcome! This app automatically monitors official NFL team YouTube channels for media availabilities,
        extracts transcripts, and organizes them by team and speaker.
        
        **Currently monitoring:**
        - 32 NFL team channels
        - Press conferences, media availabilities, locker room content
        - Automatic transcript extraction and speaker identification
        
        Check back soon as new content is processed!
        """)
        return
    
    selected_team = st.sidebar.selectbox(
        "Select a Team:",
        options=teams_with_data,
        index=0,
    )
    
    # ========================================================================
    # MAIN CONTENT: SPEAKER & TRANSCRIPT DISPLAY
    # ========================================================================
    
    st.title(f"🏈 {selected_team}")
    
    # Get speakers for selected team
    speakers = get_speakers_for_team(selected_team)
    
    if not speakers:
        st.info(f"No interviews found for {selected_team} yet.")
        return
    
    # Speaker selection
    speaker_options = [f"{name} (Latest: {date[:10]})" for name, date in speakers]
    selected_speaker_idx = st.selectbox(
        "Select a Speaker:",
        options=range(len(speakers)),
        format_func=lambda i: speaker_options[i],
    )
    
    selected_speaker = speakers[selected_speaker_idx][0]
    
    st.markdown("---")
    
    # Get interviews for selected speaker
    interviews = get_interviews_for_speaker(selected_team, selected_speaker)
    
    if not interviews:
        st.warning(f"No interviews found for {selected_speaker}.")
        return
    
    st.subheader(f"📹 Interviews with {selected_speaker}")
    
    # Display interviews chronologically
    for interview in interviews:
        with st.expander(f"📅 {interview['published_at'][:10]} - {interview['title']}", expanded=False):
            
            # Video link
            st.markdown(f"**[🎥 Watch on YouTube]({interview['url']})**")
            
            st.markdown("---")
            
            # Transcript display
            if interview["transcript"]:
                try:
                    # Try to parse as JSON
                    data = json.loads(interview["transcript"])
                    
                    if isinstance(data, dict) and "q_and_a" in data:
                        # Formatted Q&A
                        for qa in data["q_and_a"]:
                            timecode = qa.get("timecode", "[--:--]")
                            
                            # Timecode with link
                            video_id = interview["url"].split("v=")[-1]
                            timecode_seconds = 0
                            
                            # Parse timecode to seconds if available
                            if timecode and timecode != "[--:--]":
                                match = re.match(r"\[(\d+):(\d+)\]", timecode)
                                if match:
                                    timecode_seconds = int(match.group(1)) * 60 + int(match.group(2))
                            
                            timecode_link = f"https://www.youtube.com/watch?v={video_id}&t={timecode_seconds}s"
                            
                            st.markdown(f"**[{timecode}]({timecode_link})**")
                            
                            if qa.get("question"):
                                st.markdown(f"*Reporter:* {qa['question']}")
                            
                            st.markdown(f"**{selected_speaker}:** {qa.get('answer', '')}")
                            st.markdown("")
                    else:
                        st.text(interview["transcript"])
                
                except json.JSONDecodeError:
                    st.text(interview["transcript"])
            else:
                st.info("Transcript processing in progress...")
            
            # Metadata
            st.caption(f"Processed: {interview['processed_at']}")


if __name__ == "__main__":
    main()

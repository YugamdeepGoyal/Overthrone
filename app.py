"""
OVERTHRONE :: WAR ROOM OS v5.0
Run: streamlit run app.py
Requires: pip install streamlit redis
"""

import streamlit as st
import redis
import json
import time
import random
import hashlib
import subprocess
import sys
import io
import contextlib
from datetime import datetime, timedelta

# ── PAGE CONFIG ─────────────────────────────────────────────
st.set_page_config(
    page_title="OVERTHRONE :: WAR ROOM",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── REDIS w/ MOCK FALLBACK ───────────────────────────────────
class MockRedis:
    def __init__(self):
        self._d = {}
        self._lists = {}
    def get(self, k):
        return self._d.get(k)
    def set(self, k, v, ex=None):
        self._d[k] = v
        return True
    def lpush(self, k, *vals):
        if k not in self._lists:
            self._lists[k] = []
        for v in vals:
            self._lists[k].insert(0, v)
        return len(self._lists[k])
    def lrange(self, k, s, e):
        lst = self._lists.get(k, [])
        return lst[s: None if e == -1 else e + 1]
    def ping(self):
        return True
    def delete(self, k):
        self._d.pop(k, None)
        self._lists.pop(k, None)
        return True

@st.cache_resource
def get_redis():
    try:
        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        r.ping()
        return r, True
    except Exception:
        return MockRedis(), False

R, redis_live = get_redis()

# ── CONSTANTS ────────────────────────────────────────────────
TEAM_COLORS = {
    "ALPHA":   {"color": "#0099FF", "bg": "#001933", "icon": "🔵"},
    "CRIMSON": {"color": "#FF2244", "bg": "#330011", "icon": "🔴"},
    "VERDANT": {"color": "#00CC88", "bg": "#003322", "icon": "🟢"},
    "AURUM":   {"color": "#FFB800", "bg": "#332500", "icon": "🟡"},
}

CELL_COLORS = {"": "#0a0a14", "ALPHA": "#001a3a", "CRIMSON": "#2a0011", "VERDANT": "#00221a", "AURUM": "#221500"}
CELL_GLOW   = {"": "transparent", "ALPHA": "#0099FF", "CRIMSON": "#FF2244", "VERDANT": "#00CC88", "AURUM": "#FFB800"}

TASKS = {
    "monarch": [
        {"id":"m1","title":"Cipher of Seven Seals",    "diff":"EASY",   "pts":500,  "desc":"Decode a Caesar-13 shift applied to the royal decree."},
        {"id":"m2","title":"The Merchant's Paradox",   "diff":"MEDIUM", "pts":750,  "desc":"Solve the riddle: which merchant owes the crown gold?"},
        {"id":"m3","title":"Labyrinth of Mirrors",     "diff":"MEDIUM", "pts":750,  "desc":"Navigate the logic grid — only one path leads to the throne."},
        {"id":"m4","title":"The Dragon's Number",      "diff":"HARD",   "pts":1000, "desc":"Find the prime p where p^2 - p + 41 is also prime, beyond p=40."},
    ],
    "sovereign": [
        {"id":"s1","title":"API Backoff Optimizer",    "diff":"EASY",   "pts":500,  "desc":"Implement exponential backoff with jitter for HTTP retries.",
         "starter": "import time, random\n\ndef backoff_retry(max_retries=5):\n    for attempt in range(max_retries):\n        # Your code here\n        pass\n\nbackoff_retry()"},
        {"id":"s2","title":"BFS Territory Scanner",    "diff":"MEDIUM", "pts":750,  "desc":"Write BFS to find all cells reachable within N moves on a 10x10 grid.",
         "starter": "from collections import deque\n\ndef bfs_reachable(start, n, grid_size=10):\n    # Your BFS implementation here\n    visited = set()\n    queue = deque([(start, 0)])\n    # ...\n    return visited\n\nprint(bfs_reachable(0, 3))"},
        {"id":"s3","title":"Territory Score Calc",     "diff":"MEDIUM", "pts":750,  "desc":"Write a function to compute team scores from a grid list.",
         "starter": "def compute_scores(grid):\n    scores = {}\n    for cell in grid:\n        if cell:\n            scores[cell] = scores.get(cell, 0) + 1\n    return scores\n\ngrid = ['ALPHA','ALPHA','CRIMSON','',  'VERDANT']\nprint(compute_scores(grid))"},
        {"id":"s4","title":"Sovereign Strategy Engine","diff":"HARD",   "pts":1000, "desc":"Code a greedy+lookahead function to maximize territory gain.",
         "starter": "def best_attack(my_cells, enemy_grid):\n    # Greedy strategy: find most isolated enemy cell\n    # Return index of best cell to capture\n    pass\n\nprint(best_attack([0,1,10], ['CRIMSON']*100))"},
    ],
}

DIFF_COLOR = {"EASY": "#00CC88", "MEDIUM": "#FFB800", "HARD": "#FF2244"}

# ── AUTH HELPERS ─────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def load_users():
    raw = R.get("ot:users")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}

def save_users(users):
    R.set("ot:users", json.dumps(users))

def load_teams_meta():
    raw = R.get("ot:teams_meta")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}

def save_teams_meta(teams_meta):
    R.set("ot:teams_meta", json.dumps(teams_meta))

def register_user(username, password, display_name):
    users = load_users()
    if username in users:
        return False, "Username already exists."
    users[username] = {
        "pw_hash": hash_pw(password),
        "display_name": display_name,
        "team": None,
        "created": datetime.utcnow().isoformat(),
    }
    save_users(users)
    return True, "Account created!"

def login_user(username, password):
    users = load_users()
    if username not in users:
        return False, "User not found."
    if users[username]["pw_hash"] != hash_pw(password):
        return False, "Wrong password."
    return True, users[username]

def get_user(username):
    users = load_users()
    return users.get(username)

def update_user_team(username, team_name):
    users = load_users()
    if username in users:
        users[username]["team"] = team_name
        save_users(users)

def create_team(team_name, creator_username):
    teams_meta = load_teams_meta()
    if team_name in teams_meta:
        return False, "Team name already taken."
    if team_name not in TEAM_COLORS:
        return False, "Invalid team slot."
    teams_meta[team_name] = {
        "creator": creator_username,
        "members": [creator_username],
        "created": datetime.utcnow().isoformat(),
    }
    save_teams_meta(teams_meta)
    update_user_team(creator_username, team_name)
    return True, f"Team {team_name} created!"

def join_team(team_name, username):
    teams_meta = load_teams_meta()
    if team_name not in teams_meta:
        return False, "Team doesn't exist yet — create it first."
    if username in teams_meta[team_name]["members"]:
        return False, "Already in this team."
    teams_meta[team_name]["members"].append(username)
    save_teams_meta(teams_meta)
    update_user_team(username, team_name)
    return True, f"Joined {team_name}!"

# ── GAME STATE HELPERS ───────────────────────────────────────
def _init_state():
    grid = [""] * 100
    seeds = {
        "ALPHA":   [0,1,2,10,11,20],
        "CRIMSON": [9,8,19,18,29,28],
        "VERDANT": [70,80,81,90,91,92],
        "AURUM":   [77,78,87,88,98,99],
    }
    for t, cells in seeds.items():
        for c in cells:
            grid[c] = t
    return {
        "grid": grid,
        "hp":   {t: 5000 for t in TEAM_COLORS},
        "ap":   {t: 1200 for t in TEAM_COLORS},
        "epoch": 1,
        "phase": "MOBILIZATION",
        "epoch_end": (datetime.utcnow() + timedelta(minutes=15)).isoformat(),
    }

def load_gs():
    raw = R.get("ot:state")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    s = _init_state()
    R.set("ot:state", json.dumps(s))
    return s

def save_gs(s):
    R.set("ot:state", json.dumps(s))

def push_ev(kind, msg, team=None):
    ev = {"ts": datetime.utcnow().strftime("%H:%M:%S"), "kind": kind, "msg": msg, "team": team}
    R.lpush("ot:events", json.dumps(ev))

def load_evs():
    raw = R.lrange("ot:events", 0, 24)
    out = []
    for r in raw:
        try:
            out.append(json.loads(r))
        except Exception:
            pass
    return out

def terr_count(grid):
    c = {t: 0 for t in TEAM_COLORS}
    c[""] = 0
    for cell in grid:
        if cell in c:
            c[cell] += 1
    return c

# ── CODE EXECUTION ───────────────────────────────────────────
def run_code_safe(code: str, timeout: int = 5) -> tuple[str, str]:
    """Run user Python code in restricted subprocess. Returns (stdout, stderr)."""
    blocked = ["import os", "import sys", "import subprocess", "open(", "__import__",
               "exec(", "eval(", "compile(", "os.system", "os.popen", "shutil"]
    for b in blocked:
        if b in code:
            return "", f"[SECURITY] Blocked keyword detected: '{b}'"
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout[:3000], result.stderr[:1000]
    except subprocess.TimeoutExpired:
        return "", "[TIMEOUT] Code exceeded 5-second limit."
    except Exception as e:
        return "", str(e)

# ── AUTH GATE ────────────────────────────────────────────────
def show_auth_page():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
    *, *::before, *::after { box-sizing: border-box; }
    :root { --void:#03030a; --panel:#080813; --card:#0c0c1a; --gold:#D4AF37; --goldb:#FFD700; --cyan:#00E5FF; --dim:#3a3a5a; --text:#dde0ee; }
    .stApp { background-color: var(--void) !important;
        background-image: radial-gradient(ellipse 90% 50% at 50% 0%, rgba(0,150,255,0.07) 0%, transparent 55%),
        repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(255,255,255,0.012) 3px, rgba(255,255,255,0.012) 4px);
        font-family: 'Rajdhani', sans-serif; color: var(--text); }
    .main .block-container { max-width: 540px !important; padding-top: 2rem !important; }
    .stButton > button { font-family:'Orbitron',monospace !important; font-size:0.58rem !important; letter-spacing:2px !important;
        text-transform:uppercase !important; background:transparent !important; border:1px solid rgba(212,175,55,0.4) !important;
        color:var(--gold) !important; border-radius:2px !important; padding:0.55rem 0.9rem !important; width:100%; transition:all 0.2s !important; }
    .stButton > button:hover { background:rgba(212,175,55,0.1) !important; box-shadow:0 0 16px rgba(212,175,55,0.18) !important; }
    [data-testid="stTextInput"] input { background:var(--card) !important; border:1px solid rgba(212,175,55,0.25) !important;
        border-radius:2px !important; color:var(--text) !important; font-family:'Share Tech Mono',monospace !important; }
    [data-testid="stSelectbox"] > div > div { background:var(--card) !important; border:1px solid rgba(212,175,55,0.25) !important;
        border-radius:2px !important; color:var(--text) !important; font-family:'Share Tech Mono',monospace !important; }
    [data-testid="stSidebar"] { display:none !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center;margin-bottom:2rem">
        <div style="font-family:'Orbitron',monospace;font-size:2.2rem;font-weight:900;letter-spacing:6px;
            background:linear-gradient(135deg,#b8892a 0%,#FFD700 45%,#D4AF37 70%,#FFF5CC 100%);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;">OVERTHRONE</div>
        <div style="font-family:'Share Tech Mono',monospace;font-size:0.58rem;color:#3a3a5a;letter-spacing:3px;margin-top:4px">
            HELIX x ISTE · WAR ROOM OS v5.0</div>
    </div>
    """, unsafe_allow_html=True)

    tab = st.radio("", ["LOGIN", "REGISTER"], horizontal=True, label_visibility="collapsed")

    if tab == "LOGIN":
        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
        username = st.text_input("Username", key="login_user", placeholder="sovereign_handle")
        password = st.text_input("Password", key="login_pw", type="password", placeholder="••••••••")
        if st.button("ENTER THE WAR ROOM", use_container_width=True):
            if username and password:
                ok, result = login_user(username, password)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.user_data = result
                    st.rerun()
                else:
                    st.error(result)
            else:
                st.warning("Fill in all fields.")

    else:  # REGISTER
        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
        display_name = st.text_input("Display Name", key="reg_display", placeholder="Your Sovereign Name")
        username     = st.text_input("Username",     key="reg_user",    placeholder="unique_handle")
        password     = st.text_input("Password",     key="reg_pw",      type="password", placeholder="min 6 characters")
        pw2          = st.text_input("Confirm Password", key="reg_pw2", type="password", placeholder="repeat password")
        if st.button("CREATE ACCOUNT", use_container_width=True):
            if not all([display_name, username, password, pw2]):
                st.warning("Fill in all fields.")
            elif password != pw2:
                st.error("Passwords don't match.")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                ok, msg = register_user(username, password, display_name)
                if ok:
                    st.success(msg + " — Please login.")
                else:
                    st.error(msg)

    st.markdown("""
    <div style="margin-top:3rem;text-align:center;font-family:'Share Tech Mono',monospace;font-size:0.55rem;color:#222238">
        WILL YOU RULE THE MAP OR BE OVERTHROWN?
    </div>
    """, unsafe_allow_html=True)

# ── TEAM ASSIGNMENT PAGE ─────────────────────────────────────
def show_team_page():
    username = st.session_state.username
    teams_meta = load_teams_meta()

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
    .stApp { background-color:#03030a !important;
        background-image:radial-gradient(ellipse 90% 50% at 50% 0%,rgba(0,150,255,0.07) 0%,transparent 55%),
        repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(255,255,255,0.012) 3px,rgba(255,255,255,0.012) 4px);
        font-family:'Rajdhani',sans-serif;color:#dde0ee; }
    .main .block-container { max-width:700px !important; padding-top:1.5rem !important; }
    .stButton > button { font-family:'Orbitron',monospace !important; font-size:0.58rem !important; letter-spacing:2px !important;
        text-transform:uppercase !important; background:transparent !important; border:1px solid rgba(212,175,55,0.4) !important;
        color:#D4AF37 !important; border-radius:2px !important; padding:0.5rem !important; transition:all 0.2s !important; }
    .stButton > button:hover { background:rgba(212,175,55,0.1) !important; }
    [data-testid="stSidebar"] { display:none !important; }
    </style>
    """, unsafe_allow_html=True)

    user = get_user(username)
    dn = user.get("display_name", username) if user else username

    st.markdown(f"""
    <div style="text-align:center;margin-bottom:1.5rem">
        <div style="font-family:'Orbitron',monospace;font-size:1.6rem;font-weight:900;letter-spacing:6px;
            background:linear-gradient(135deg,#b8892a 0%,#FFD700 45%,#D4AF37 70%,#FFF5CC 100%);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;">OVERTHRONE</div>
        <div style="font-family:'Share Tech Mono',monospace;font-size:0.6rem;color:#3a3a5a;letter-spacing:3px;margin-top:4px">
            WELCOME, {dn.upper()} — CHOOSE YOUR KINGDOM</div>
    </div>
    """, unsafe_allow_html=True)

    for tname, tinfo in TEAM_COLORS.items():
        c    = tinfo["color"]
        icon = tinfo["icon"]
        bg   = tinfo["bg"]
        meta = teams_meta.get(tname, None)
        member_count = len(meta["members"]) if meta else 0
        created = meta is not None

        cols = st.columns([2, 1, 1], gap="small")
        with cols[0]:
            status_txt = f"{member_count} members" if created else "No team yet"
            status_col = "#00CC88" if created else "#3a3a5a"
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,{bg} 0%,#0c0c1a 100%);border:1px solid {c}33;border-left:3px solid {c};
                        border-radius:3px;padding:0.8rem 1rem;margin-bottom:4px">
                <div style="font-family:'Orbitron',monospace;font-size:0.65rem;letter-spacing:2px;color:{c}">{icon} TEAM {tname}</div>
                <div style="font-family:'Share Tech Mono',monospace;font-size:0.6rem;color:{status_col};margin-top:3px">{status_txt}</div>
            </div>
            """, unsafe_allow_html=True)
        with cols[1]:
            if not created:
                if st.button(f"CREATE", key=f"create_{tname}", use_container_width=True):
                    ok, msg = create_team(tname, username)
                    if ok:
                        st.session_state.user_data = get_user(username)
                        push_ev("SYS", f"Team {tname} created by {dn}", tname)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.markdown("<div style='height:42px'></div>", unsafe_allow_html=True)
        with cols[2]:
            if created:
                if st.button(f"JOIN", key=f"join_{tname}", use_container_width=True):
                    ok, msg = join_team(tname, username)
                    if ok:
                        st.session_state.user_data = get_user(username)
                        push_ev("SYS", f"{dn} joined Team {tname}", tname)
                        st.rerun()
                    else:
                        st.error(msg)

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    if st.button("LOGOUT", use_container_width=False):
        for k in ["logged_in","username","user_data","active_tab","cooldown","ws_log","seeded","code_outputs"]:
            st.session_state.pop(k, None)
        st.rerun()

# ─────────────────────────────────────────────────────────────
#  MAIN WAR ROOM
# ─────────────────────────────────────────────────────────────
def show_war_room():
    username = st.session_state.username
    user     = get_user(username)
    MT       = user["team"]   # e.g. "ALPHA"
    dn       = user.get("display_name", username)

    # ── SESSION DEFAULTS ─────────────────────────────────────
    if "active_tab" not in st.session_state: st.session_state.active_tab = "TASKS"
    if "cooldown"   not in st.session_state: st.session_state.cooldown   = {}
    if "ws_log"     not in st.session_state: st.session_state.ws_log     = []
    if "code_outputs" not in st.session_state: st.session_state.code_outputs = {}
    if "seeded"     not in st.session_state:
        push_ev("SYS",     "Epoch 1 commenced — kingdoms mobilizing")
        push_ev("TASK",    "Team Alpha completed API Backoff +750 AP", "ALPHA")
        push_ev("ATTACK",  "Team Crimson assaulted Sector 7", "CRIMSON")
        push_ev("ALLIANCE","Alliance formed: Verdant and Aurum", "VERDANT")
        st.session_state.seeded = True

    # ── LOAD DATA ────────────────────────────────────────────
    gs   = load_gs()
    evs  = load_evs()
    tc   = terr_count(gs["grid"])
    teams_meta = load_teams_meta()

    try:
        epoch_end = datetime.fromisoformat(gs["epoch_end"])
        remaining = max(0.0, (epoch_end - datetime.utcnow()).total_seconds())
    except Exception:
        remaining = 450.0

    pct_left  = remaining / 900.0
    mins_left = int(remaining // 60)
    secs_left = int(remaining % 60)
    MY_COLOR  = TEAM_COLORS[MT]["color"]

    # ── STYLES ───────────────────────────────────────────────
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
*, *::before, *::after { box-sizing: border-box; }
:root {
    --void:#03030a; --panel:#080813; --card:#0c0c1a; --gold:#D4AF37; --goldb:#FFD700;
    --cyan:#00E5FF; --red:#FF2244; --green:#00CC88; --purple:#CC44FF; --dim:#3a3a5a;
    --muted:#222238; --text:#dde0ee; --bdim:rgba(255,255,255,0.05); --bgold:rgba(212,175,55,0.25);
}
.stApp {
    background-color:var(--void) !important;
    background-image:
        radial-gradient(ellipse 90% 50% at 50% 0%,rgba(0,150,255,0.07) 0%,transparent 55%),
        radial-gradient(ellipse 70% 60% at 95% 100%,rgba(212,175,55,0.05) 0%,transparent 50%),
        repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(255,255,255,0.012) 3px,rgba(255,255,255,0.012) 4px);
    font-family:'Rajdhani',sans-serif; color:var(--text);
}
.main .block-container { padding:0.75rem 1.25rem 2rem !important; max-width:1700px !important; }
::-webkit-scrollbar { width:3px; height:3px; }
::-webkit-scrollbar-track { background:#06060f; }
::-webkit-scrollbar-thumb { background:var(--gold); border-radius:2px; }
[data-testid="stSidebar"] {
    background:linear-gradient(160deg,#05050f 0%,#09091a 100%) !important;
    border-right:1px solid rgba(212,175,55,0.2) !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top:0 !important; }
.stButton > button {
    font-family:'Orbitron',monospace !important; font-size:0.58rem !important;
    letter-spacing:2px !important; text-transform:uppercase !important;
    background:transparent !important; border:1px solid rgba(212,175,55,0.3) !important;
    color:var(--gold) !important; border-radius:2px !important; padding:0.45rem 0.9rem !important;
    width:100%; transition:all 0.2s !important;
}
.stButton > button:hover { background:rgba(212,175,55,0.1) !important; box-shadow:0 0 16px rgba(212,175,55,0.18) !important; color:var(--goldb) !important; }
.stButton > button:disabled { opacity:0.35 !important; cursor:not-allowed !important; }
[data-testid="stSelectbox"] > div > div { background:var(--card) !important; border:1px solid rgba(212,175,55,0.25) !important; border-radius:2px !important; color:var(--text) !important; font-family:'Share Tech Mono',monospace !important; font-size:0.8rem !important; }
[data-testid="stTextInput"] input { background:var(--card) !important; border:1px solid rgba(212,175,55,0.25) !important; border-radius:2px !important; color:var(--text) !important; font-family:'Share Tech Mono',monospace !important; font-size:0.8rem !important; }
[data-testid="stTextArea"] textarea { background:#000 !important; border:1px solid rgba(0,229,255,0.3) !important; border-radius:2px !important; color:#00E5FF !important; font-family:'Share Tech Mono',monospace !important; font-size:0.82rem !important; }
[data-testid="stExpander"] { background:var(--card) !important; border:1px solid var(--bdim) !important; border-radius:3px !important; }
.stProgress > div > div > div { background:linear-gradient(90deg,var(--gold),var(--goldb)) !important; box-shadow:0 0 6px var(--gold) !important; }
.stProgress > div > div { background:rgba(212,175,55,0.08) !important; }
[data-testid="metric-container"] { background:var(--card) !important; border:1px solid rgba(212,175,55,0.2) !important; border-radius:3px !important; padding:0.8rem !important; }
[data-testid="stMetricLabel"] p { font-family:'Orbitron',monospace !important; font-size:0.52rem !important; letter-spacing:2px !important; color:var(--dim) !important; }
[data-testid="stMetricValue"] { font-family:'Orbitron',monospace !important; color:var(--goldb) !important; font-size:1.3rem !important; }
hr { border:none !important; border-top:1px solid rgba(212,175,55,0.15) !important; margin:0.8rem 0 !important; }
@keyframes scan  { from{transform:translateX(-100%)} to{transform:translateX(100%)} }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
@keyframes evIn  { from{opacity:0;transform:translateX(-6px)} to{opacity:1;transform:translateX(0)} }
.ot-hdr { display:flex;align-items:center;justify-content:space-between;padding:0.9rem 1.2rem;
    background:linear-gradient(90deg,rgba(212,175,55,0.05) 0%,transparent 70%);
    border-bottom:1px solid rgba(212,175,55,0.2);margin-bottom:1rem;position:relative;overflow:hidden; }
.ot-hdr::after { content:'';position:absolute;bottom:0;left:0;right:0;height:1px;
    background:linear-gradient(90deg,transparent,var(--gold),transparent);animation:scan 4s linear infinite; }
.ot-logo { font-family:'Orbitron',monospace;font-size:1.9rem;font-weight:900;letter-spacing:6px;
    background:linear-gradient(135deg,#b8892a 0%,#FFD700 45%,#D4AF37 70%,#FFF5CC 100%);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent; }
.ot-subtitle { font-family:'Share Tech Mono',monospace;font-size:0.58rem;color:var(--dim);letter-spacing:3px;margin-top:2px; }
.ot-live-badge { font-family:'Share Tech Mono',monospace;font-size:0.6rem;color:var(--green);
    border:1px solid var(--green);padding:2px 8px;border-radius:2px;animation:pulse 1.8s ease infinite; }
.ot-epoch-box { text-align:right; }
.ot-epoch-num { font-family:'Orbitron',monospace;font-size:1.3rem;font-weight:700;color:var(--gold);line-height:1; }
.ot-epoch-phase { font-family:'Share Tech Mono',monospace;font-size:0.55rem;letter-spacing:3px;color:var(--dim); }
.ot-timer { font-family:'Orbitron',monospace;font-size:1.5rem;font-weight:700;min-width:75px;text-align:right; }
.ot-tbar { height:2px;background:var(--muted);margin-bottom:1rem;overflow:hidden; }
.ot-tbar-fill { height:100%;background:linear-gradient(90deg,var(--gold),var(--goldb));box-shadow:0 0 8px var(--gold); }
.kcard { background:var(--card);border:1px solid rgba(255,255,255,0.05);border-radius:3px;padding:0.9rem 0.9rem 0.9rem 1.1rem;position:relative;overflow:hidden;transition:border-color 0.3s;margin-bottom:12px; }
.kcard:hover { border-color:rgba(212,175,55,0.3); }
.kcard-accent { position:absolute;top:0;left:0;width:3px;height:100%; }
.kcard-name { font-family:'Orbitron',monospace;font-size:0.62rem;letter-spacing:2px;margin-bottom:0.6rem; }
.kcard-stats { display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px; }
.kcard-sl { font-family:'Share Tech Mono',monospace;font-size:0.5rem;letter-spacing:2px;color:var(--dim); }
.kcard-sv { font-family:'Share Tech Mono',monospace;font-size:1rem;line-height:1.2; }
.mini-bar { height:3px;background:var(--muted);border-radius:2px;margin-top:3px;overflow:hidden; }
.mini-bar-f { height:100%;border-radius:2px; }
.you-tag { font-family:'Orbitron',monospace;font-size:0.42rem;letter-spacing:2px;padding:1px 5px;border-radius:1px;margin-left:6px;vertical-align:middle; }
.map-wrap { background:#000;border:1px solid rgba(212,175,55,0.25);border-radius:4px;padding:8px;
    box-shadow:0 0 40px rgba(0,0,0,0.6),inset 0 0 60px rgba(0,0,0,0.5);position:relative; }
.map-corner { position:absolute;width:14px;height:14px;border-color:rgba(212,175,55,0.4);border-style:solid; }
.map-corner.tl { top:4px;left:4px;border-width:1px 0 0 1px; }
.map-corner.tr { top:4px;right:4px;border-width:1px 1px 0 0; }
.map-corner.bl { bottom:4px;left:4px;border-width:0 0 1px 1px; }
.map-corner.br { bottom:4px;right:4px;border-width:0 1px 1px 0; }
.map-label { font-family:'Share Tech Mono',monospace;font-size:0.5rem;letter-spacing:4px;color:var(--dim);text-align:center;padding:4px 0 8px; }
.map-grid { display:grid;grid-template-columns:repeat(10,1fr);gap:3px; }
.map-cell { aspect-ratio:1;border-radius:1px;transition:all 0.3s cubic-bezier(.175,.885,.32,1.275);cursor:crosshair; }
.map-cell:hover { transform:scale(1.5);z-index:10;filter:brightness(2.5); }
.map-legend { display:flex;flex-wrap:wrap;gap:12px;margin-top:8px; }
.legend-item { display:flex;align-items:center;gap:6px;font-family:'Share Tech Mono',monospace;font-size:0.62rem;color:var(--dim); }
.legend-dot { width:8px;height:8px;border-radius:1px;flex-shrink:0; }
.sec-lbl { font-family:'Orbitron',monospace;font-size:0.5rem;letter-spacing:4px;color:var(--dim);margin-bottom:8px; }
.tc { background:var(--card);border:1px solid var(--bdim);border-radius:3px;padding:0.9rem;position:relative;overflow:hidden;transition:border-color 0.3s;margin-bottom:8px; }
.tc:hover { border-color:rgba(212,175,55,0.3); }
.tc-diff { position:absolute;top:8px;right:8px;font-family:'Orbitron',monospace;font-size:0.45rem;letter-spacing:2px;padding:2px 7px;border-radius:1px; }
.tc-title { font-family:'Orbitron',monospace;font-size:0.65rem;letter-spacing:1px;color:var(--gold);margin-bottom:0.4rem;margin-right:70px; }
.tc-desc  { font-size:0.78rem;color:var(--dim);line-height:1.5;margin-bottom:0.6rem; }
.tc-pts   { font-family:'Share Tech Mono',monospace;font-size:0.85rem;color:var(--cyan); }
.ev-feed { display:flex;flex-direction:column;gap:4px;max-height:300px;overflow-y:auto; }
.ev-item { padding:6px 10px;border-radius:2px;background:rgba(255,255,255,0.02);border-left:2px solid;display:flex;gap:8px;align-items:baseline;animation:evIn 0.3s ease-out;font-family:'Share Tech Mono',monospace;font-size:0.68rem; }
.ev-ts  { color:var(--muted);font-size:0.55rem;flex-shrink:0;white-space:nowrap; }
.ev-msg { color:var(--text); }
.ac { background:var(--card);border-radius:3px;padding:0.9rem;border:1px solid var(--bdim);text-align:center;transition:all 0.25s;margin-bottom:8px;position:relative;overflow:hidden; }
.ac:hover { transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,0.4); }
.ac-label { font-family:'Orbitron',monospace;font-size:0.52rem;letter-spacing:2px;margin-bottom:0.25rem; }
.ac-desc  { font-size:0.7rem;color:var(--dim);line-height:1.4; }
.ac-top   { position:absolute;top:0;left:0;right:0;height:2px; }
.lb-row { display:grid;grid-template-columns:28px 1fr 70px 50px 90px;align-items:center;gap:10px;padding:9px 12px;
    background:var(--card);border:1px solid var(--bdim);border-radius:2px;margin-bottom:4px;transition:border-color 0.2s; }
.lb-row:hover { border-color:rgba(212,175,55,0.3); }
.lb-rank { font-family:'Orbitron',monospace;font-size:0.65rem; }
.lb-name { font-family:'Orbitron',monospace;font-size:0.6rem;letter-spacing:1px; }
.lb-val  { font-family:'Share Tech Mono',monospace;font-size:0.8rem;text-align:right; }
.lb-bar-wrap { height:4px;background:var(--muted);border-radius:2px;overflow:hidden; }
.lb-bar-fill { height:100%;border-radius:2px; }
.sb-head { padding:1rem;border-bottom:1px solid rgba(212,175,55,0.2); }
.sb-section { padding:0.9rem;border-bottom:1px solid var(--bdim); }
.sb-title { font-family:'Orbitron',monospace;font-size:0.47rem;letter-spacing:4px;color:var(--muted);margin-bottom:0.7rem; }
.sb-row { display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem; }
.sb-lbl { font-family:'Share Tech Mono',monospace;font-size:0.68rem;color:var(--dim); }
.sb-val { font-family:'Share Tech Mono',monospace;font-size:0.68rem; }
.cd-bar { background:rgba(255,34,68,0.08);border:1px solid rgba(255,34,68,0.3);border-radius:3px;padding:0.6rem 0.9rem;font-family:'Share Tech Mono',monospace;font-size:0.72rem;color:#FF2244;margin-bottom:10px; }
.ws-term { background:#000;border:1px solid #111;border-radius:3px;padding:0.9rem;font-family:'Share Tech Mono',monospace;font-size:0.72rem;height:220px;overflow-y:auto;color:var(--green); }
.ws-ln { line-height:1.9; }
.ws-ln.err  { color:var(--red); }
.ws-ln.info { color:var(--cyan); }
.ws-ln.sys  { color:var(--dim); }
.elim-row { display:flex;justify-content:space-between;align-items:center;padding:5px 8px;border-bottom:1px solid var(--bdim);font-family:'Share Tech Mono',monospace;font-size:0.65rem; }
.code-term { background:#000810;border:1px solid rgba(0,229,255,0.25);border-radius:3px;padding:1rem;font-family:'Share Tech Mono',monospace;font-size:0.75rem;min-height:80px;overflow-y:auto;color:#00E5FF;white-space:pre-wrap; }
.code-term .stdout { color:#00E5FF; }
.code-term .stderr { color:#FF2244; }
.code-term .ok { color:#00CC88; }
.member-pill { display:inline-block;background:rgba(212,175,55,0.08);border:1px solid rgba(212,175,55,0.2);border-radius:2px;padding:1px 7px;font-family:'Share Tech Mono',monospace;font-size:0.6rem;color:#D4AF37;margin:2px; }
</style>
""", unsafe_allow_html=True)

    # ── SIDEBAR ───────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"""
        <div class="sb-head">
            <div class="ot-logo" style="font-size:1.1rem;letter-spacing:4px">OVERTHRONE</div>
            <div class="ot-subtitle" style="margin-top:3px">HELIX x ISTE · WAR ROOM OS</div>
        </div>
        """, unsafe_allow_html=True)

        # User identity
        st.markdown(f"""
        <div class="sb-section">
            <div class="sb-title">SOVEREIGN IDENTITY</div>
            <div class="sb-row">
                <span class="sb-lbl">USER</span>
                <span class="sb-val" style="color:{MY_COLOR}">{dn}</span>
            </div>
            <div class="sb-row">
                <span class="sb-lbl">TEAM</span>
                <span class="sb-val" style="color:{MY_COLOR}">{TEAM_COLORS[MT]['icon']} {MT}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Team members
        my_meta = teams_meta.get(MT, {})
        members = my_meta.get("members", [username])
        all_users = load_users()
        member_names = [all_users.get(m, {}).get("display_name", m) for m in members]
        pills = "".join(f'<span class="member-pill">{n}</span>' for n in member_names)
        st.markdown(f"""
        <div class="sb-section">
            <div class="sb-title">TEAM ROSTER</div>
            {pills}
        </div>
        """, unsafe_allow_html=True)

        my_hp   = int(gs["hp"].get(MT, 5000))
        my_ap   = int(gs["ap"].get(MT, 0))
        my_terr = tc.get(MT, 0)
        hp_p = max(0, my_hp / 5000)
        ap_p = min(my_ap / 3000, 1.0)

        st.markdown(f"""
        <div class="sb-section">
            <div class="sb-title">BIOMETRICS · LIVE</div>
            <div class="sb-row"><span class="sb-lbl">HEALTH POINTS</span>
                 <span class="sb-val" style="color:{MY_COLOR}">{my_hp:,}</span></div>
            <div class="mini-bar" style="margin-bottom:8px">
                <div class="mini-bar-f" style="width:{hp_p*100:.0f}%;background:{MY_COLOR};box-shadow:0 0 5px {MY_COLOR}"></div>
            </div>
            <div class="sb-row"><span class="sb-lbl">ATTACK POINTS</span>
                 <span class="sb-val" style="color:#00E5FF">{my_ap:,}</span></div>
            <div class="mini-bar" style="margin-bottom:8px">
                <div class="mini-bar-f" style="width:{ap_p*100:.0f}%;background:#00E5FF;box-shadow:0 0 5px #00E5FF"></div>
            </div>
            <div class="sb-row"><span class="sb-lbl">TERRITORY</span>
                 <span class="sb-val" style="color:#D4AF37">{my_terr} / 100 cells</span></div>
            <div class="mini-bar"><div class="mini-bar-f" style="width:{my_terr}%;background:#D4AF37"></div></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="sb-section">
            <div class="sb-title">EPOCH STATUS</div>
            <div class="sb-row"><span class="sb-lbl">EPOCH</span>
                 <span class="sb-val" style="color:#D4AF37">{gs['epoch']}</span></div>
            <div class="sb-row"><span class="sb-lbl">PHASE</span>
                 <span class="sb-val" style="color:#00E5FF;font-size:0.6rem">{gs['phase']}</span></div>
            <div class="sb-row"><span class="sb-lbl">REMAINING</span>
                 <span class="sb-val" style="color:{'#FF2244' if mins_left<3 else '#FFD700'}">{mins_left:02d}:{secs_left:02d}</span></div>
            <div class="mini-bar" style="margin-top:6px">
                <div class="mini-bar-f" style="width:{pct_left*100:.0f}%;background:linear-gradient(90deg,#D4AF37,#FFD700)"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="sb-section"><div class="sb-title">QUICK ACTIONS</div>', unsafe_allow_html=True)
        if st.button("SIMULATE EPOCH", use_container_width=True):
            new_grid = gs["grid"].copy()
            for t in TEAM_COLORS:
                ap_avail = int(gs["ap"].get(t, 0))
                if ap_avail < 200:
                    continue
                owned = [i for i, o in enumerate(new_grid) if o == t]
                targets = []
                for cell in owned:
                    r2, c2 = divmod(cell, 10)
                    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr, nc = r2+dr, c2+dc
                        if 0<=nr<10 and 0<=nc<10:
                            ni = nr*10+nc
                            if new_grid[ni] != t:
                                targets.append(ni)
                if targets:
                    tgt = random.choice(targets)
                    prev = new_grid[tgt]
                    new_grid[tgt] = t
                    gs["ap"][t] = ap_avail - 200
                    if prev:
                        gs["hp"][prev] = max(0, int(gs["hp"].get(prev, 5000)) - 100)
                    push_ev("ATTACK", f"Team {t} captured cell {tgt}", t)
            gs["grid"] = new_grid
            gs["epoch"] = gs["epoch"] + 1
            gs["epoch_end"] = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            save_gs(gs)
            st.rerun()

        if st.button("RESET GAME", use_container_width=True):
            R.set("ot:state", json.dumps(_init_state()))
            push_ev("SYS", "Game reset — new epoch begins")
            st.rerun()

        if st.button("REFRESH NOW", use_container_width=True):
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

        redis_col = "#00CC88" if redis_live else "#FF2244"
        redis_txt = "CONNECTED" if redis_live else "MOCK (local)"
        st.markdown(f"""
        <div class="sb-section">
            <div class="sb-title">SYSTEM STATUS</div>
            <div class="sb-row">
                <span class="sb-lbl">REDIS</span>
                <span style="font-family:'Share Tech Mono',monospace;font-size:0.62rem;color:{redis_col}">{redis_txt}</span>
            </div>
            <div class="sb-row">
                <span class="sb-lbl">WEBSOCKET</span>
                <span style="font-family:'Share Tech Mono',monospace;font-size:0.62rem;color:#00E5FF">:8765</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("LOGOUT", use_container_width=True):
            for k in ["logged_in","username","user_data","active_tab","cooldown","ws_log","seeded","code_outputs"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── HEADER ───────────────────────────────────────────────
    timer_color = "#FF2244" if mins_left < 3 else "#FFD700"
    st.markdown(f"""
<div class="ot-hdr">
    <div>
        <div class="ot-logo">OVERTHRONE</div>
        <div class="ot-subtitle">HELIX x ISTE · THE ULTIMATE KINGDOM SIMULATION</div>
    </div>
    <div style="display:flex;align-items:center;gap:1.2rem">
        <span class="ot-live-badge">LIVE</span>
        <div style="font-family:'Share Tech Mono',monospace;font-size:0.58rem;color:{MY_COLOR}">
            {TEAM_COLORS[MT]['icon']} {dn.upper()} · {MT}
        </div>
    </div>
    <div class="ot-epoch-box">
        <div class="ot-epoch-num">EPOCH {gs['epoch']}</div>
        <div class="ot-epoch-phase">{gs['phase']}</div>
    </div>
    <div class="ot-timer" style="color:{timer_color}">{mins_left:02d}:{secs_left:02d}</div>
</div>
<div class="ot-tbar"><div class="ot-tbar-fill" style="width:{pct_left*100:.1f}%"></div></div>
""", unsafe_allow_html=True)

    # ── KINGDOM STATUS ROW ───────────────────────────────────
    k_cols = st.columns(4, gap="small")
    for col, (tname, tinfo) in zip(k_cols, TEAM_COLORS.items()):
        hp   = int(gs["hp"].get(tname, 5000))
        ap   = int(gs["ap"].get(tname, 0))
        terr = tc.get(tname, 0)
        c    = tinfo["color"]
        bg   = tinfo["bg"]
        mine = tname == MT
        hp_p = max(0, hp/5000)
        ap_p = min(ap/3000, 1.0)
        badge = f'<span class="you-tag" style="background:{c}22;color:{c};border:1px solid {c}44">YOU</span>' if mine else ""
        border = f"border-color:{c}44;" if mine else ""
        with col:
            st.markdown(f"""
            <div class="kcard" style="{border}background:linear-gradient(135deg,{bg} 0%,var(--card) 100%)">
                <div class="kcard-accent" style="background:{c};box-shadow:0 0 8px {c}"></div>
                <div class="kcard-name" style="color:{c}">{tinfo['icon']} TEAM {tname}{badge}</div>
                <div class="kcard-stats">
                    <div><div class="kcard-sl">HP</div><div class="kcard-sv" style="color:{c}">{hp:,}</div>
                         <div class="mini-bar"><div class="mini-bar-f" style="width:{hp_p*100:.0f}%;background:{c}"></div></div></div>
                    <div><div class="kcard-sl">AP</div><div class="kcard-sv" style="color:#00E5FF">{ap:,}</div>
                         <div class="mini-bar"><div class="mini-bar-f" style="width:{ap_p*100:.0f}%;background:#00E5FF"></div></div></div>
                    <div><div class="kcard-sl">TERR</div><div class="kcard-sv" style="color:#D4AF37">{terr}</div>
                         <div class="kcard-sl" style="font-size:0.42rem">/100 cells</div></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── MAIN LAYOUT ──────────────────────────────────────────
    left_col, right_col = st.columns([2.3, 1], gap="large")

    with left_col:
        st.markdown('<div class="sec-lbl">SUB-SECTOR ALPHA-9 · BATTLE MAP · LIVE</div>', unsafe_allow_html=True)

        cells_html = ""
        for idx, owner in enumerate(gs["grid"]):
            bg   = CELL_COLORS.get(owner, "#0a0a14")
            glow = CELL_GLOW.get(owner, "transparent")
            shadow = f"inset 0 0 5px {glow}aa, 0 0 2px {glow}55" if owner else "none"
            cells_html += f'<div class="map-cell" title="Cell {idx}" style="background:{bg};box-shadow:{shadow}"></div>'

        legend_html = ""
        for tname, tinfo in TEAM_COLORS.items():
            legend_html += f'<div class="legend-item"><div class="legend-dot" style="background:{tinfo["color"]};box-shadow:0 0 4px {tinfo["color"]}"></div>TEAM {tname} ({tc.get(tname,0)})</div>'
        legend_html += '<div class="legend-item"><div class="legend-dot" style="background:#0a0a14;border:1px solid #222"></div>UNCLAIMED</div>'

        st.markdown(f"""
        <div class="map-wrap">
            <div class="map-corner tl"></div><div class="map-corner tr"></div>
            <div class="map-corner bl"></div><div class="map-corner br"></div>
            <div class="map-label">VIRTUAL BATTLEFIELD  10 x 10 GRID</div>
            <div class="map-grid">{cells_html}</div>
            <div class="map-legend" style="margin-top:8px">{legend_html}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # TAB BAR
        tab_names = ["TASKS", "CODE TERMINAL", "STRATEGY DECK", "LEADERBOARD", "WS TERMINAL"]
        tab_cols  = st.columns(len(tab_names), gap="small")
        for i, tname in enumerate(tab_names):
            with tab_cols[i]:
                if st.button(tname, key=f"tab_{tname}", use_container_width=True):
                    st.session_state.active_tab = tname

        active = st.session_state.active_tab
        st.markdown(f"<div style='font-family:ShareTechMono,monospace;font-size:0.55rem;color:var(--dim);margin-bottom:12px'>► {active}</div>", unsafe_allow_html=True)

        # ── TASKS TAB ──────────────────────────────────────────
        if active == "TASKS":
            cd_end = st.session_state.cooldown.get(MT, 0)
            cd_rem = max(0.0, cd_end - time.time())
            if cd_rem > 0:
                st.markdown(f'<div class="cd-bar">TASK CARD COOLDOWN — {int(cd_rem//60):02d}:{int(cd_rem%60):02d} remaining</div>', unsafe_allow_html=True)

            for section_key, section_label in [("monarch","MONARCH TASKS · MANUAL PUZZLES"), ("sovereign","SOVEREIGN TASKS · TECHNICAL CHALLENGES")]:
                st.markdown(f'<div class="sec-lbl" style="margin-top:10px">{section_label}</div>', unsafe_allow_html=True)
                tc_cols = st.columns(2, gap="small")
                for i, task in enumerate(TASKS[section_key]):
                    dc = DIFF_COLOR[task["diff"]]
                    with tc_cols[i % 2]:
                        st.markdown(f"""
                        <div class="tc">
                            <div class="tc-diff" style="background:{dc}18;color:{dc};border:1px solid {dc}44">{task['diff']}</div>
                            <div class="tc-title">{task['title']}</div>
                            <div class="tc-desc">{task['desc']}</div>
                            <div class="tc-pts">+{task['pts']} AP</div>
                        </div>
                        """, unsafe_allow_html=True)
                        btn_label = "CLAIM" if section_key == "monarch" else "EXECUTE"
                        if st.button(f"{btn_label} +{task['pts']}AP", key=f"task_{task['id']}", use_container_width=True, disabled=(cd_rem > 0)):
                            fail = random.random() < 0.15
                            if fail:
                                st.session_state.cooldown[MT] = time.time() + 900
                                push_ev("TASK", f"Task FAILED — Team {MT} entering cooldown", MT)
                                st.error("Task failed! 15-minute cooldown activated.")
                            else:
                                gs["ap"][MT] = int(gs["ap"].get(MT, 0)) + task["pts"]
                                save_gs(gs)
                                push_ev("TASK", f"Team {MT} ({dn}) completed '{task['title']}' +{task['pts']} AP", MT)
                                st.success(f"+{task['pts']} AP earned!")
                            st.rerun()

        # ── CODE TERMINAL TAB ──────────────────────────────────
        elif active == "CODE TERMINAL":
            st.markdown('<div class="sec-lbl">SOVEREIGN CODE TERMINAL · PYTHON EXECUTION ENGINE</div>', unsafe_allow_html=True)
            st.markdown("""
            <div style="background:rgba(0,229,255,0.04);border:1px solid rgba(0,229,255,0.15);border-radius:3px;padding:0.7rem 1rem;margin-bottom:12px;font-family:'Share Tech Mono',monospace;font-size:0.68rem;color:var(--dim)">
                Write Python code for Sovereign tasks. Execute to earn AP. Standard library available.
                <span style="color:#FF2244"> os, sys, subprocess blocked for security.</span>
            </div>
            """, unsafe_allow_html=True)

            # Task selector
            sov_task_names = {t["id"]: t["title"] for t in TASKS["sovereign"]}
            sel_id = st.selectbox(
                "Load task template",
                options=["custom"] + [t["id"] for t in TASKS["sovereign"]],
                format_func=lambda x: "— Custom Code —" if x == "custom" else f"{sov_task_names[x]}",
                key="code_task_sel",
            )

            default_code = "# Write your Python code here\nprint('Hello, War Room!')"
            if sel_id != "custom":
                task_obj = next((t for t in TASKS["sovereign"] if t["id"] == sel_id), None)
                if task_obj:
                    default_code = task_obj.get("starter", default_code)

            code_key = f"code_{sel_id}"
            if code_key not in st.session_state:
                st.session_state[code_key] = default_code

            user_code = st.text_area(
                "Code Editor",
                value=st.session_state[code_key],
                height=280,
                key=f"editor_{sel_id}",
                label_visibility="collapsed",
                placeholder="# Write Python here..."
            )
            st.session_state[code_key] = user_code

            run_col, submit_col = st.columns([1, 1], gap="small")
            with run_col:
                run_clicked = st.button("▶  RUN CODE", key="run_code", use_container_width=True)
            with submit_col:
                submit_clicked = st.button("✓  SUBMIT FOR AP", key="submit_code", use_container_width=True,
                                           disabled=(sel_id == "custom"))

            output_key = f"out_{sel_id}"
            if run_clicked:
                stdout, stderr = run_code_safe(user_code)
                st.session_state.code_outputs[output_key] = {"stdout": stdout, "stderr": stderr, "ts": datetime.utcnow().strftime("%H:%M:%S")}

            if submit_clicked and sel_id != "custom":
                stdout, stderr = run_code_safe(user_code)
                st.session_state.code_outputs[output_key] = {"stdout": stdout, "stderr": stderr, "ts": datetime.utcnow().strftime("%H:%M:%S")}
                task_obj = next((t for t in TASKS["sovereign"] if t["id"] == sel_id), None)
                if task_obj and not stderr:
                    fail = random.random() < 0.1
                    if fail:
                        push_ev("TASK", f"Code submission FAILED — Team {MT}", MT)
                        st.error("Submission rejected by the judges. Try again.")
                    else:
                        gs["ap"][MT] = int(gs["ap"].get(MT, 0)) + task_obj["pts"]
                        save_gs(gs)
                        push_ev("TASK", f"Team {MT} ({dn}) submitted code '{task_obj['title']}' +{task_obj['pts']} AP", MT)
                        st.success(f"✓ Accepted! +{task_obj['pts']} AP awarded to Team {MT}")
                    st.rerun()
                elif stderr:
                    st.error("Fix errors before submitting.")

            # Output terminal
            out = st.session_state.code_outputs.get(output_key)
            if out:
                ts   = out.get("ts", "")
                sout = out.get("stdout", "")
                serr = out.get("stderr", "")
                out_html = f'<div class="code-term">'
                out_html += f'<div style="color:#3a3a5a;font-size:0.55rem;margin-bottom:6px">RUN @ {ts}</div>'
                if sout:
                    out_html += f'<div class="stdout">{sout}</div>'
                if serr:
                    out_html += f'<div class="stderr">{serr}</div>'
                if not sout and not serr:
                    out_html += '<div class="ok">✓ No output</div>'
                out_html += '</div>'
                st.markdown(out_html, unsafe_allow_html=True)
            else:
                st.markdown('<div class="code-term" style="color:#222238">// Output will appear here after execution</div>', unsafe_allow_html=True)

        # ── STRATEGY DECK ──────────────────────────────────────
        elif active == "STRATEGY DECK":
            other_teams = [(tname, tinfo) for tname, tinfo in TEAM_COLORS.items() if tname != MT]
            enemy_names = [tname for tname, _ in other_teams]
            cards = [
                ("ATTACK",   "#FF2244", "ATTACK CARD",    "Spend 500 AP to invade a neighbouring enemy cell."),
                ("ALLIANCE", "#00CC88", "ALLIANCE CARD",  "Form a Non-Aggression Pact — both kingdoms share task slots."),
                ("BACKSTAB", "#9933FF", "BACKSTAB CARD",  "Secretly betray your ally and seize their territory for a massive bonus."),
                ("SUSPICION","#FFB800", "SUSPICION CARD", "Accuse an ally of preparing a backstab. Wrong = self-eliminate."),
            ]
            card_cols = st.columns(2, gap="small")
            for i, (cname, cc, clabel, cdesc) in enumerate(cards):
                with card_cols[i % 2]:
                    st.markdown(f"""
                    <div class="ac" style="border-color:{cc}22;border-top:2px solid {cc}">
                        <div class="ac-top" style="background:linear-gradient(90deg,{cc},transparent)"></div>
                        <div class="ac-label" style="color:{cc}">{clabel}</div>
                        <div class="ac-desc">{cdesc}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    target_name = st.selectbox(f"Target for {cname}", enemy_names, key=f"sel_{cname}", label_visibility="collapsed")
                    target_info = TEAM_COLORS.get(target_name, {})
                    if st.button(f"PLAY {cname}", key=f"play_{cname}", use_container_width=True):
                        if cname == "ATTACK":
                            if int(gs["ap"].get(MT, 0)) >= 500:
                                enemy_cells = [idx for idx, o in enumerate(gs["grid"]) if o == target_name]
                                if enemy_cells:
                                    tgt = random.choice(enemy_cells)
                                    gs["grid"][tgt] = MT
                                    gs["ap"][MT]           = int(gs["ap"].get(MT, 0)) - 500
                                    gs["hp"][target_name]  = max(0, int(gs["hp"].get(target_name, 5000)) - 100)
                                    save_gs(gs)
                                    push_ev("ATTACK", f"Team {MT} attacked {target_name} — cell {tgt} captured!", MT)
                                    st.success(f"Cell {tgt} captured from {target_name}!")
                                else:
                                    st.warning("No enemy cells to capture.")
                            else:
                                st.error("Insufficient AP — need 500 AP.")
                            st.rerun()
                        elif cname == "ALLIANCE":
                            push_ev("ALLIANCE", f"Non-Aggression Pact: Team {MT} and {target_name}", MT)
                            st.success(f"Alliance forged with {target_name}!")
                        elif cname == "BACKSTAB":
                            enemy_cells = [idx for idx, o in enumerate(gs["grid"]) if o == target_name]
                            captured = random.randint(3, min(6, max(1, len(enemy_cells)))) if enemy_cells else 0
                            chosen = random.sample(enemy_cells, captured) if enemy_cells else []
                            for c in chosen:
                                gs["grid"][c] = MT
                            gs["hp"][target_name] = max(0, int(gs["hp"].get(target_name, 5000)) - captured * 250)
                            save_gs(gs)
                            push_ev("BACKSTAB", f"BACKSTAB! Team {MT} betrayed {target_name} — {captured} cells seized!", MT)
                            st.success(f"Backstab! {captured} cells captured from {target_name}!")
                            st.rerun()
                        elif cname == "SUSPICION":
                            correct = random.random() < 0.5
                            if correct:
                                push_ev("SUSPICION", f"Team {MT} correctly accused {target_name} — ELIMINATED!", MT)
                                st.success(f"Correct! {target_name} was plotting — ELIMINATED!")
                            else:
                                push_ev("SUSPICION", f"Team {MT} falsely accused {target_name} — self-eliminated!", MT)
                                st.error("False accusation — your kingdom pays the price!")
                            st.rerun()

        # ── LEADERBOARD ────────────────────────────────────────
        elif active == "LEADERBOARD":
            ranked = sorted(TEAM_COLORS.items(), key=lambda x: (tc.get(x[0], 0), int(gs["hp"].get(x[0], 0))), reverse=True)
            rank_icons  = ["#1", "#2", "#3", "#4"]
            rank_colors = ["#FFD700","#C0C0C0","#CD7F32","#444"]

            # Members per team
            all_users = load_users()
            for rank, (tname, tinfo) in enumerate(ranked):
                hp   = int(gs["hp"].get(tname, 0))
                terr = tc.get(tname, 0)
                c    = tinfo["color"]
                mine_style = f"border-color:{c}44;background:{c}08;" if tname == MT else ""
                mine_flag  = "  YOURS" if tname == MT else ""
                meta  = teams_meta.get(tname, {})
                mbrs  = meta.get("members", [])
                mbr_names = [all_users.get(m, {}).get("display_name", m) for m in mbrs]
                mbr_str = ", ".join(mbr_names) if mbr_names else "—"
                st.markdown(f"""
                <div class="lb-row" style="{mine_style}">
                    <div class="lb-rank" style="color:{rank_colors[rank]}">{rank_icons[rank]}</div>
                    <div>
                        <div class="lb-name" style="color:{c}">{tinfo['icon']} TEAM {tname}{mine_flag}</div>
                        <div style="font-family:'Share Tech Mono',monospace;font-size:0.52rem;color:var(--dim);margin-top:2px">{mbr_str}</div>
                    </div>
                    <div class="lb-val" style="color:#D4AF37">{hp:,}</div>
                    <div class="lb-val" style="color:#00E5FF">{terr}</div>
                    <div class="lb-bar-wrap">
                        <div class="lb-bar-fill" style="width:{terr}%;background:{c};box-shadow:0 0 5px {c}"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        # ── WS TERMINAL ────────────────────────────────────────
        elif active == "WS TERMINAL":
            st.markdown('<div class="sec-lbl">REAL-TIME WEBSOCKET STREAM</div>', unsafe_allow_html=True)
            wc1, wc2 = st.columns([3, 1], gap="small")
            with wc1:
                ws_in = st.text_input("msg", placeholder="e.g. ATTACK:team_alpha:cell42", label_visibility="collapsed")
            with wc2:
                if st.button("TRANSMIT", use_container_width=True):
                    if ws_in:
                        push_ev("WS_TX", f"TX: {ws_in}", MT)
                        st.session_state.ws_log.append({"t":"info","m": f">>> {ws_in}"})
                        st.session_state.ws_log.append({"t":"sys", "m": f"[{datetime.utcnow().strftime('%H:%M:%S')}] Queued for broadcast"})
                        st.rerun()

            base_lines = [
                {"t":"sys",  "m":"[SYSTEM] ws://localhost:8765 · Status: LISTENING"},
                {"t":"sys",  "m":"[SYSTEM] Connected clients: 4 · Redis pub/sub: ACTIVE"},
                {"t":"info", "m":"[00:01:12] EPOCH_START · Epoch 1 · Phase: MOBILIZATION"},
                {"t":"info", "m":"[00:02:44] TASK_COMPLETE · Team Alpha · +750 AP"},
                {"t":"err",  "m":"[00:03:11] ATTACK · Crimson → Alpha · Cell 15 captured"},
                {"t":"info", "m":"[00:05:30] ALLIANCE · Verdant + Aurum pact formed"},
                {"t":"err",  "m":"[00:08:01] BACKSTAB · Aurum betrayed Verdant · 5 cells!"},
            ] + st.session_state.ws_log[-8:]

            lines_html = "".join(f'<div class="ws-ln {l["t"]}">{l["m"]}</div>' for l in base_lines)
            st.markdown(f'<div class="ws-term">{lines_html}</div>', unsafe_allow_html=True)

            with st.expander("ws_server.py — run in separate terminal"):
                st.code("""import asyncio, websockets, json, redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
CLIENTS = set()

async def handler(ws, path="/"):
    CLIENTS.add(ws)
    try:
        async for msg in ws:
            data = json.loads(msg)
            r.lpush("ot:events", json.dumps(data))
            r.publish("ot:ws", json.dumps(data))
            if CLIENTS:
                await asyncio.gather(*[c.send(json.dumps(data)) for c in CLIENTS])
    finally:
        CLIENTS.discard(ws)

async def main():
    async with websockets.serve(handler, "localhost", 8765):
        print("WS Server ready · ws://localhost:8765")
        await asyncio.Future()

asyncio.run(main())""", language="python")

    # ── RIGHT COLUMN ──────────────────────────────────────────
    with right_col:
        st.markdown('<div class="sec-lbl">COMMS FEED · LIVE</div>', unsafe_allow_html=True)

        EV_COLORS = {
            "ATTACK":"#FF2244","BACKSTAB":"#9933FF","ALLIANCE":"#00CC88",
            "SUSPICION":"#FFB800","TASK":"#00E5FF","SYS":"#333355","WS_TX":"#00CC88",
        }
        if not evs:
            for m, k in [("Epoch 1 commenced","SYS"),("Alpha +750 AP","TASK"),
                         ("Crimson assaulted Sector 7","ATTACK"),("Verdant + Aurum alliance","ALLIANCE")]:
                push_ev(k, m)
            evs = load_evs()

        feed_html = '<div class="ev-feed">'
        for ev in evs[:22]:
            bc = EV_COLORS.get(ev.get("kind","SYS"), "#333355")
            feed_html += f'<div class="ev-item" style="border-left-color:{bc}"><span class="ev-ts">{ev.get("ts","--:--:--")}</span><span class="ev-msg">{ev.get("msg","")}</span></div>'
        feed_html += '</div>'
        st.markdown(feed_html, unsafe_allow_html=True)

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="sec-lbl">ARMORY · ACTION CARDS</div>', unsafe_allow_html=True)

        armory = [
            ("ATTACK CARD",   "#FF2244","Spend AP to invade enemy cells."),
            ("ALLIANCE CARD", "#00CC88","Non-Aggression Pact with ally."),
            ("BACKSTAB CARD", "#9933FF","Betray ally for massive bonus."),
            ("SUSPICION CARD","#FFB800","Accuse ally of treason."),
            ("TASK CARD",     "#00E5FF","Earn AP via challenges."),
            ("CODE TERMINAL", "#CC44FF","Execute code for Sovereign tasks."),
        ]
        for label, cc, desc in armory:
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;padding:7px 10px;
                        background:var(--card);border:1px solid {cc}1a;border-left:2px solid {cc};
                        border-radius:2px;margin-bottom:3px">
                <div>
                    <div style="font-family:'Orbitron',monospace;font-size:0.52rem;letter-spacing:2px;color:{cc}">{label}</div>
                    <div style="font-size:0.7rem;color:var(--dim)">{desc}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="sec-lbl">ELIMINATION TRACKER</div>', unsafe_allow_html=True)

        ranked_e = sorted(TEAM_COLORS.items(), key=lambda x: int(gs["hp"].get(x[0], 0)), reverse=True)
        for tname, tinfo in ranked_e:
            hp = int(gs["hp"].get(tname, 5000))
            status = "ELIMINATED" if hp <= 0 else "ACTIVE"
            sc = "#FF2244" if hp <= 0 else "#00CC88"
            st.markdown(f"""
            <div class="elim-row">
                <span style="color:{tinfo['color']}">{tinfo['icon']} TEAM {tname}</span>
                <span style="font-family:'Orbitron',monospace;font-size:0.48rem;letter-spacing:2px;color:{sc}">{status}</span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("""
<div style="margin-top:2rem;padding:0.8rem 0;border-top:1px solid rgba(212,175,55,0.12);
            display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
    <div style="font-family:'Share Tech Mono',monospace;font-size:0.58rem;color:#3a3a5a">
        OVERTHRONE WAR ROOM OS · HELIX x ISTE · v5.0
    </div>
    <div style="font-family:'Orbitron',monospace;font-size:0.52rem;letter-spacing:2px;color:#D4AF37">
        WILL YOU RULE THE MAP OR BE OVERTHROWN?
    </div>
</div>
""", unsafe_allow_html=True)

# ── ROUTER ───────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    show_auth_page()
else:
    user = get_user(st.session_state.username)
    if not user or not user.get("team"):
        show_team_page()
    else:
        st.session_state.user_data = user
        show_war_room()

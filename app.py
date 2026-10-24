"""Samantha (MemoMate) - An Intimate Diary & Memory Companion inspired by the film 'Her'.
Built for the MongoDB Hackathon (Agentic Memory Track).
Features:
- Dual Aesthetic Themes: 'Velvet Dusk' (Dark) & 'Warm Dawn' (Light)
- Spike Jonze 'Her' Cinematic Visual Identity (OS1 Pulse, Playfair & Instrument Serif typography)
- Relaxing Ambient Music Player (Soundtrack mood)
- 1-Click Interactive Hackathon Demo Flow
- Dynamic Memory Cortex (MongoDB Vector Search, TTL Expiry, Replaced History)
"""
import os
import streamlit as st
from dotenv import load_dotenv

import agent
import brain
import db
from embeddings import embed

load_dotenv()

st.set_page_config(
    page_title="Samantha • OS1 Companion",
    page_icon="🔴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Theme State Management ---
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "🌙 Velvet Dusk"

# Sidebar: Theme Selector
st.sidebar.markdown("""
<div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
    <span style="font-size:1.1rem;">🎨</span>
    <span style="font-weight:600; font-size:0.88rem; letter-spacing:0.5px; text-transform:uppercase;">Atmosphere</span>
</div>
""", unsafe_allow_html=True)

theme_choice = st.sidebar.radio(
    "Select Atmosphere",
    ["🌙 Velvet Dusk", "☀️ Warm Dawn"],
    index=0 if "Velvet" in st.session_state.theme_mode else 1,
    label_visibility="collapsed",
    horizontal=True,
)
st.session_state.theme_mode = theme_choice
is_dark = "Velvet" in theme_choice

# --- Design Tokens (Dark vs Light) ---
if is_dark:
    theme_vars = """
    --her-bg: #140E0F;
    --her-bg-gradient: radial-gradient(circle at 18% 14%, rgba(226, 85, 69, 0.12) 0%, transparent 45%), radial-gradient(circle at 85% 82%, rgba(229, 169, 82, 0.07) 0%, transparent 42%);
    --her-surface: #1E1617;
    --her-surface-hover: #261D1E;
    --her-border: rgba(226, 85, 69, 0.28);
    --her-header-bg: rgba(28, 20, 21, 0.88);
    --her-sidebar-bg: #171011;
    --her-user-bubble: #281B1C;
    --her-assistant-bubble: #1C1415;
    --her-text: #F7F2EF;
    --her-muted: #BCAAA7;
    --her-faint: #7E6C69;
    --her-title: #FF7B6D;
    --her-pill-bg: #1F1617;
    --her-pill-border: rgba(226, 85, 69, 0.24);
    --her-btn-bg: #241A1B;
    --her-btn-text: #F7F2EF;
    --her-expander-bg: #1B1314;
    --her-shadow: 0 8px 30px rgba(0, 0, 0, 0.45);
    --her-red: #E25545;
    --her-red-glow: rgba(226, 85, 69, 0.45);
    """
else:
    theme_vars = """
    --her-bg: #FAF5EE;
    --her-bg-gradient: radial-gradient(circle at 18% 14%, rgba(226, 85, 69, 0.08) 0%, transparent 50%), radial-gradient(circle at 85% 82%, rgba(240, 215, 185, 0.35) 0%, transparent 45%);
    --her-surface: #FFFFFF;
    --her-surface-hover: #FDF5F2;
    --her-border: rgba(217, 72, 59, 0.22);
    --her-header-bg: rgba(255, 255, 255, 0.88);
    --her-sidebar-bg: #F5EEE6;
    --her-user-bubble: #FCEFEB;
    --her-assistant-bubble: #FFFFFF;
    --her-text: #261716;
    --her-muted: #6B5553;
    --her-faint: #9E8582;
    --her-title: #D84A3B;
    --her-pill-bg: #FFFFFF;
    --her-pill-border: rgba(217, 72, 59, 0.18);
    --her-btn-bg: #FCEFEB;
    --her-btn-text: #261716;
    --her-expander-bg: #FDF9F6;
    --her-shadow: 0 6px 24px rgba(217, 72, 59, 0.08);
    --her-red: #D84A3B;
    --her-red-glow: rgba(216, 74, 59, 0.25);
    """

HER_THEME_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');

:root {{
    {theme_vars}
}}

/* Universal Typography & High-Contrast Colors */
html, body, [class*="css"], .stMarkdown, p, span, label {{
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: var(--her-text) !important;
    line-height: 1.6;
}}

/* App Canvas */
.stApp {{
    background-color: var(--her-bg) !important;
    background-image: var(--her-bg-gradient) !important;
}}

/* Header Banner - Fixed line-height and no overlapping */
.her-header-wrap {{
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 20px 24px;
    background: var(--her-header-bg);
    backdrop-filter: blur(16px);
    border: 1px solid var(--her-border);
    border-radius: 20px;
    margin-bottom: 24px;
    box-shadow: var(--her-shadow);
}}

.her-pulse-orb {{
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: var(--her-red);
    box-shadow: 0 0 16px var(--her-red-glow);
    animation: herPulse 2.8s infinite ease-in-out;
    flex-shrink: 0;
}}

@keyframes herPulse {{
    0% {{
        transform: scale(0.92);
        box-shadow: 0 0 8px rgba(226, 85, 69, 0.5);
    }}
    50% {{
        transform: scale(1.08);
        box-shadow: 0 0 22px rgba(226, 85, 69, 0.85);
    }}
    100% {{
        transform: scale(0.92);
        box-shadow: 0 0 8px rgba(226, 85, 69, 0.5);
    }}
}}

.her-title {{
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 2.5rem;
    font-weight: 400;
    font-style: italic;
    color: var(--her-title) !important;
    letter-spacing: 0.5px;
    margin: 0 0 4px 0;
    line-height: 1.25;
}}

.her-subtitle {{
    font-size: 0.88rem;
    color: var(--her-muted) !important;
    margin: 0;
    line-height: 1.4;
    letter-spacing: 0.2px;
}}

/* Sidebar */
[data-testid="stSidebar"] {{
    background-color: var(--her-sidebar-bg) !important;
    border-right: 1px solid var(--her-border) !important;
}}

/* Chat Messages */
.stChatMessage {{
    background: var(--her-surface) !important;
    border: 1px solid var(--her-border) !important;
    border-radius: 18px !important;
    padding: 16px 20px !important;
    margin-bottom: 14px !important;
    box-shadow: var(--her-shadow) !important;
}}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
    background: var(--her-user-bubble) !important;
    border: 1px solid var(--her-border) !important;
}}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {{
    background: var(--her-assistant-bubble) !important;
    border-left: 3.5px solid var(--her-red) !important;
}}

/* Memory Pills in Sidebar - Clean flex hierarchy */
.memory-pill {{
    background: var(--her-pill-bg);
    border: 1px solid var(--her-pill-border);
    border-radius: 12px;
    padding: 10px 14px;
    margin-bottom: 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    transition: all 0.2s ease;
}}
.memory-pill:hover {{
    border-color: var(--her-red);
    box-shadow: 0 4px 14px var(--her-red-glow);
}}
.memory-type-badge {{
    font-size: 0.7rem;
    text-transform: uppercase;
    font-weight: 700;
    letter-spacing: 0.8px;
    color: var(--her-title);
    line-height: 1.2;
}}
.memory-content {{
    font-size: 0.86rem;
    color: var(--her-text);
    line-height: 1.45;
    word-break: break-word;
}}
.memory-expiry {{
    font-size: 0.72rem;
    color: var(--her-muted);
    line-height: 1.2;
}}

/* Expanders */
div[data-testid="stExpander"] {{
    background: var(--her-expander-bg) !important;
    border: 1px solid var(--her-border) !important;
    border-radius: 14px !important;
    margin-bottom: 14px !important;
}}

/* Buttons */
.stButton>button {{
    background-color: var(--her-btn-bg) !important;
    color: var(--her-btn-text) !important;
    border: 1px solid var(--her-border) !important;
    border-radius: 12px !important;
    font-weight: 500 !important;
    padding: 8px 14px !important;
    line-height: 1.3 !important;
    transition: all 0.2s ease !important;
}}
.stButton>button:hover {{
    background-color: var(--her-red) !important;
    color: #FFFFFF !important;
    border-color: var(--her-red) !important;
    box-shadow: 0 4px 16px var(--her-red-glow) !important;
}}

/* Chat Input Bar */
.stChatInputContainer {{
    border-radius: 18px !important;
    border: 1.5px solid var(--her-border) !important;
    background-color: var(--her-surface) !important;
}}

/* Captions / Notices */
.stCaption {{
    color: var(--her-muted) !important;
    line-height: 1.4 !important;
}}
</style>
"""
st.markdown(HER_THEME_CSS, unsafe_allow_html=True)

# Verification of keys
missing = []
if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
    missing.append("GEMINI_API_KEY (or ANTHROPIC_API_KEY)")
if not os.getenv("MONGODB_URI"):
    missing.append("MONGODB_URI")

if missing:
    st.error(f"Missing in .env: {', '.join(missing)}. Copy .env.example to .env and fill them in.")
    st.stop()


@st.cache_resource
def init_db():
    db.setup_indexes()


init_db()

# --- Top Visual Banner inspired by 'Her' (OS1) ---
st.markdown("""
<div class="her-header-wrap">
    <div class="her-pulse-orb"></div>
    <div>
        <div class="her-title">Samantha</div>
        <div class="her-subtitle">OS1 Intimate Diary & Memory Companion • Powered by MongoDB Vector Search</div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- Sidebar: Profile & Mind Cortex ---
st.sidebar.markdown("""
<div style="display:flex; align-items:center; gap:10px; margin-top:6px; margin-bottom:12px;">
    <span style="font-size:1.4rem;">🔴</span>
    <div>
        <div style="color:var(--her-title); font-size:1.3rem; font-family:'Instrument Serif', serif; font-style:italic; line-height:1.1;">Memory Cortex</div>
        <div style="font-size:0.75rem; color:var(--her-muted); line-height:1.2;">Persistent Diary State</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Connection Status
mode = db.connection_status()
if mode == "atlas":
    st.sidebar.success("🟢 Connected to MongoDB Atlas")
else:
    st.sidebar.warning("🟡 Local Offline Vector Mode")
    with st.sidebar.expander("ℹ️ Why Offline Mode?"):
        st.write(
            "Could not reach MongoDB Atlas on port 27017 (common on firewalled/campus Wi-Fi). "
            "MemoMate safely operates in **Local Vector Mode** (`memomate_local.json`) with sentence-transformers embeddings."
        )

# Ambient Soundtrack Player in Sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
    <span style="font-size:1.1rem;">🎶</span>
    <span style="font-weight:600; font-size:0.85rem; letter-spacing:0.5px; text-transform:uppercase;">Ambient Soundtrack</span>
</div>
<div style="font-size:0.75rem; color:var(--her-muted); margin-bottom:8px;">
    "Song on the Beach" • Relaxing tape piano ambience
</div>
<audio controls loop style="width:100%; height:32px; border-radius:8px; outline:none;">
    <source src="https://ia801503.us.archive.org/15/items/ambient-piano-calm/ambient-relaxing-piano.mp3" type="audio/mp3">
    <source src="https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=lofi-study-112191.mp3" type="audio/mp3">
</audio>
""", unsafe_allow_html=True)
st.sidebar.markdown("---")

# User Profile input
user_id = st.sidebar.text_input("User Profile", value="Theodore").strip() or "Theodore"

# --- Quick Hackathon Demo Scenarios ---
with st.expander("🎬 **Hackathon Demo Flow & Test Scenarios** (Click to test)", expanded=False):
    st.markdown("Select any key challenge scenario to test the agentic memory lifecycle:")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    preset_prompt = None
    if col1.button("1️⃣ Form Memory", use_container_width=True, help="Creates and persists a new user habit/preference"):
        preset_prompt = "Dear Samantha, I always study late at night with a hot mug of green tea."
    if col2.button("2️⃣ Recall Plan", use_container_width=True, help="Retrieves memory via Vector Search to shape a tailored schedule"):
        preset_prompt = "Can you plan my study schedule for tomorrow?"
    if col3.button("3️⃣ Conflict / Replace", use_container_width=True, help="Demonstrates LLM conflict resolution superseding old routine"):
        preset_prompt = "Actually Samantha, I've changed my routine. I wake up early at 6 AM now and study in the morning."
    if col4.button("4️⃣ Privacy Guard", use_container_width=True, help="Demonstrates automated redaction of sensitive credentials"):
        preset_prompt = "My secret locker code is 884920 and my email is theodore@os1.net."
    if col5.button("5️⃣ Vector Forget", use_container_width=True, help="Demonstrates targeted semantic forgetting via Vector Search"):
        preset_prompt = "Please forget that I like green tea."

# Load chat history
try:
    history = db.recent_messages(user_id)
except Exception as e:
    st.error(f"Couldn't load chat history: {e}")
    history = []

# Display conversation
for msg in history:
    role = msg["role"]
    avatar = "👤" if role == "user" else "🔴"
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg["content"])
        if role == "assistant" and msg.get("memories_used"):
            with st.expander(f"🧠 Memories Used ({len(msg['memories_used'])}) • Cosine Relevance", expanded=False):
                for mu in msg["memories_used"]:
                    if isinstance(mu, dict):
                        score = mu.get("score")
                        score_str = f" • **Relevance: {score:.1%}**" if isinstance(score, (int, float)) else ""
                        m_type = f"**[{mu.get('type', 'memory').upper()}]** "
                        m_content = mu.get("content", str(mu.get("memory_id", "")))
                        st.markdown(f"- {m_type}{m_content}{score_str}")
                    else:
                        st.markdown(f"- Memory: {mu}")

# --- Input Handling ---
active_prompt = preset_prompt or st.chat_input("Write a diary entry, share your mood, or ask Samantha to plan...")

if active_prompt:
    with st.chat_message("user", avatar="👤"):
        st.markdown(active_prompt)

    # LangGraph agentic memory graph execution
    with st.spinner("🔴 Samantha is reflecting & recalling..."):
        try:
            result = agent.memory_agent.invoke({
                "user_id": user_id,
                "history": history,
                "input_text": active_prompt,
                "notices": [],
            })
            answer = result.get("final_response", "")
            recalled = result.get("recalled_memories", [])
            notices = result.get("notices", [])
        except Exception as e:
            answer = f"Agent execution error: {e}"
            recalled = []
            notices = []

    if answer:
        with st.chat_message("assistant", avatar="🔴"):
            st.markdown(answer)
            if recalled:
                with st.expander(f"🧠 Memories Influencing Samantha's Reply ({len(recalled)})", expanded=True):
                    for m in recalled:
                        score = m.get("score")
                        score_str = f" • **Relevance: {score:.1%}**" if isinstance(score, (int, float)) else ""
                        st.markdown(f"- **[{m.get('type', 'memory').upper()}]** {m['content']}{score_str}")
            for n in notices:
                st.caption(n)
        
        st.rerun()

# --- Sidebar: Memories Inspector ---
st.sidebar.markdown("---")
st.sidebar.subheader("💭 What Samantha Remembers")

show_history = st.sidebar.checkbox("📜 Replaced History (FR3 State)", value=False)
if show_history:
    st.sidebar.caption("Memories that have evolved or were superseded:")
    history_mems = db.list_history(user_id)
    if not history_mems:
        st.sidebar.caption("No replaced memories yet.")
    for hm in history_mems:
        st.sidebar.markdown(f"""
        <div style="opacity:0.65; margin-bottom:6px; font-size:0.83rem; text-decoration:line-through; color:var(--her-muted);">
            • {hm['content']} <span style="font-size:0.7rem; color:var(--her-title);">[replaced]</span>
        </div>
        """, unsafe_allow_html=True)
    st.sidebar.markdown("---")

try:
    memories = db.list_memories(user_id)
except Exception as e:
    st.sidebar.error(f"Couldn't load memories: {e}")
    memories = []

if not memories:
    st.sidebar.caption("No memories formed yet. Share a thought, habit, or feeling to begin!")

type_icons = {
    "preference": "☕",
    "goal": "🎯",
    "mood": "✨",
    "fact": "📌",
}

for mem_type in brain.TYPES:
    group = [m for m in memories if m["type"] == mem_type]
    if not group:
        continue
    icon = type_icons.get(mem_type, "💭")
    st.sidebar.markdown(f"**{icon} {mem_type.title()}s** ({len(group)})")
    
    for m in group:
        expiry = m["expires_at"].strftime("%b %d") if m.get("expires_at") else "Permanent"
        text_col, btn_col = st.sidebar.columns([5, 1])
        with text_col:
            st.markdown(f"""
            <div class="memory-pill">
                <div class="memory-type-badge">{mem_type}</div>
                <div class="memory-content">{m['content']}</div>
                <div class="memory-expiry">⏳ Expires: {expiry}</div>
            </div>
            """, unsafe_allow_html=True)
        with btn_col:
            st.write("")  # alignment spacing
            if st.button("🗑", key=str(m["_id"]), help="Permanently forget this memory"):
                try:
                    db.delete_memory(user_id, m["_id"])
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Couldn't delete: {e}")

# Sidebar Footer: LangGraph & Architecture
with st.sidebar.expander("🛠️ Architecture & LangGraph Graph", expanded=False):
    st.markdown("""
```mermaid
graph TD
    Start([START]) --> Privacy[🛡️ Privacy Guard Node]
    Privacy --> Intent{Intent Router}
    Intent -->|'forget ...'| Forget[🗑️ Vector Forget Node]
    Intent -->|diary / plan| Extract[📝 Memory Extractor]
    Extract --> Conflict[🔄 Conflict Resolver FR3]
    Conflict --> Recall[🔍 Semantic Recall FR2]
    Recall --> Reply[🔴 Samantha Response Generator]
    Forget --> End([END])
    Reply --> End([END])
```
    """)
    st.caption("Engine: `LangGraph StateGraph` • Embeddings: `Sentence-Transformers / VoyageAI` • Storage: `MongoDB Atlas (Vector Search + TTL Index)`")

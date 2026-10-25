"""Samantha (MemoMate) - An Intimate Diary & Memory Companion inspired by the film 'Her'.
Built for the MongoDB Hackathon (Agentic Memory Track).
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
    st.session_state.theme_mode = "🌙 Midnight Coral"

# Sidebar: Atmosphere Selector
st.sidebar.markdown("""
<div style="font-weight:600; font-size:0.82rem; letter-spacing:0.8px; text-transform:uppercase; margin-bottom:6px;">
    Atmosphere
</div>
""", unsafe_allow_html=True)

theme_choice = st.sidebar.radio(
    "Select Atmosphere",
    ["🌙 Midnight Coral", "☀️ Clean Daylight"],
    index=0 if "Midnight" in st.session_state.theme_mode else 1,
    label_visibility="collapsed",
    horizontal=True,
)
st.session_state.theme_mode = theme_choice
is_dark = "Midnight" in theme_choice

# --- Design Tokens (Dark & Light) ---
if is_dark:
    theme_vars = """
    --her-bg: #0D1117;
    --her-bg-gradient: radial-gradient(circle at 12% 12%, rgba(255, 90, 67, 0.09) 0%, transparent 45%), radial-gradient(circle at 88% 85%, rgba(224, 169, 109, 0.05) 0%, transparent 40%);
    --her-surface: #161B22;
    --her-surface-hover: #1F242C;
    --her-border: rgba(255, 90, 67, 0.22);
    --her-header-bg: rgba(22, 27, 34, 0.94);
    --her-sidebar-bg: #111419;
    --her-user-bubble: #1F2630;
    --her-assistant-bubble: #161B22;
    --her-text: #F0F6FC;
    --her-text-secondary: #C9D1D9;
    --her-muted: #8B949E;
    --her-title: #FF6B57;
    --her-card-bg: #161B22;
    --her-card-border: rgba(255, 90, 67, 0.20);
    --her-btn-bg: #1F2630;
    --her-btn-text: #F0F6FC;
    --her-expander-bg: #161B22;
    --her-input-bg: #161B22;
    --her-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
    --her-coral: #FF5A43;
    --her-coral-glow: rgba(255, 90, 67, 0.45);
    """
else:
    theme_vars = """
    --her-bg: #F5F7FA;
    --her-bg-gradient: radial-gradient(circle at 12% 12%, rgba(224, 72, 54, 0.05) 0%, transparent 50%), radial-gradient(circle at 88% 85%, rgba(240, 220, 200, 0.3) 0%, transparent 45%);
    --her-surface: #FFFFFF;
    --her-surface-hover: #F8FAFD;
    --her-border: rgba(0, 0, 0, 0.10);
    --her-header-bg: #FFFFFF;
    --her-sidebar-bg: #FFFFFF;
    --her-user-bubble: #EFF3F8;
    --her-assistant-bubble: #FFFFFF;
    --her-text: #1E2329;
    --her-text-secondary: #3B424C;
    --her-muted: #5E6773;
    --her-title: #E04836;
    --her-card-bg: #FFFFFF;
    --her-card-border: rgba(0, 0, 0, 0.10);
    --her-btn-bg: #FFFFFF;
    --her-btn-text: #1E2329;
    --her-expander-bg: #FFFFFF;
    --her-input-bg: #FFFFFF;
    --her-shadow: 0 2px 14px rgba(0, 0, 0, 0.06);
    --her-coral: #E04836;
    --her-coral-glow: rgba(224, 72, 54, 0.25);
    """

HER_THEME_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Playfair+Display:ital,wght@0,600;1,500;1,600&display=swap');

:root {{
    {theme_vars}
}}

/* Typography: Set clean sans-serif on text elements ONLY, NEVER on icons */
body, p, h1, h2, h3, h4, .stMarkdown p, .stChatMessage p, label, input, textarea {{
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--her-text) !important;
}}

/* PRESERVE STREAMLIT ICONS (Fixes literal 'arrow_down' and 'arrow_right' text) */
[data-testid*="Icon"], [data-testid*="icon"], [class*="material-symbols"], [class*="material-icons"], .material-icons, summary svg, summary span:has(svg) {{
    font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
}}

/* App Canvas */
.stApp {{
    background-color: var(--her-bg) !important;
    background-image: var(--her-bg-gradient) !important;
}}

/* Header Banner */
.her-header-wrap {{
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 18px 24px;
    background: var(--her-header-bg);
    border: 1px solid var(--her-border);
    border-radius: 16px;
    margin-bottom: 22px;
    box-shadow: var(--her-shadow);
}}

.her-pulse-orb {{
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--her-coral);
    box-shadow: 0 0 16px var(--her-coral-glow);
    animation: herPulse 2.8s infinite ease-in-out;
    flex-shrink: 0;
}}

@keyframes herPulse {{
    0% {{
        transform: scale(0.92);
        box-shadow: 0 0 8px rgba(255, 90, 67, 0.45);
    }}
    50% {{
        transform: scale(1.08);
        box-shadow: 0 0 20px rgba(255, 90, 67, 0.85);
    }}
    100% {{
        transform: scale(0.92);
        box-shadow: 0 0 8px rgba(255, 90, 67, 0.45);
    }}
}}

.her-header-content {{
    display: flex;
    flex-direction: column;
    gap: 2px;
}}

.her-title {{
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 2.1rem;
    font-weight: 600;
    font-style: italic;
    color: var(--her-title) !important;
    letter-spacing: -0.3px;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.2 !important;
}}

.her-subtitle {{
    font-size: 0.88rem;
    color: var(--her-muted) !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.4 !important;
}}

/* Sidebar */
[data-testid="stSidebar"] {{
    background-color: var(--her-sidebar-bg) !important;
    border-right: 1px solid var(--her-border) !important;
}}

[data-testid="stSidebar"] label, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span:not([data-testid*="icon"]) {{
    color: var(--her-text) !important;
}}

/* Chat Messages */
.stChatMessage {{
    background: var(--her-surface) !important;
    border: 1px solid var(--her-border) !important;
    border-radius: 16px !important;
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
    border-left: 3.5px solid var(--her-coral) !important;
}}

/* Memory Cards in Sidebar */
.memory-card {{
    background: var(--her-card-bg);
    border: 1px solid var(--her-card-border);
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    box-shadow: var(--her-shadow);
    transition: all 0.2s ease;
}}
.memory-card:hover {{
    border-color: var(--her-coral);
    box-shadow: 0 4px 14px var(--her-coral-glow);
}}
.memory-card-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
}}
.memory-type-tag {{
    font-size: 0.72rem;
    text-transform: uppercase;
    font-weight: 700;
    letter-spacing: 0.8px;
    color: var(--her-title);
    line-height: 1.2 !important;
}}
.memory-expiry-tag {{
    font-size: 0.70rem;
    color: var(--her-muted);
    line-height: 1.2 !important;
}}
.memory-card-body {{
    font-size: 0.87rem;
    color: var(--her-text-secondary);
    line-height: 1.45 !important;
    word-break: break-word;
}}

/* Expanders */
div[data-testid="stExpander"] {{
    background: var(--her-expander-bg) !important;
    border: 1px solid var(--her-border) !important;
    border-radius: 12px !important;
    margin-bottom: 14px !important;
    box-shadow: var(--her-shadow) !important;
}}

div[data-testid="stExpander"] summary, div[data-testid="stExpander"] summary span:not([data-testid*="icon"]) {{
    color: var(--her-text) !important;
    font-weight: 500 !important;
}}

/* Buttons */
.stButton>button {{
    background-color: var(--her-btn-bg) !important;
    color: var(--her-btn-text) !important;
    border: 1px solid var(--her-border) !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    padding: 8px 14px !important;
    line-height: 1.3 !important;
    box-shadow: var(--her-shadow) !important;
    transition: all 0.2s ease !important;
}}
.stButton>button:hover {{
    background-color: var(--her-coral) !important;
    color: #FFFFFF !important;
    border-color: var(--her-coral) !important;
}}

/* Chat Input Bar */
.stChatInputContainer {{
    border-radius: 14px !important;
    border: 1.5px solid var(--her-border) !important;
    background-color: var(--her-surface) !important;
}}

.stChatInput textarea {{
    color: var(--her-text) !important;
}}

/* Captions / Notices */
.stCaption, [data-testid="stSidebar"] .stCaption {{
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
    <div class="her-header-content">
        <h1 class="her-title">Samantha</h1>
        <p class="her-subtitle">OS1 Intimate Diary & Memory Companion • Powered by MongoDB Vector Search</p>
    </div>
</div>
""", unsafe_allow_html=True)

# Connection Status - Strictly Online
st.sidebar.success("🟢 Connected to MongoDB Atlas (Online Cloud Mode)")

# Ambient Soundtrack Player in Sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style="font-weight:600; font-size:0.80rem; letter-spacing:0.8px; text-transform:uppercase; margin-bottom:4px;">
    Ambient Soundtrack
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
    
    preset_prompt = None
    row1_c1, row1_c2, row1_c3 = st.columns(3)
    with row1_c1:
        if st.button("✨ 1. Form Memory", use_container_width=True, help="Creates and persists a new user habit/preference"):
            preset_prompt = "Dear Samantha, I always study late at night with a hot mug of green tea."
    with row1_c2:
        if st.button("🔍 2. Recall & Plan", use_container_width=True, help="Retrieves memory via Vector Search to shape a tailored schedule"):
            preset_prompt = "Can you plan my study schedule for tomorrow?"
    with row1_c3:
        if st.button("🔄 3. Conflict / Replace", use_container_width=True, help="Demonstrates LLM conflict resolution superseding old routine"):
            preset_prompt = "Actually Samantha, I've changed my routine. I wake up early at 6 AM now and study in the morning."

    row2_c1, row2_c2 = st.columns(2)
    with row2_c1:
        if st.button("🛡️ 4. Privacy Guard (Redaction)", use_container_width=True, help="Demonstrates automated redaction of sensitive credentials"):
            preset_prompt = "My secret locker code is 884920 and my email is theodore@os1.net."
    with row2_c2:
        if st.button("🗑️ 5. Vector Forget (Semantic Delete)", use_container_width=True, help="Demonstrates targeted semantic forgetting via Vector Search"):
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
        st.sidebar.markdown(f"""
        <div class="memory-card">
            <div class="memory-card-header">
                <span class="memory-type-tag">{mem_type}</span>
                <span class="memory-expiry-tag">⏳ {expiry}</span>
            </div>
            <div class="memory-card-body">{m['content']}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.sidebar.button("🗑️ Forget this memory", key=f"del_{m['_id']}", use_container_width=True):
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

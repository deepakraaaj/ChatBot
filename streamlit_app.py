import streamlit as st
import requests
import json
import uuid

# --- Configuration ---
BASE_URL = "http://localhost:8000"
USER_ID = 1  # Hardcoded development user
AUTH_HEADER = {"Authorization": f"Bearer dev-token-bypass:{USER_ID}"}

st.set_page_config(page_title="AI Facility Ops", page_icon="🏢", layout="wide")

# --- Styles ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Chat Message Bubbles */
    .stChatMessage {
        background-color: transparent !important;
    }
    
    div[data-testid="chatAvatarIcon-user"] {
        background-color: #465fff !important;
    }
    
    /* Buttons */
    div.stButton > button {
        background-color: #465fff;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s;
    }
    div.stButton > button:hover {
        background-color: #3b4ecc;
        color: white;
        box-shadow: 0 4px 12px rgba(70, 95, 255, 0.2);
    }

    /* Input */
    .stTextInput input {
        border-radius: 8px;
        border: 1px solid #e0e0e0;
    }
</style>
""", unsafe_allow_html=True)

# --- State Management ---
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "processing" not in st.session_state:
    st.session_state.processing = False

# --- Backend API ---
def start_session():
    """Initializes a new session with the backend."""
    try:
        resp = requests.post(f"{BASE_URL}/session/start", headers=AUTH_HEADER)
        if resp.status_code == 200:
            data = resp.json()
            st.session_state.session_id = data["session_id"]
            # Optional system welcome
            # st.session_state.messages.append({"role": "assistant", "content": "Session started. How can I help?"})
        else:
            st.error(f"Failed to start session: {resp.text}")
    except Exception as e:
        st.error(f"Backend connection failed: {e}")

def stream_chat(message):
    """Generates streaming response from backend NDJSON."""
    url = f"{BASE_URL}/chat"
    payload = {
        "session_id": st.session_state.session_id,
        "message": message,
        "user_id": USER_ID
    }
    
    try:
        with requests.post(url, headers=AUTH_HEADER, json=payload, stream=True) as response:
            if response.status_code != 200:
                yield f"Error: {response.status_code} - {response.text}"
                return

            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        event_type = data.get("type")
                        
                        if event_type == "token":
                            yield data.get("content", "")
                        elif event_type == "error":
                            yield f"\n[Error: {data.get('message')}]"
                        elif event_type == "result":
                            # Handle metadata/result (e.g. log workflow activation)
                            pass
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        yield f"Connection error: {e}"

# --- Logic ---
# Auto-start session on load
if not st.session_state.session_id:
    start_session()

# --- UI Render ---
st.title("🏢 Facility Ops AI")

# Sidebar for debug/info
with st.sidebar:
    st.subheader("Session Info")
    st.code(st.session_state.session_id or "Not Connected", language="text")
    
    if st.button("Reset Session"):
        st.session_state.session_id = None
        st.session_state.messages = []
        st.rerun()

# Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input
if prompt := st.chat_input("Ask about safety, workflows, or data...", disabled=st.session_state.session_id is None):
    # Optimistic UI update
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Streaming Response
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_text = ""
        
        for chunk in stream_chat(prompt):
            full_text += chunk
            response_placeholder.markdown(full_text + "▌")
        
        response_placeholder.markdown(full_text)
    
    st.session_state.messages.append({"role": "assistant", "content": full_text})

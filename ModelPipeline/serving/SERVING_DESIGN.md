## Frontend for FinSights Model Pipeline

This document outlines the design for the serving layer of the FinSights Model Pipeline, focusing on the frontend and backend architecture using Streamlit, Pydantic and FastAPI.

### Clean separation:
- T1: FastAPI backend with uvicorn (persistent event loop)
- T2: Streamlit frontend (separate process, makes HTTP requests)
- This is the clean separation architecture - not direct Python imports in Streamlit.

```
SCRIPT (to):
Start → Run → Finish → Exit

FRONTEND - BACKEND (concept):
Start → Initialize → Listen... → Handle Request → Listen... → Handle Request → Listen... [Forever]
                                    ↑                              ↑
                                    └──────────────────────────────┘
                                         Event Loop ( Magic :D )
```


### event_loop / uvicorn event loop:
```
Server "alive" (listening)
┌─────────────────────────────────────────┐
│ PROCESS: uvicorn (PID 12345)            │
│ STATE: Running (infinite loop)          │
│ PORT: 8000 (bound to TCP socket)        │
│ MEMORY: Contains all ML dependencies    │
│         (boto3, polars, code)           │
└─────────────────────────────────────────┘
     ↑
     │ Waiting for HTTP requests...
     │ (blocks here until request arrives)
```


### Overview:
```
📦serving
 ┣ 📂.streamlit
 ┃ ┗ 📜config.toml
 ┣ 📂backend
 ┃ ┣ 📜api_service.py
 ┃ ┣ 📜config.py
 ┃ ┣ 📜models.py
 ┃ ┣ 📜requirements.txt
 ┃ ┗ 📜__init__.py
 ┣ 📂frontend
 ┃ ┣ 📜api_client.py
 ┃ ┣ 📜chat.py
 ┃ ┣ 📜metrics.py
 ┃ ┣ 📜requirements.txt
 ┃ ┣ 📜state.py
 ┃ ┗ 📜__init__.py
 ┣ 📜.env.example.txt
 ┣ 📜FRONTEND_DESIGN.md
 ┣ 📜run_dev.sh
 ┗ 📜Serving_SETUP.md
```

Edit `.env` to customize:
- `BACKEND_PORT`: Backend API port (default: 8000)
- `FRONTEND_PORT`: Frontend UI port (default: 8501)
- `LOG_LEVEL`: Logging verbosity
- `ENABLE_CACHE`: Query result caching




### Potential Process Flow:
```
1. USER types in Streamlit: "What was Apple's revenue?"
                ↓
2. STREAMLIT makes HTTP call:
   requests.post("http://localhost:8000/query", 
                 json={"question": "What was Apple's revenue?"})
                ↓
3. FASTAPI receives at @app.post("/query"):
   - Validates input with Pydantic, Extracts question from request
                ↓
4. CONTROLLER calls backend:
   result = answer_query(query=request.question, ...)  # ← CODE
                ↓
5. ORCHESTRATOR runs ():
                ↓
6. CONTROLLER packages response:
   return QueryResponse(answer=result['answer'], ...)
                ↓
7. STREAMLIT receives and displays:
   st.write(response.json()['answer'])
```

1. Use Native-component container Queries. Not in-line python or css forced injections; unmaintainable.
2. Session State / Streamlit has built-in theming since v1.10.
3. Streamlit's native components just handle 99%
4. Native theming via TOML, Container components for layout. 



#### Pattern - clean ideas:
```
# app.py - Clean routing
if st.session_state.page == "Home":
    render_home()
elif st.session_state.page == "Chatbot":
    render_chatbot()
```



### Step-by-Step: User Asks "What was Apple's revenue?"**
┌─────────────────────────────────────────────────────────────┐
│ 1. USER TYPES IN BROWSER                                    │
│    - Browser shows Streamlit UI at localhost:8501           │
│    - User types: "What was Apple's 2023 revenue?"           │
│    - Clicks submit                                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. BROWSER → STREAMLIT (HTTP)                               │
│    POST http://localhost:8501/_stcore/stream                │
│    Body: {user input, session state, etc.}                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. STREAMLIT PROCESS (PID 12346)                            │
│    - Receives HTTP from browser                             │
│    - Executes Python code:                                  │
│                                                             │
│    prompt = st.chat_input(...)  # Gets user text            │
│    result = requests.post(      # ← Makes HTTP call         │
│        "http://localhost:8000/query",                       │
│        json={"question": prompt}                            │
│    )                                                        │
└─────────────────────────────────────────────────────────────┘
                          ↓ HTTP over loopback (localhost)
┌─────────────────────────────────────────────────────────────┐
│ 4. UVICORN PROCESS (PID 12345)                              │
│    - Event loop wakes up (request arrived!)                 │
│    - Parses HTTP request                                    │
│    - Calls FastAPI route:                                   │
│                                                             │
│    @app.post("/query")                                      │
│    async def query_endpoint(request):                       │
│        result = answer_query(...)  # ← IN-MEMORY CALL       │
└─────────────────────────────────────────────────────────────┘
                          ↓ Function call (same process)
┌─────────────────────────────────────────────────────────────┐
│ 5. ORCHESTRATOR (SAME PROCESS - PID 12345)                  │  
│    - answer_query() executes                                │
│    - Loads RAG components (already in memory)               │
│    - Calls AWS Bedrock (network request)                    │
│    - Processes response                                     │
│    - Returns Python dict                                    │
└─────────────────────────────────────────────────────────────┘
                          ↓ Return value
┌─────────────────────────────────────────────────────────────┐
│ 6. FASTAPI CONVERTS TO HTTP                                 │
│    - Takes Python dict                                      │
│    - Serializes to JSON                                     │
│    - Wraps in HTTP response                                 │
│    - Sends back to Streamlit                                │
└─────────────────────────────────────────────────────────────┘
                          ↓ HTTP response
┌─────────────────────────────────────────────────────────────┐
│ 7. STREAMLIT RECEIVES RESPONSE                              │
│    - response.json() parses it                              │
│    - Updates UI with answer                                 │
│    - Sends new HTML to browser                              │
└─────────────────────────────────────────────────────────────┘
                          ↓ HTTP response
┌─────────────────────────────────────────────────────────────┐
│ 8. BROWSER DISPLAYS RESULT                                  │
│    - User sees answer on screen                             │
└─────────────────────────────────────────────────────────────┘


---

### Microservices potential architecture:
- may not do this but looking into this research. 
```
┌──────────────────┐      HTTP       ┌─────────────────────┐
│  Streamlit       │ ───────────────→│  FastAPI            │
│  (venv_serving)  │                 │  (venv_serving)     │
└──────────────────┘                 │                     │
                                     │  Lightweight proxy  │
                                     └─────────────────────┘
                                              │
                                              │ HTTP/RPC
                                              ↓
                                     ┌─────────────────────┐
                                     │  ML Service         │
                                     │  (venv_ml_rag)      │
                                     │                     │
                                     │  Runs orchestrator  │
                                     │  in separate process│
                                     └─────────────────────┘
```

### If we plan on using GITHUB actions:
```
Code → GitHub (storage) → GitHub Actions (CI/CD) → Streamlit Cloud/Railway/Alternative (hosting)
                                        ↓
                                 Run tests, checks
```
- Streamlit Cloud for frontend, Modal.com for serverless backend -- expensive. 
- A little out of scope now.
- Streamlit Cloud - AWS and data files not so possible? (investigating)

---

## Frontend Design:

```
Dependency Tree:
    api_client.py          # NO dependencies (pure HTTP client)
         ↓
    state.py               # Uses api_client for health checks ()
         ↓
    chat.py                # Needs BOTH api_client + state
         ↓
    metrics.py             # Needs state (to access metadata)
```

### Design Constraints
- NO CSS Hacks → Use native Streamlit components only
- NO Custom JavaScript → Pure Python/Streamlit
- Stateless Queries → Each query independent, no conversation context
- Error Tolerance → Graceful degradation if backend unavailable
- Performance → Use st.cache_resource for backend client initialization


### Feature 1: Query Submission Flow
  1. User types question in st.chat_input()
  2. Validate input (min 10 chars)
  3. Display user message immediately
  4. Show loading spinner: "Processing query..."
  5. Call api_client.send_query()
  6. Handle response:
     - Success → Display answer + metadata
     - Error → Display error message with details
  7. Update session state with new message
  8. Scroll to bottom of chat

### Feature 2: Backend Health Check
   ON APP STARTUP:
   1. Call api_client.check_health()
   2. If healthy → Show green indicator
   3. If unhealthy → Show warning banner
   4. Store status in st.session_state.backend_healthy

### Feature 3: Metadata Display
   FOR EACH ASSISTANT MESSAGE:
   1. Show answer text prominently
   2. Add expandable section below answer:
      - LLM Info: Model, tokens, cost
      - Context Info: KPI/RAG flags, length
      - Processing Time
   3. Update cumulative cost tracker

### Feature 4: Error Handling
   ERROR TYPES TO HANDLE:
   - Connection Error → "Backend not responding. Is it running?"
   - Timeout → "Query took too long (>120s)"
   - Validation Error → "Question too short (min 10 chars)"
   - Pipeline Error → Display error.stage and error.error

### Feature 5: Chat History
   VISUAL ONLY (NO SEMANTIC MEMORY):
   - Display all past Q&A pairs on page load
   - Each query is independent (no context passed)
   - Optional: "Clear History" button in sidebar



#### RCA1 quick info:
- Root Cause: Two places are opening the browser:
- Streamlit's built-in auto-open (--server.headless false)
- backup script command (Start-Process "http://localhost:8501")
#### RCA2 and so on: No bugs, cosmetic warnings.
- SyntaxWarnings - Streamlit library has docstrings with \. that should be \\. or raw strings
- Config option 'server.enableCORS=false' is not compatible with 'server.enableXsrfProtection=true'. As a result, 'server.enableCORS' is being overridden to 'true'. Just informational.
- Python 3.12 made regex escape sequences stricter. Streamlit team needs to update their docstrings.

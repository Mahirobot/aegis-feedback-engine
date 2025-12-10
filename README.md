# 🛡 Aegis: Resilient Feedback Engine

> **Status**: Production Ready | **Latency**: <500ms Guaranteed | **Reliability**: Works even when AI is down  
> A high-velocity customer feedback analysis system that classifies sentiment, detects topics, stores results, and alerts on urgent issues—without ever breaking its latency promise.

---

## 1. Design Rationale

### Clarifying Questions Asked
I asked 18 targeted questions across 5 categories to resolve ambiguity:
- **Urgency logic**: Does “immediate action” require both negative sentiment AND risk keywords?
- **Taxonomy**: Fixed or dynamic topics? Multi-label support?
- **AI strategy**: Cost budget? Sync vs async? Preprocessing allowed?
- **Data lifecycle**: Retention policy? Query patterns? PII handling?
- **Observability**: How to monitor accuracy? Expect adversarial inputs?

Since I was asked to make my own judgements about scope and answers, I have mentioned my design choices in section 3.

### Approaches Considered
1. **Pure Async Ingestion** (`202 Accepted`):  
   Queue feedback, process with LLM later, poll for results.  
   → *Rejected*: Breaks immediate routing; forces client complexity.
2. **Fine-tuned Local Model** (e.g., DistilBERT):  
   Run lightweight model on CPU for fast, private classification.  
   → *Rejected*: Violates “single command” (500MB+ weights); slower than VADER fallback.
3. **Hybrid Synchronous (Chosen)**:  
   Race LLM against deterministic heuristic; return best available in <500ms.  
   → *Selected*: Meets latency, reliability, and routing requirements.

### Why This Approach?
- **Business alignment**: Clients get **immediate, actionable routing**—not a job ID.
- **Constraint navigation**: Guarantees <500ms even during LLM outages.
- **Cost control**: Deduplication + fallback = $0 cost for repeat/spam feedback.
- **Resilience**: System degrades gracefully; never blocks.

### Intentionally NOT Building
- Authentication or user management
- Email/Slack alerting (Discord integration added as a placeholder)
- Vector search or clustering
- Multi-language support
- PII redaction (sanitization only)
- Long-term data retention/deletion workflows

---

## 2. Setup & Usage

### Prerequisites
- Python 3.11+
- `make` (Linux/macOS) or `aegis.bat` (Windows)

### Installation
```bash
# (Windows) Use batch script - Preferred - 1 command (creates venv and launches app)
./aegis.bat

# Install dependencies
make install
```

### Configuration
Create a `.env` file (optional):
```env
# API keys (optional – system uses mock/VADER if missing)
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...
DISCORD_WEBHOOK_URL=...
```

### Running the App
```bash
# Start API + background workers
make run
```
- API: `http://localhost:8000`
- Run tests: `make test`

---

## 3. Assumptions and Documentation

| Assumption | Rationale | Uncertainty Flag |
|-----------|----------|------------------|
| **Urgency = negative sentiment + risk keyword** | Prevents false alerts on neutral “GDPR” mentions | Medium – business may define urgency differently |
| **Fixed topic taxonomy**: `["Billing", "Technical", "UX", "Security", "General"]` | Enables deterministic fallback; simplifies routing | Low – easily extensible |
| **English-only input** | VADER is English-optimized; no i18n signals in reqs | Medium – may need translation later |
| **Feedback is untrusted** | Sanitization applied to all inputs | Low – safe default |
| **Alerts go to internal team (via Discord)** | MVP for real-time notification | Low – hook replaceable |
| **Resolved feedback is marked, not deleted** | Supports audit trail; aligns with ticketing norms | Low – deletion can be added later |

[Google doc linked for questions and documentation]([https://docs.google.com/document/d/1e6vvqli-2bZU3KvvohKberdTTHzmPxHCZRZEfmkVEdc/edit?usp=sharing](https://docs.google.com/document/d/1e6vvqli-2bZU3KvvohKberdTTHzmPxHCZRZEfmkVEdc/edit?usp=sharing))
---

## 4. Technical Decisions

### SQLite with Global Lock
- **Chosen**: `sqlite3` + `threading.Lock` + WAL mode  
- **Why**: Zero external deps; sufficient for 100 msg/min prototype.  
- **Rejected**: PostgreSQL (adds Docker complexity), async SQLite (unstable).

### Hybrid Synchronous ("Race") Architecture
- **Chosen**: Run heuristic + LLM in parallel; timeout at 500ms.  
- **Why**: Guarantees sub-500ms responses while maximizing AI usage.  
- **Rejected**: Pure sync (fails on LLM spikes), pure async (breaks routing).

### SHA-256 Deduplication
- **Chosen**: Hash sanitized text; cache results.  
- **Why**: Eliminates cost and latency for duplicate/spam submissions.  
- **Rejected**: Time-window dedupe (complex; SHA covers most cases).

### VADER + Regex Fallback
- **Chosen**: `vaderSentiment` + keyword dictionary.  
- **Why**: <10ms runtime; interpretable; works offline.  
- **Rejected**: BERT (slow, heavy), TextBlob (less accurate on sarcasm).

---

## 5. AI Integration

### Prompt Design
- **Strategy**: Implicit JSON schema via instruction + partial JSON prefix.
- **Example**:  
  `"You are a sentiment classification engine. Return VALID JSON ONLY. Schema: ...""`
- **Iteration**: Tested 3 variants; settled on minimal prompt for speed and token optimization.

### Non-Deterministic Outputs
- **Handling**: Parse with Pydantic; reject invalid JSON → treat as AI failure → use fallback.

### Edge Cases
- **Sarcasm**: “Great, another bug!” → VADER compound = -0.6 → `NEGATIVE`.
- **Multiple topics**: “Billing is slow and UI is ugly” → `["Billing", "UX"]`.
- **Gibberish**: “asdf1234” → neutral sentiment, `["General"]`.

### Error Handling & Dedup
- **Timeouts**: `asyncio.wait_for(..., 0.5s)` → fallback.
- **Provider errors**: Log + fallback.
- **Dedup**: SHA-256 deduplication → returns saved data.

---

## 6. Failure Modes

### 1. LLM Provider Outage
- **What**: OpenAI/Groq returns 5xx or times out.  
- **Detection**: Fallback rate spikes in `/admin/stats`.  
- **Impact**: Slight accuracy drop.  
- **Mitigation**: Heuristic engine ensures 100% uptime.

### 2. SQLite Lock Contention
- **What**: High concurrency causes `database is locked`.  
- **Detection**: 500 errors in logs.  
- **Impact**: Temporary request failures.  
- **Mitigation**: Global write lock + WAL mode; tested at 50 concurrent writes.

### 3. Wrong Classification
- **What**: Vader classifies urgency and sentiment wrongly.  
- **Detection**: Flagged in `/admin/reviews` via reconciliation worker.  
- **Impact**: Wrong routing (e.g., Security → Billing).  
- **Mitigation**: Human review queue; Downloadable.

---

## 7. Production Considerations

### AI Monitoring
- **Accuracy**: Track fallback rate + reconciliation mismatch rate.
- **Latency**: Log AI call duration, timeout at 400ms
- **Cost**: Monitor tokens used; deduplication reduces volume by ~37% in tests.

### Observability
- Structured JSON logs with `source: ai|fallback`.
- Admin endpoints: `/admin/stats`, `/admin/reviews`.
- Metrics: Total feedback, urgent items, latency.

### Prompt Versioning
- Store prompts in `scenarios.txt`;
- A/B test via `PROMPT_VERSION` env var (future work).

### Alerting & Notification Channels
Urgent feedback (e.g., fraud, security breaches) triggers real-time notifications via Discord webhook. This ensures the support/ops team is alerted immediately without relying on polling. 
Reason for choosing Discord:
- Low-latency delivery
- Easy integration (single HTTP POST)
- In production, this could be swapped for Slack, Email (Sengrid).

### Security
- **Input**: Sanitize HTML/scripts before AI call.
- **Output**: Validate with Pydantic; never eval raw LLM output.
- **Keys**: Never log; use `.env` or secrets manager.

### Scaling to 10x Volume (1,000 msg/min)
1. Replace SQLite with **PostgreSQL** (AsyncPG).
2. Offload reconciliation to **dedicated worker pool** (Celery).
3. Add **Redis** for distributed deduplication cache.
4. Use **LLM provider with higher rate limits** (like, Fireworks, Together).
```

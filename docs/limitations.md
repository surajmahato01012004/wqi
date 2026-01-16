# Limitations and Caveats

**System**
- SQLite in development is not ideal for concurrent writes or container restarts; prefer Postgres in production.
- Nearest-location queries use Haversine over all rows; for large datasets, add geospatial indexing or a spatial DB.
- Authentication is client-side only (localStorage) and not secure for production; implement server-side sessions and roles for real deployments.
- Basic input validation on forms; stricter validation and rate limiting recommended for production.
- Animated background uses canvas; extremely low-end devices may prefer a static image toggle.

**WQI**
- WQI depends on user-entered values; inaccurate inputs lead to misleading scores.
- Parameter standards and weights are simplified; domain calibration may be needed for local compliance.
- Temperature effect uses absolute deviation from ideal; alternative formulations may be desired.
- Sensors page computes WQI from IoT readings and assumes ideal observed values for missing parameters (DO=14.6 mg/L, TDS=0 mg/L, Nitrate=0 mg/L). This can bias results optimistic if actual DO/TDS/Nitrate differ.

**Chatbot**
- Model: `HuggingFaceTB/SmolLM3-3B:hf-inference` (app.py:237).
- Scope:
  - General-purpose reasoning, not domain-expert water chemistry.
  - No live access to internal DB or map data; cannot query or modify location samples directly.
  - Answers are generated; factual accuracy is not guaranteed (risk of hallucinations).
- Length:
  - Request configured with `max_tokens=3000` (app.py:253); very long answers may be truncated.
- Latency:
  - Network call to Hugging Face Router; speed depends on service load and connectivity.
- Safety:
  - No content filtering beyond removing chain-of-thought. Consider moderation if exposed publicly.
- Client behavior:
  - Enforces a minimum send delay to avoid spamming backend; may frustrate rapid trial use.
  - Frontend calls relative `/chat` to avoid hardcoded external URLs.

**What It Can Answer**
- Generic questions about WQI concepts, parameters, and usage guidance.
- Explanations of app features, workflows, and basic troubleshooting.
- High-level technical answers about architecture choices (from `technical_overview.md`).

**What It Cannot Answer Reliably**
- Exact, authoritative scientific recommendations without a vetted knowledge base.
- Real-time queries into the app’s DB or sensor data (unless integrated with a secure API).
- Highly specialized regulatory or regional guidelines without curated context.

**Improvement Plan**
- Use a domain-tuned model or larger foundation model for better accuracy.
- Add a retrieval layer (RAG) over curated documentation and datasets.
- Provide guardrails: prompt templates, policy filters, and fallback responses.
- Stream responses in the UI, add retry/backoff, and better error messaging.
- Integrate knowledge of app state via internal APIs, with access controls and logging.
- Implement analytics for chatbot interactions to iteratively improve prompts and content.
 - Extend IoT ingestion to include DO, TDS, and Nitrate sensors to eliminate assumptions on the Sensors page WQI.

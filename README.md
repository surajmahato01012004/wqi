# Aqua Track: Water Quality Monitoring System

A full-stack Flask application to compute, visualize, and manage Water Quality Index (WQI) across locations, with an AI chatbot, interactive map, downloadable reports, and an animated water-themed UI.

**Key Features**
- WQI calculator with chart and status badges on `/` (templates/index.html).
- Location and sample management with CRUD on `/data` (templates/data.html).
- Interactive WQI map using Google Maps on `/map` (templates/map.html).
- Dashboard with quick links, live sensor card, and public-awareness slogan on `/dashboard` (templates/dashboard.html).
- AI chatbot page (templates/chatbot.html) with server endpoint at `/chat`.
- Sensors page showing latest ESP32 readings and computed WQI on `/sensors` (templates/sensors.html).
- Login, Signup, and User Dashboard pages with client-side auth on `/login`, `/signup`, `/user-dashboard`.
- CSV/Excel export including temperature via `/download_excel`.
- Auto-migration that adds a `temperature` column for backward compatibility.


**Project Structure**
- `app.py` — Flask app, models, routes, APIs, WQI and status logic.
- `templates/` — Jinja2 templates extending `layout.html` with Bootstrap 5.
- `static/` — Frontend assets (`script.js`, `map.js`, `chatbot.js`, CSS, water background animation).
- `static/sensors.js` — IoT latest-readings polling and WQI display.
- `data/wqi.db` — SQLite database (auto-created locally).
- `data/static_wb.json` — Static West Bengal reference data (seeded into DB).
- `requirements.txt` — Python dependencies.
- `Procfile` — Production entry (`gunicorn app:app`).

**Project Tree**

```
root
├─ app.py
├─ requirements.txt
├─ Procfile
├─ README.md
├─ data
│  ├─ wqi.db
│  └─ static_wb.json
├─ templates
│  ├─ layout.html
│  ├─ index.html
│  ├─ map.html
│  ├─ data.html
│  ├─ dashboard.html
│  ├─ sensors.html
│  ├─ login.html
│  ├─ signup.html
│  └─ user_dashboard.html
├─ static
│  ├─ script.js
│  ├─ map.js
│  ├─ sensors.js
│  ├─ chatbot.js
│  ├─ style.css
│  └─ js
│     └─ global_ripple.js
```

**Detailed Structure**
- Pages
  - `templates/layout.html` base layout, navbar, assets
  - `templates/index.html` calculator
  - `templates/map.html` WQI map
  - `templates/data.html` CRUD dashboard
  - `templates/dashboard.html` landing dashboard
  - `templates/chatbot.html` AI chatbot UI
- JavaScript
  - `static/script.js` calculator chart and status
  - `static/map.js` map and API integration
  - `static/chatbot.js` chat UI and backend calls
  - `static/js/global_ripple.js` animated background canvas
- Styles
  - `static/style.css` site stylesheet and contrast, background
- Data
  - `data/wqi.db` local SQLite file
  - `data/static_wb.json` seed JSON for reference locations

**Setup**
- Install: `pip install -r requirements.txt`
- Environment:
  - `GOOGLE_MAPS_API_KEY` for the map page.
  - `HUGGING_FACE_API_TOKEN` for the `/chat` endpoint.
  - `HF_CHAT_MODEL` optional, defaults to `HuggingFaceTB/SmolLM3-3B:hf-inference` (app.py:237).
  - `DATABASE_URL` optional (Postgres). Falls back to SQLite (app.py:22–25, 26–37).
- Run: `python app.py` → `http://127.0.0.1:5000/`
 
**Local Development**
- Create venv (optional) and install dependencies: `pip install -r requirements.txt`
- Set environment variables if needed:
  - Windows PowerShell:
    - `$env:GOOGLE_MAPS_API_KEY="<api_key>"`
    - `$env:HUGGING_FACE_API_TOKEN="<hf_token>"`
    - `$env:HF_CHAT_MODEL="HuggingFaceTB/SmolLM3-3B:hf-inference"`
- Start server: `python app.py`
- Open:
  - `http://127.0.0.1:5000/` calculator
  - `http://127.0.0.1:5000/dashboard` dashboard
  - `http://127.0.0.1:5000/map` map
  - `http://127.0.0.1:5000/data` database
  - `http://127.0.0.1:5000/chatbot.html` chatbot

**Data Model**
- `Location`: `id`, `latitude`, `longitude`, `name`, `samples` relationship.
- `WaterSample`: `id`, `location_id`, `ph`, `do`, `tds`, `turbidity`, `nitrate`, `temperature`, `wqi`, `timestamp`.
- `IoTReading`: `temperature_c`, `ph`, `turbidity_percent`, `turbidity_ntu`, `timestamp`.
- Auto-migration adds `temperature` to `water_samples` if missing.
 
**Database Details**
- Default: SQLite stored at `data/wqi.db`
- External: Provide `DATABASE_URL` (Postgres recommended in production)
- Auto-migration:
  - On startup, adds `temperature FLOAT` column to `water_samples` if not present
- Indexes:
  - `latitude`, `longitude`, `timestamp`, and `wqi` columns indexed for typical queries
- Migrations:
  - For production, adopt `Flask-Migrate` to manage schema updates

**WQI Logic**
- Core function (app.py:117–173) computes dynamic weights from standards and applies per-parameter `Qi`. Temperature uses absolute deviation from ideal (app.py:157–161).
- Status mapping (app.py:176–188):
  - 0–25 Excellent (`success`)
  - 26–50 Good (`primary`)
  - 51–75 Poor (`warning`)
  - 76–100 Very Poor (`danger`)
  - >100 Unfit (`dark`)
 - UI: calculator badge background matches status color; semi-pie chart is larger.

**UI and UX**
- `layout.html` provides navbar, global animated background, and high-contrast content container.
- Chart rendering and status badges on calculator (`static/script.js`).
- Map markers colored by WQI status (`static/map.js`).
- Chatbot cleans model outputs and enforces send delay (`static/chatbot.js`).

**APIs Summary**
- `POST /calculate` → `{ wqi, status, color }`
- `GET /api/locations` → list of locations with latest WQI + references
- `GET /api/wqi?lat&lng` → nearest location’s WQI
- `GET /api/iot` / `POST /api/iot` → latest/ingest IoT readings
- `GET /download_excel` → CSV/XLSX export of data and static references

**Deployment**
- Local SQLite for development; prefer managed Postgres in production.
- Configure environment variables on the platform (Render, etc.).
- Use `gunicorn` with `Procfile` for production.
 
**Render Deployment**
- Prerequisites:
  - Create a Render Web Service
  - Set environment variables:
    - `DATABASE_URL` (managed Postgres)
    - `GOOGLE_MAPS_API_KEY`
    - `HUGGING_FACE_API_TOKEN`
    - `HF_CHAT_MODEL` (optional)
- Build & Start:
  - Uses `requirements.txt` for install
  - Start command via `Procfile`: `gunicorn app:app`
- Notes:
  - Use Postgres to avoid ephemeral filesystem issues
  - Verify `/download_excel` in Render; large exports may need streaming

**Sensor WQI**
- The Sensors page computes WQI from latest IoT values.
- Assumes ideal observed values for unspecified parameters: `DO=14.6 mg/L`, `TDS=0 mg/L`, `Nitrate=0 mg/L`.
- Uses the same weights and status mapping as the calculator and data pages.

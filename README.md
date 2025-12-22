# AquaTrack WQI

A Flask application that computes and visualizes Water Quality Index (WQI). It supports manual WQI calculation, a location-based WQI system backed by SQLite via SQLAlchemy, a Google Map UI showing the WQI at stored locations, and a database dashboard with CRUD for locations and samples.

## Features
- Manual WQI calculator page (`/`) using existing logic
- Location-based WQI with `Location` and `WaterSample` tables (SQLite + SQLAlchemy)
- API for nearest WQI and listing all locations
- Google Maps page (`/map`) showing colored markers and click-to-query nearest WQI
- Database page (`/data`) for CRUD operations on locations and samples
- Demo seed endpoint for Kolkata water bodies

## Project Structure
- `app.py`: Flask app, SQLAlchemy models, routes, APIs, WQI logic
- `templates/`:
  - `index.html`: Calculator page
  - `map.html`: Google Map page
  - `data.html`: Database dashboard with CRUD
  - `dashboard.html`: Landing dashboard with links
- `static/`:
  - `script.js`: Calculator chart rendering
  - `map.js`: Map initialization, markers, API calls
- `data/wqi.db`: SQLite database file (auto-created)
- `requirements.txt`: Dependencies
- `Procfile`: Deployment entry for Gunicorn

## Setup
- Install dependencies:
  - `pip install -r requirements.txt`
- Set environment for Google Maps:
  - `GOOGLE_MAPS_API_KEY=<your_api_key>`
- Start the app:
  - `python app.py`
- Open:
  - Calculator: `http://127.0.0.1:5000/`
  - Dashboard: `http://127.0.0.1:5000/dashboard`
  - Map: `http://127.0.0.1:5000/map`
  - Database: `http://127.0.0.1:5000/data`

## Database Design
- `Location`:
  - `id`, `latitude`, `longitude`, `name`
  - Relationship: `samples` to `WaterSample`
- `WaterSample`:
  - `id`, `location_id`, `ph`, `do`, `tds`, `turbidity`, `nitrate`, `wqi`, `timestamp`
- Tables are created automatically on app start. The DB file is stored in `data/wqi.db` under the project directory for local development.

## WQI Logic
- The calculator uses parameter configs for `ph`, `tds`, `do`, `turbidity`, `nitrate`, computing a weighted index.
- Status categories:
  - `0–25` Excellent (`success`)
  - `26–50` Good (`primary`)
  - `51–75` Poor (`warning`)
  - `76–100` Very Poor (`danger`)
  - `>100` Unfit (`dark`)
- The same category colors are used in the map markers and badges across the app to keep the UX consistent.

## WQI Formula
- Per-parameter quality index \(Q_i\) for a parameter with observed value \(V_o\), ideal value \(V_i\), and standard \(S\):
  \[
  Q_i = 100 \times \frac{V_o - V_i}{S - V_i}
  \]
- Special handling for Dissolved Oxygen (DO):
  - If \(V_o \ge S\):
    \[
    Q_i = 100 \times \left(1 - \frac{V_o}{V_i}\right)
    \]
  - Else:
    \[
    Q_i = 100 + 100 \times \frac{S - V_o}{S}
    \]
- Clamp \(Q_i\) to be non-negative: \(Q_i = \max(0, Q_i)\)
- Weighted WQI:
  \[
  \mathrm{WQI} = \frac{\sum_i W_i \cdot Q_i}{\sum_i W_i}
  \]
- Parameter configuration (standards \(S\), ideals \(V_i\), weights \(W_i\)):
  - pH: \(S=8.5,\ V_i=7.0,\ W=4\)
  - TDS: \(S=500,\ V_i=0,\ W=1\)
  - DO: \(S=5.0,\ V_i=14.6,\ W=5\)
  - Turbidity: \(S=5.0,\ V_i=0,\ W=3\)
  - Nitrate: \(S=45,\ V_i=0,\ W=2\)

## APIs
- `GET /api/wqi?lat=<latitude>&lng=<longitude>`:
  - Finds the nearest stored location using Haversine distance
  - Retrieves the latest sample
  - Computes WQI if missing
  - Returns JSON: `latitude`, `longitude`, `wqi`, `status`, `color`
- `GET /api/locations`:
  - Lists all locations with their latest WQI (computed if missing)
  - Returns JSON items: `name`, `latitude`, `longitude`, `wqi`, `status`, `color`
- CRUD:
  - `POST /data/location` create location
  - `POST /data/location/<id>/delete` delete location
  - `POST /data/sample` create sample
  - `POST /data/sample/<id>/update` update sample
  - `POST /data/sample/<id>/delete` delete sample
- Seed:
  - `POST /seed/kolkata` inserts demo locations and samples in Kolkata

## Endpoints (Complete)
- UI pages:
  - `GET /` calculator page
  - `GET /dashboard` dashboard with links
  - `GET /map` Google Maps WQI view
  - `GET /data` database dashboard with CRUD
- Calculation:
  - `POST /calculate`
    - Body JSON: `{ "ph": <float>, "do": <float>, "turbidity": <float>, "tds": <float>, "nitrate": <float> }`
    - Returns: `{ "wqi": <number>, "status": <string>, "color": <string> }`
- Location APIs:
  - `GET /api/locations` list all locations with latest WQI
  - `GET /api/wqi?lat=<latitude>&lng=<longitude>` nearest location’s latest WQI
- CRUD APIs:
  - `POST /data/location` create location
  - `POST /data/location/<id>/delete` delete location
  - `POST /data/sample` create sample (for a location)
  - `POST /data/sample/<id>/update` update sample
  - `POST /data/sample/<id>/delete` delete sample
- Seed:
  - `POST /seed/kolkata` insert demo locations and samples for Kolkata
- IoT ingestion:
  - `GET /api/iot` inspect latest readings
  - `POST /api/iot`
    - Body JSON: `{ "temperature_c": <float>, "turbidity_percent": <float> }`
    - Returns: `{ "status": "ok", "id": <int>, "timestamp": "<ISO8601>" }`
  - Render URL for ESP32:
    - `https://wqi-hxhz.onrender.com/api/iot`
    - Example (ESP32 or Postman):
      - `POST https://wqi-hxhz.onrender.com/api/iot` with JSON body above

## Google Map Workflow
- The page `templates/map.html` loads the Google Maps API with your `GOOGLE_MAPS_API_KEY` and includes `static/map.js`.
- On page load, `map.js`:
  - Initializes the map centered on India
  - Calls `GET /api/locations` to fetch all stored locations
  - Renders a circle marker per location. Marker color is derived from the WQI category:
    - `success` `#28a745`
    - `info` `#17a2b8`
    - `warning` `#ffc107`
    - `orange` `#fd7e14`
    - `danger` `#343a40`
  - Clicking a marker opens an info window showing the location’s name, coordinates, WQI, and status.
- Clicking anywhere on the map triggers a request to `GET /api/wqi?lat=...&lng=...`:
  - The server picks the nearest location by Haversine distance, fetches the latest sample, computes WQI if needed, and returns WQI with `status` and `color`.
  - The page highlights the nearest location by dropping a larger marker and opens its info window, panning/zooming to it.

## Database Page Workflow
- `templates/data.html` shows a table of locations with their latest sample and WQI.
- Actions:
  - Add Location by name and coordinates
  - Add Sample by selecting location and entering parameters
  - Update Sample inline for the latest sample
  - Delete Sample
  - Delete Location (cascades and removes samples)
  - Seed demo data for Kolkata

## Demo Data
- Seed Kolkata water bodies:
  - PowerShell:
    - `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/seed/kolkata`
  - The database page also includes a “Seed Kolkata Samples” button

## Deployment Notes
- SQLite is convenient for local development but not ideal for Render:
  - The filesystem is ephemeral and may reset
  - Concurrency and scaling limitations
- For production on Render:
  - Use managed PostgreSQL and set `SQLALCHEMY_DATABASE_URI` to a Postgres URL
  - Consider adding migrations (e.g., Flask-Migrate)
  - Keep the app behind Gunicorn using `Procfile`
  - Ensure `GOOGLE_MAPS_API_KEY` is configured

## Extensibility
- The design is modular:
  - ORM models and business logic are separate from UI templates
  - Color and category mapping is consistent and reusable
  - APIs return simple JSON contracts for mobile or sensors
- To extend:
  - Add auth for admin CRUD
  - Add pagination and filtering
  - Add bulk import for locations/samples (CSV/JSON)
  - Switch to Postgres with geospatial indexing for nearest queries

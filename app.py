from flask import Flask, render_template, request, jsonify
import os
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, create_engine, inspect
import csv
import threading
import requests
import re
import pandas as pd
import io
from flask import send_file

# --- Application Setup ---
app = Flask(__name__)
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "wqi.db")

# Default to SQLite
sqlite_uri = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_DATABASE_URI"] = sqlite_uri

# Check external DB if provided
external_db_url = os.environ.get("DATABASE_URL")
if external_db_url:
    try:
        # Test connection with a short timeout
        test_engine = create_engine(external_db_url, connect_args={'connect_timeout': 3})
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        app.config["SQLALCHEMY_DATABASE_URI"] = external_db_url
        print("Using external database.")
    except Exception as e:
        print(f"External database connection failed: {e}. Falling back to SQLite.")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
with app.app_context():
    try:
        db.create_all()
        # Migration check for 'temperature' column in 'water_samples'
        inspector = inspect(db.engine)
        if inspector.has_table("water_samples"):
            columns = [col['name'] for col in inspector.get_columns('water_samples')]
            if 'temperature' not in columns:
                print("Migrating: Adding 'temperature' column to water_samples table...")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE water_samples ADD COLUMN temperature FLOAT"))
                    conn.commit()
                print("Migration successful.")
        # Migration for IoT readings: add 'ph' and 'turbidity_ntu' if missing
        if inspector.has_table("iot_readings"):
            iot_columns = [col['name'] for col in inspector.get_columns('iot_readings')]
            with db.engine.connect() as conn:
                if 'ph' not in iot_columns:
                    try:
                        print("Migrating: Adding 'ph' column to iot_readings table...")
                        conn.execute(text("ALTER TABLE iot_readings ADD COLUMN ph FLOAT"))
                        conn.commit()
                        print("Migration successful.")
                    except Exception as e:
                        print(f"Migration warning (ph): {e}")
                if 'turbidity_ntu' not in iot_columns:
                    try:
                        print("Migrating: Adding 'turbidity_ntu' column to iot_readings table...")
                        conn.execute(text("ALTER TABLE iot_readings ADD COLUMN turbidity_ntu FLOAT"))
                        conn.commit()
                        print("Migration successful.")
                    except Exception as e:
                        print(f"Migration warning (turbidity_ntu): {e}")
    except Exception as e:
        print(f"Error creating/migrating tables: {e}")
iot_lock = threading.Lock()

# --- WQI Calculation Constants ---
WEST_BENGAL_STATIC_DATA = [
    {"name": "Ganga (Hooghly) River", "location": "Kolkata (Dakshineswar)", "latitude": 22.6531, "longitude": 88.3717, "wqi": 65, "status": "Poor", "category": "River / Drinking Source"},
    {"name": "Damodar River", "location": "Durgapur", "latitude": 23.5204, "longitude": 87.3119, "wqi": 55, "status": "Poor", "category": "River / Industrial Area"},
    {"name": "Teesta River", "location": "Jalpaiguri", "latitude": 26.5405, "longitude": 88.7193, "wqi": 35, "status": "Good", "category": "River"},
    {"name": "Mahananda River", "location": "Siliguri", "latitude": 26.7075, "longitude": 88.4300, "wqi": 60, "status": "Poor", "category": "River / Urban Runoff"},
    {"name": "Rupnarayan River", "location": "Kolaghat", "latitude": 22.4308, "longitude": 87.8700, "wqi": 45, "status": "Good", "category": "River"},
    {"name": "Subarnarekha River", "location": "Jhargram", "latitude": 22.4500, "longitude": 86.9900, "wqi": 40, "status": "Good", "category": "River"},
    {"name": "Jaldhaka River", "location": "Mathabhanga", "latitude": 26.3400, "longitude": 89.2100, "wqi": 30, "status": "Good", "category": "River"},
    {"name": "Vidyadhari River", "location": "Haroa", "latitude": 22.6000, "longitude": 88.6800, "wqi": 80, "status": "Very Poor", "category": "River / Sewage"},
    {"name": "Kangsabati River", "location": "Midnapore", "latitude": 22.4200, "longitude": 87.3200, "wqi": 42, "status": "Good", "category": "River / Irrigation"},
    {"name": "Muriganga River", "location": "Kakdwip", "latitude": 21.8700, "longitude": 88.1800, "wqi": 50, "status": "Good", "category": "Estuary"},
    # Kolkata Samples
    {"name": "Hooghly River", "location": "Kolkata", "latitude": 22.5726, "longitude": 88.3639, "wqi": 62, "status": "Poor", "category": "River / Urban"},
    {"name": "Rabindra Sarobar", "location": "Kolkata", "latitude": 22.5126, "longitude": 88.3498, "wqi": 45, "status": "Good", "category": "Lake / Recreational"},
    {"name": "East Kolkata Wetlands", "location": "Kolkata", "latitude": 22.5500, "longitude": 88.4300, "wqi": 55, "status": "Poor", "category": "Wetland / Treatment"},
    {"name": "Subhas Sarovar", "location": "Kolkata", "latitude": 22.5787, "longitude": 88.4003, "wqi": 40, "status": "Good", "category": "Lake / Recreational"},
    {"name": "Salt Lake Water Body", "location": "Bidhannagar", "latitude": 22.5867, "longitude": 88.4173, "wqi": 48, "status": "Good", "category": "Lake / Urban"},
]

# --- ORM Models ---
class Location(db.Model):
    __tablename__ = "locations"
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False, index=True)
    longitude = db.Column(db.Float, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=True)
    samples = db.relationship("WaterSample", backref="location", lazy=True, cascade="all, delete-orphan")

class WaterSample(db.Model):
    __tablename__ = "water_samples"
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False, index=True)
    ph = db.Column(db.Float, nullable=True)
    do = db.Column(db.Float, nullable=True)
    tds = db.Column(db.Float, nullable=True)
    turbidity = db.Column(db.Float, nullable=True)
    nitrate = db.Column(db.Float, nullable=True)
    temperature = db.Column(db.Float, nullable=True)
    wqi = db.Column(db.Float, nullable=True, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class IoTReading(db.Model):
    __tablename__ = "iot_readings"
    id = db.Column(db.Integer, primary_key=True)
    temperature_c = db.Column(db.Float, nullable=False)
    turbidity_percent = db.Column(db.Float, nullable=False)
    ph = db.Column(db.Float, nullable=True)
    turbidity_ntu = db.Column(db.Float, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

# --- Core WQI Function ---
def clean_response(text):
    if not text:
        return ""
    # Remove <think> tags
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    # Remove Thinking Process: ...
    text = re.sub(r"Thinking Process:[\s\S]*?(?=\n\n|\Z)", "", text, flags=re.IGNORECASE)
    return text.strip()

def calculate_wqi(data):
    IDEAL = {
        "ph": 7.0,
        "do": 14.6,
        "turbidity": 0.0,
        "tds": 0.0,
        "nitrate": 0.0,
        "temperature": 25.0
    }

    STANDARD = {
        "ph": 8.5,
        "do": 5.0,
        "turbidity": 5.0,
        "tds": 500.0,
        "nitrate": 45.0,
        "temperature": 30.0
    }

    # Step 1: Calculate K
    try:
        K = 1 / sum(1 / s for s in STANDARD.values())
    except ZeroDivisionError:
        return 0

    total_qw = 0.0
    total_w = 0.0

    for param in STANDARD:
        # Check if param exists in data and is not None
        if param not in data or data.get(param) is None:
            continue

        try:
            observed = float(data[param])
            ideal = IDEAL[param]
            standard = STANDARD[param]
            weight = K / standard  # dynamic weight

            # Step 2: Qi calculation
            if param == "temperature":
                qi = abs(observed - ideal) / (standard - ideal) * 100
            else:
                qi = (observed - ideal) / (standard - ideal) * 100

            qi = max(qi, 0)  # clamp negative Qi

            total_qw += qi * weight
            total_w += weight

        except (ValueError, TypeError, ZeroDivisionError):
            continue

    if total_w == 0:
        return 0

    return round(total_qw / total_w, 2)

# --- Status Function ---
def get_status(wqi):
    if wqi is None:
        return "No Data", "secondary"
    if wqi <= 25:
        return "Excellent", "success"
    elif wqi <= 50:
        return "Good", "primary"
    elif wqi <= 75:
        return "Poor", "warning"
    elif wqi <= 100:
        return "Very Poor", "danger"
    else:
        return "Unfit for Consumption", "dark"

# --- Utility: Haversine distance (km) ---
def haversine_distance(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# --- Routes ---
@app.route('/')
def home():
    google_maps_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    return render_template(
        "index.html",
        google_maps_key=google_maps_key
    )

@app.route('/dashboard')
def dashboard():
    return render_template("dashboard.html")

@app.route('/map')
def map_page():
    google_maps_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    return render_template("map.html", google_maps_key=google_maps_key)

@app.route('/chatbot.html')
def chatbot_page():
    return render_template("chatbot.html")

@app.route('/login')
def login_page():
    return render_template("login.html")

@app.route('/signup')
def signup_page():
    return render_template("signup.html")

@app.route('/user-dashboard')
def user_dashboard_page():
    return render_template("user_dashboard.html")

@app.route('/chat', methods=['POST'])
def chat():
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "Please provide a question in 'message'"}), 400

    token = os.environ.get("HUGGING_FACE_API_TOKEN")
    if not token:
        return jsonify({"error": "Server is not configured with Hugging Face token"}), 500

    system_prefix = (
        "You are a helpful assistant. Provide detailed and comprehensive answers when the user asks for explanations. "
        "Keep your answers compact and brief yet logical and meaningful, ensuring the user gets a complete answer without being cut off. "
        "Do not include your internal chain of thought or reasoning process in the final output, only the response to the user."
    )
    model_id = os.environ.get("HF_CHAT_MODEL", "HuggingFaceTB/SmolLM3-3B:hf-inference")
    fallback_model = "HuggingFaceTB/SmolLM3-3B:hf-inference"
    try:
        resp = requests.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prefix},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": 3000,
                "temperature": 0.7,
            },
            timeout=60,
        )
    except Exception as e:
        return jsonify({"error": "Chat service unreachable", "detail": str(e)}), 502

    if resp.status_code >= 400:
        try:
            data_err = resp.json()
        except:
            data_err = {}
        if model_id != fallback_model:
            try:
                resp2 = requests.post(
                    "https://router.huggingface.co/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": fallback_model,
                        "messages": [
                            {"role": "system", "content": system_prefix},
                            {"role": "user", "content": user_message},
                        ],
                        "max_tokens": 3000,
                        "temperature": 0.7,
                    },
                    timeout=60,
                )
            except Exception as e2:
                return jsonify({"error": "Chat service unreachable", "detail": str(e2)}), 502
            if resp2.status_code >= 400:
                return jsonify({"error": "Chat service failed", "detail": resp2.text}), 502
            try:
                data = resp2.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
            except Exception:
                return jsonify({"error": "Invalid response from chat service"}), 502
            if not content:
                content = "No answer available."
            
            # Check for incomplete finish
            finish_reason = (
                data.get("choices", [{}])[0]
                .get("finish_reason", "")
            )
            content = clean_response(content)
            if finish_reason == "length":
                content += "\n\n(Note: My response was cut off because it reached the maximum length.)"
                
            return jsonify({"reply": content})
        return jsonify({"error": "Chat service failed", "detail": resp.text}), 502

    try:
        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        finish_reason = (
            data.get("choices", [{}])[0]
            .get("finish_reason", "")
        )
    except Exception:
        return jsonify({"error": "Invalid response from chat service"}), 502

    if not content:
        content = "No answer available."
    content = clean_response(content)
    if finish_reason == "length":
        content += "\n\n(Note: My response was cut off because it reached the maximum length.)"

    return jsonify({"reply": content})

@app.route('/data')
def data_page():
    locations = Location.query.all()
    rows = []
    for loc in locations:
        sample = (WaterSample.query
                  .filter_by(location_id=loc.id)
                  .order_by(WaterSample.timestamp.desc())
                  .first())
        if sample and sample.wqi is None:
            data = {"ph": sample.ph, "do": sample.do, "tds": sample.tds, "turbidity": sample.turbidity, "nitrate": sample.nitrate, "temperature": sample.temperature}
            sample.wqi = calculate_wqi(data)
            db.session.commit()
        wqi_val = sample.wqi if sample else None
        status, color = get_status(wqi_val) if wqi_val is not None else ("No Data", "secondary")
        rows.append({
            "name": loc.name or "Unnamed",
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "wqi": wqi_val,
            "status": status,
            "color": color,
            "timestamp": sample.timestamp if sample else None,
            "location_id": loc.id,
            "sample_id": sample.id if sample else None,
            "ph": sample.ph if sample else None,
            "do": sample.do if sample else None,
            "tds": sample.tds if sample else None,
            "turbidity": sample.turbidity if sample else None,
            "nitrate": sample.nitrate if sample else None,
            "temperature": sample.temperature if sample else None,
        })
    return render_template("data.html", rows=rows, wb_data=WEST_BENGAL_STATIC_DATA)

@app.route('/download_excel')
def download_excel():
    locations = Location.query.all()
    data_list = []
    
    # User Data
    for loc in locations:
        sample = (WaterSample.query
                  .filter_by(location_id=loc.id)
                  .order_by(WaterSample.timestamp.desc())
                  .first())
        
        row = {
            "Location Name": loc.name,
            "Latitude": loc.latitude,
            "Longitude": loc.longitude,
            "WQI": sample.wqi if sample else None,
            "Status": get_status(sample.wqi)[0] if sample and sample.wqi is not None else "No Data",
            "pH": sample.ph if sample else None,
            "DO (mg/L)": sample.do if sample else None,
            "TDS (mg/L)": sample.tds if sample else None,
            "Turbidity (NTU)": sample.turbidity if sample else None,
            "Nitrate (mg/L)": sample.nitrate if sample else None,
            "Temperature (C)": sample.temperature if sample else None,
            "Timestamp": sample.timestamp if sample else None,
            "Type": "User Added"
        }
        data_list.append(row)
    
    # Static West Bengal Data
    for item in WEST_BENGAL_STATIC_DATA:
        row = {
            "Location Name": item["name"] + " - " + item["location"],
            "Latitude": item["latitude"],
            "Longitude": item["longitude"],
            "WQI": item["wqi"],
            "Status": item["status"],
            "pH": None,
            "DO (mg/L)": None,
            "TDS (mg/L)": None,
            "Turbidity (NTU)": None,
            "Nitrate (mg/L)": None,
            "Temperature (C)": 25.0,
            "Timestamp": None,
            "Type": "Static Reference (West Bengal)"
        }
        data_list.append(row)

    df = pd.DataFrame(data_list)
    
    # Try using openpyxl for Excel, fallback to CSV if missing
    try:
        import openpyxl
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Water Quality Data')
        
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'water_quality_data_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
    except ImportError:
        # Fallback to CSV
        output = io.BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'water_quality_data_{datetime.now().strftime("%Y%m%d")}.csv'
        )

@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.json
    score = calculate_wqi(data)
    status, color = get_status(score)
    return jsonify({
        "wqi": score,
        "status": status,
        "color": color
    })

@app.route('/api/locations', methods=['GET'])
def api_locations():
    locations = Location.query.all()
    output = []
    
    # User added locations
    for loc in locations:
        sample = (WaterSample.query
                  .filter_by(location_id=loc.id)
                  .order_by(WaterSample.timestamp.desc())
                  .first())
        wqi_val = None
        if sample:
            if sample.wqi is None:
                data = {"ph": sample.ph, "do": sample.do, "tds": sample.tds, "turbidity": sample.turbidity, "nitrate": sample.nitrate, "temperature": sample.temperature}
                sample.wqi = calculate_wqi(data)
                db.session.commit()
            wqi_val = sample.wqi
        status, color = get_status(wqi_val) if wqi_val is not None else ("No Data", "secondary")
        output.append({
            "name": loc.name,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "wqi": wqi_val,
            "status": status,
            "color": color
        })
    
    # Static West Bengal locations
    for item in WEST_BENGAL_STATIC_DATA:
        # Determine color based on WQI value using the standard get_status function
        # If static data has hardcoded status, we might need to adjust logic, but using get_status is safer if we have WQI
        # However, WEST_BENGAL_STATIC_DATA has 'wqi' and 'status'.
        # Let's trust 'wqi' to derive the color if possible, or map status explicitly.
        # Given the request, let's map status to the new colors strictly.
        # But wait, get_status does exactly what is needed based on WQI.
        # Let's use get_status(item["wqi"]) to ensure consistency.
        status, color = get_status(item["wqi"])

        output.append({
            "name": item["name"] + " (" + item["location"] + ")",
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "wqi": item["wqi"],
            "status": status, # Overwrite static status with dynamically calculated one to be safe, or keep item["status"]
            "color": color
        })

    return jsonify(output)

@app.route('/data/location', methods=['POST'])
def create_location():
    name = request.form.get("name") or None
    try:
        latitude = float(request.form.get("latitude"))
        longitude = float(request.form.get("longitude"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid latitude/longitude"}), 400
    loc = Location(name=name, latitude=latitude, longitude=longitude)
    db.session.add(loc)
    db.session.commit()
    return jsonify({"status": "ok", "location_id": loc.id}), 200

@app.route('/data/location/<int:location_id>/delete', methods=['POST'])
def delete_location(location_id):
    loc = Location.query.get_or_404(location_id)
    db.session.delete(loc)
    db.session.commit()
    return jsonify({"status": "ok"}), 200

@app.route('/data/sample', methods=['POST'])
def create_sample():
    try:
        location_id = int(request.form.get("location_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid location"}), 400
    loc = Location.query.get_or_404(location_id)
    def f(name):
        v = request.form.get(name)
        return float(v) if v not in (None, "",) else None
    payload = {
        "ph": f("ph"),
        "do": f("do"),
        "tds": f("tds"),
        "turbidity": f("turbidity"),
        "nitrate": f("nitrate"),
        "temperature": f("temperature"),
    }
    sample = WaterSample(location_id=loc.id, **payload)
    sample.wqi = calculate_wqi(payload)
    db.session.add(sample)
    db.session.commit()
    return jsonify({"status": "ok", "sample_id": sample.id}), 200

@app.route('/data/sample/<int:sample_id>/update', methods=['POST'])
def update_sample(sample_id):
    sample = WaterSample.query.get_or_404(sample_id)
    def f(name, current):
        v = request.form.get(name)
        return float(v) if v not in (None, "",) else current
    sample.ph = f("ph", sample.ph)
    sample.do = f("do", sample.do)
    sample.tds = f("tds", sample.tds)
    sample.turbidity = f("turbidity", sample.turbidity)
    sample.nitrate = f("nitrate", sample.nitrate)
    sample.temperature = f("temperature", sample.temperature)
    payload = {"ph": sample.ph, "do": sample.do, "tds": sample.tds, "turbidity": sample.turbidity, "nitrate": sample.nitrate, "temperature": sample.temperature}
    sample.wqi = calculate_wqi(payload)
    db.session.commit()
    return jsonify({"status": "ok"}), 200

@app.route('/data/sample/<int:sample_id>/delete', methods=['POST'])
def delete_sample(sample_id):
    sample = WaterSample.query.get_or_404(sample_id)
    db.session.delete(sample)
    db.session.commit()
    return jsonify({"status": "ok"}), 200

@app.route('/api/iot', methods=['POST', 'GET'])
def ingest_iot():
    if request.method == 'GET':
        latest = (IoTReading.query
                  .order_by(IoTReading.timestamp.desc())
                  .first())
        if not latest:
            return jsonify({"error": "No data"}), 404
        payload = {}
        if latest.temperature_c is not None:
            payload["temperature_c"] = round(float(latest.temperature_c), 2)
        if latest.ph is not None:
            payload["ph"] = round(float(latest.ph), 2)
        turb_val = latest.turbidity_ntu if latest.turbidity_ntu is not None else latest.turbidity_percent
        if turb_val is not None:
            payload["turbidity"] = round(float(turb_val), 2)
        payload["timestamp"] = latest.timestamp.isoformat()
        return jsonify(payload)
    payload = request.get_json(silent=True) or {}
    # Parse temperature
    try:
        temperature_c = float(payload.get("temperature_c"))
    except (TypeError, ValueError):
        return jsonify({"error": "Missing or invalid 'temperature_c'"}), 400
    # Parse pH (optional)
    ph_val = None
    if payload.get("ph") is not None:
        try:
            ph_val = float(payload.get("ph"))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid 'ph'"}), 400
    # Parse turbidity from any of the keys
    turbidity_ntu_val = None
    turbidity_percent_val = None
    if payload.get("turbidity") is not None:
        try:
            turbidity_ntu_val = float(payload.get("turbidity"))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid 'turbidity'"}), 400
    elif payload.get("turbidity_ntu") is not None:
        try:
            turbidity_ntu_val = float(payload.get("turbidity_ntu"))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid 'turbidity_ntu'"}), 400
    if payload.get("turbidity_percent") is not None:
        try:
            turbidity_percent_val = float(payload.get("turbidity_percent"))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid 'turbidity_percent'"}), 400
    # Require some turbidity value
    if turbidity_ntu_val is None and turbidity_percent_val is None:
        return jsonify({"error": "Provide 'turbidity' (or 'turbidity_ntu') or 'turbidity_percent'"}), 400
    # If percent missing, mirror from NTU to keep non-null constraint
    if turbidity_percent_val is None and turbidity_ntu_val is not None:
        turbidity_percent_val = turbidity_ntu_val
    ts = datetime.utcnow()
    rec = IoTReading(
        temperature_c=temperature_c,
        turbidity_percent=turbidity_percent_val,
        ph=ph_val,
        turbidity_ntu=turbidity_ntu_val,
        timestamp=ts
    )
    db.session.add(rec)
    db.session.commit()
    csv_path = os.path.join(DATA_DIR, "iot.csv")
    write_header = not os.path.exists(csv_path)
    with iot_lock:
        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["id", "temperature_c", "ph", "turbidity_percent", "turbidity_ntu", "timestamp"])
            writer.writerow([rec.id, temperature_c, ph_val, turbidity_percent_val, turbidity_ntu_val, ts.isoformat()])
    return jsonify({"status": "ok", "id": rec.id, "timestamp": ts.isoformat()})

@app.route('/sensors')
def sensors_page():
    return render_template("sensors.html")

@app.route('/api/wqi', methods=['GET'])
def api_wqi():
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid or missing lat/lng"}), 400

    locations = Location.query.all()
    if not locations:
        return jsonify({"error": "No locations available"}), 404

    nearest = None
    nearest_dist = float("inf")
    for loc in locations:
        dist = haversine_distance(lat, lng, loc.latitude, loc.longitude)
        if dist < nearest_dist:
            nearest = loc
            nearest_dist = dist

    if nearest is None:
        return jsonify({"error": "No nearby location found"}), 404

    sample = (WaterSample.query
              .filter_by(location_id=nearest.id)
              .order_by(WaterSample.timestamp.desc())
              .first())
    if sample is None:
        return jsonify({"error": "No samples for nearest location"}), 404

    if sample.wqi is None:
        data = {
            "ph": sample.ph,
            "do": sample.do,
            "tds": sample.tds,
            "turbidity": sample.turbidity,
            "nitrate": sample.nitrate
        }
        sample.wqi = calculate_wqi(data)
        db.session.commit()

    status, color = get_status(sample.wqi)
    return jsonify({
        "latitude": nearest.latitude,
        "longitude": nearest.longitude,
        "wqi": sample.wqi,
        "status": status,
        "color": color
    })

# --- Run ---
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

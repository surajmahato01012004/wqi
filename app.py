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
import json

# --- Application Setup ---
app = Flask(__name__)  # create the Flask web application
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "wqi.db")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CONFIG = {}

def load_config():
    global CONFIG
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:  # open config.json from project root
            CONFIG = json.load(f) or {}  # parse JSON into a Python dict; default to empty if file is blank
    except Exception:
        CONFIG = {}  # if config fails to load, keep an empty dict so code can use safe defaults

load_config()

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
iot_lock = threading.Lock()

def seed_reference_locations():
    # load static reference locations from JSON and insert into the database if missing
    try:
        static_path = os.path.join(DATA_DIR, "static_wb.json")
        if not os.path.exists(static_path):
            return
        with open(static_path, "r", encoding="utf-8") as f:
            items = json.load(f) or []
        created = 0
        for item in items:
            name = item.get("name")
            location = item.get("location")
            exists = ReferenceLocation.query.filter_by(name=name, location=location).first()  # skip duplicates
            if exists:
                continue
            rec = ReferenceLocation(
                name=name,
                location=location,
                latitude=float(item.get("latitude")),
                longitude=float(item.get("longitude")),
                wqi=float(item.get("wqi")),
                status=item.get("status"),
                category=item.get("category")
            )
            db.session.add(rec)  # stage the new row for insert
            created += 1
        if created:
            db.session.commit()  # write inserts to the database
            print(f"Seeded {created} reference locations from static_wb.json")
    except Exception as e:
        print(f"Reference seed error: {e}")

# --- ORM Models ---
class Location(db.Model):
    __tablename__ = "locations"
    # stores a named lat/long and relates to multiple water samples
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False, index=True)
    longitude = db.Column(db.Float, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=True)
    samples = db.relationship("WaterSample", backref="location", lazy=True, cascade="all, delete-orphan")

class WaterSample(db.Model):
    __tablename__ = "water_samples"
    # stores one set of water readings for a location at a point in time
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
    # raw readings posted by an IoT device (ESP32)
    id = db.Column(db.Integer, primary_key=True)
    temperature_c = db.Column(db.Float, nullable=False)
    turbidity_percent = db.Column(db.Float, nullable=False)
    ph = db.Column(db.Float, nullable=True)
    turbidity_ntu = db.Column(db.Float, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class ReferenceLocation(db.Model):
    __tablename__ = "reference_locations"
    # static reference points with precomputed WQI and labels
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    wqi = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(64), nullable=False)
    category = db.Column(db.String(255), nullable=True)

with app.app_context():
    try:
        db.create_all()  # ensure tables exist
        inspector = inspect(db.engine)
        if inspector.has_table("water_samples"):
            columns = [col['name'] for col in inspector.get_columns('water_samples')]
            if 'temperature' not in columns:
                print("Migrating: Adding 'temperature' column to water_samples table...")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE water_samples ADD COLUMN temperature FLOAT"))
                    conn.commit()
                print("Migration successful.")
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
        seed_reference_locations()  # insert static locations from JSON
    except Exception as e:
        print(f"Error creating/migrating tables: {e}")

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
    """
    Calculates the Water Quality Index (WQI) using the Weighted Arithmetic WQI method.

    Parameters:
    - data (dict): Observed values for water quality parameters.
      Example: {"ph":7.8, "do":6.5, "turbidity":3.0, "tds":200, "nitrate":10, "temperature":28}

    Returns:
    - float: Water Quality Index (rounded to 2 decimals), or None if no valid data.
    """

    cfg_wqi = CONFIG.get("wqi", {})  # read WQI portion of config
    IDEAL = cfg_wqi.get("ideal", {  # ideal target values for each parameter
        "ph": 7.0,
        "do": 14.6,
        "turbidity": 0.0,
        "tds": 0.0,
        "nitrate": 0.0,
        "temperature": 25.0,
    })
    STANDARD = cfg_wqi.get("standard", {  # permissible standard values for each parameter
        "ph": 8.5,
        "do": 5.0,
        "turbidity": 5.0,
        "tds": 500.0,
        "nitrate": 45.0,
        "temperature": 30.0,
    })

    # 3) Proportionality constant K
    try:
        K = 1 / sum(1 / v for v in STANDARD.values())  # proportionality constant using standards
    except ZeroDivisionError:
        return None

    total_qw = 0.0
    total_w = 0.0

    for param in STANDARD:  # iterate each parameter (ph, do, turbidity, etc.)
        if param not in data or data[param] is None:
            continue

        try:
            Vo = float(data[param])  # observed value from input
            Vi = IDEAL[param]        # ideal target value
            Vs = STANDARD[param]     # permissible standard value

            Wi = K / Vs  # unit weight for this parameter

            # quality rating Qi: how far the observed value is from ideal/standard
            if param == "do":
                Qi = (Vi - Vo) / (Vi - Vs) * 100  # for DO, lower than ideal is worse
            elif param in ["ph", "temperature"]:
                Qi = abs(Vo - Vi) / (Vs - Vi) * 100  # absolute deviation from ideal
            else:
                Qi = (Vo - Vi) / (Vs - Vi) * 100  # higher than ideal indicates worse quality

            Qi = max(0.0, Qi)  # clamp negative to zero

            total_qw += Qi * Wi  # accumulate Qi weighted
            total_w += Wi        # accumulate weights

        except (ValueError, TypeError, ZeroDivisionError):
            continue

    if total_w == 0:
        return None

    return round(total_qw / total_w, 2)  # weighted average -> final WQI


def get_status(wqi):
    """
    Returns a qualitative status for a given WQI.

    - wqi: Water Quality Index (float)
    Returns: (status_string, bootstrap_color)
    """

    if wqi is None:
        return "No Data", "secondary"  # no score -> show secondary
    thresholds = CONFIG.get("wqi", {}).get("status_thresholds")  # pick thresholds from config
    if not thresholds:
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
    for t in thresholds:  # find the first threshold bucket matching this wqi
        mx = t.get("max")
        if mx is None or wqi <= float(mx):
            return t.get("status") or "Unknown", t.get("color") or "secondary"
    return "Unknown", "secondary"

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
    google_maps_key = os.environ.get("GOOGLE_MAPS_API_KEY")  # pass Google Maps key from environment to template
    return render_template(
        "index.html",
        google_maps_key=google_maps_key
    )

@app.route('/dashboard')
def dashboard():
    return render_template("dashboard.html")

@app.route('/map')
def map_page():
    google_maps_key = os.environ.get("GOOGLE_MAPS_API_KEY")  # used by the map template to load Google Maps
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
    payload = request.get_json(silent=True) or {}  # read JSON body with user's message
    user_message = (payload.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "Please provide a question in 'message'"}), 400

    token = os.environ.get("HUGGING_FACE_API_TOKEN")  # token must be set as env var
    if not token:
        return jsonify({"error": "Server is not configured with Hugging Face token"}), 500

    system_prefix = (
        "You are a helpful assistant. Provide detailed and comprehensive answers when the user asks for explanations. "
        "Keep your answers compact and brief yet logical and meaningful, ensuring the user gets a complete answer without being cut off. "
        "Do not include your internal chain of thought or reasoning process in the final output, only the response to the user."
    )
    model_id = os.environ.get("HF_CHAT_MODEL", "HuggingFaceTB/SmolLM3-3B:hf-inference")  # primary chat model
    fallback_model = "HuggingFaceTB/SmolLM3-3B:hf-inference"  # fallback if primary fails
    try:
        resp = requests.post(  # call Hugging Face chat completions
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

    return jsonify({"reply": content})  # return cleaned model output to the UI

@app.route('/data')
def data_page():
    locations = Location.query.all()  # read all locations
    rows = []
    for loc in locations:
        sample = (WaterSample.query  # fetch most recent sample for the location
                  .filter_by(location_id=loc.id)
                  .order_by(WaterSample.timestamp.desc())
                  .first())
        if sample and sample.wqi is None:
            data = {"ph": sample.ph, "do": sample.do, "tds": sample.tds, "turbidity": sample.turbidity, "nitrate": sample.nitrate, "temperature": sample.temperature}
            sample.wqi = calculate_wqi(data)
            db.session.commit()
        wqi_val = sample.wqi if sample else None  # may be None if no sample exists
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
    ref_rows = ReferenceLocation.query.all()
    return render_template("data.html", rows=rows, wb_data=ref_rows)

@app.route('/download_excel')
def download_excel():
    locations = Location.query.all()  # pull all data to export
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
    
    # Static Reference Data
    for item in ReferenceLocation.query.all():
        row = {
            "Location Name": item.name + " - " + item.location,
            "Latitude": item.latitude,
            "Longitude": item.longitude,
            "WQI": item.wqi,
            "Status": item.status,
            "pH": None,
            "DO (mg/L)": None,
            "TDS (mg/L)": None,
            "Turbidity (NTU)": None,
            "Nitrate (mg/L)": None,
            "Temperature (C)": None,
            "Timestamp": None,
            "Type": "Static Reference"
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
    data = request.json  # parse input parameters for WQI calculation
    score = calculate_wqi(data)  # compute WQI
    status, color = get_status(score)
    return jsonify({
        "wqi": score,
        "status": status,
        "color": color
    })

@app.route('/api/locations', methods=['GET'])
def api_locations():
    locations = Location.query.all()  # list all locations with latest WQI
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
        status, color = get_status(wqi_val) if wqi_val is not None else ("No Data", "secondary")  # derive status from WQI
        output.append({
            "name": loc.name,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "wqi": wqi_val,
            "status": status,
            "color": color
        })
    
    # Static Reference locations
    for item in ReferenceLocation.query.all():
        status, color = get_status(item.wqi)
        output.append({
            "name": item.name + " (" + item.location + ")",
            "latitude": item.latitude,
            "longitude": item.longitude,
            "wqi": item.wqi,
            "status": status,
            "color": color
        })

    return jsonify(output)  # send combined list (user + reference)

@app.route('/data/location', methods=['POST'])
def create_location():
    name = request.form.get("name") or None  # optional name
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
    sample.wqi = calculate_wqi(payload)  # compute and store WQI for the sample
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
    if request.method == 'GET':  # return latest IoT reading
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
    payload = request.get_json(silent=True) or {}  # parse POSTed IoT reading
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
    ts = datetime.utcnow()  # record time of ingestion
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
        with open(csv_path, "a", newline="") as f:  # also append to a CSV for quick inspection
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["id", "temperature_c", "ph", "turbidity_percent", "turbidity_ntu", "timestamp"])
            writer.writerow([rec.id, temperature_c, ph_val, turbidity_percent_val, turbidity_ntu_val, ts.isoformat()])
    return jsonify({"status": "ok", "id": rec.id, "timestamp": ts.isoformat()})

@app.route('/sensors')
def sensors_page():
    return render_template("sensors.html")

@app.route('/config', methods=['GET'])
def get_config():
    return jsonify(CONFIG or {})  # expose current config to frontend

@app.route('/api/wqi', methods=['GET'])
def api_wqi():
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid or missing lat/lng"}), 400

    locations = Location.query.all()  # choose the nearest stored location to the clicked point
    if not locations:
        return jsonify({"error": "No locations available"}), 404

    nearest = None
    nearest_dist = float("inf")
    for loc in locations:
        dist = haversine_distance(lat, lng, loc.latitude, loc.longitude)  # compute great-circle distance (km)
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
        sample.wqi = calculate_wqi(data)  # compute WQI if missing
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
        try:
            seed_reference_locations()
        except Exception as e:
            print(f"Startup seed failed: {e}")
    app.run(debug=True)  # run the development server

from flask import Flask, render_template, request, jsonify
import os
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
from flask_sqlalchemy import SQLAlchemy
import csv
import threading
import requests
import re

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "wqi.db")
DB_URL = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_DATABASE_URI"] = DB
Llation Constants ---i: , 'weight': 2}
DBURLf DB_RLc(dsq)i///DB_PATH    __tablename__ = "locations"
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False, index=True)
    longitude = db.Cole = db.Column(db.String(255), nullable=True)
samples = db.relam
    __tablename__ = "water_samples"
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False, index=True)
    ph = db.Column(db.Float, nullable=True)
    do = db.Column(db.Float, nullable=True)
    tds = db.Column(db.Float, nullable=True)
    turbidity = db.Column(db.Float, nullable=True)
    nitrate = db.Column(db.Float, nullable=True)
    wqi = db.Column(db.Float, nullable=True, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class IoTReading(db.Model):
    __tablename__ = "iot_readings"
    id = db.Column(db.Integer, primary_key=True)
    temperature_c = db.Column(db.Float, nullable=False)
    turbidity_percent = db.Column(db.Float, nullable=False)
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
    total_w = 0
    total_qw = 0

    for param, config in PARAMETERS.items():
        if param in data and data[param] is not None:
            try:
                observed = float(data[param])
                standard = config['standard']
                ideal = config['ideal']
                weight = config['weight']

                if (standard - ideal) == 0:
                    qi = 0
                else:
                    qi = 100 * (observed - ideal) / (standard - ideal)

                if param == 'do':
                    if observed >= standard:
                        qi = 100 * (1 - observed / ideal)
                    else:
                        qi = 100 + 100 * (standard - observed) / standard

                qi = max(0, qi)

                total_qw += qi * weight
                total_w += weight
            except:
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
                "max_tokens": 1000,
                "temperature": 0.7,
            },
            timeout=30,
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
                        "max_tokens": 300,
                        "temperature": 0.7,
                    },
                    timeout=30,
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
            if not content:10
                content = "No answer available."
            content = re.sub(r"<think>[\\s\\S]*?</think>", "", content, flags=re.IGNORECASE)
            content = content.strip()
            return jsonify({"reply": content})
        return jsonify({"error": "Chat service failed", "detail": resp.text}), 502

    try:
        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
    except Exception:
        return jsonify({"error": "Invalid response from chat service"}), 502

    if not content:
        content = "No answer available."
    content = re.sub(r"<think>[\\s\\S]*?</think>", "", content, flags=re.IGNORECASE)
    content = content.strip()

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
            data = {"ph": sample.ph, "do": sample.do, "tds": sample.tds, "turbidity": sample.turbidity, "nitrate": sample.nitrate}
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
        })
    return render_template("data.html", rows=rows)

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
    for loc in locations:
        sample = (WaterSample.query
                  .filter_by(location_id=loc.id)
                  .order_by(WaterSample.timestamp.desc())
                  .first())
        wqi_val = None
        if sample:
            if sample.wqi is None:
                data = {"ph": sample.ph, "do": sample.do, "tds": sample.tds, "turbidity": sample.turbidity, "nitrate": sample.nitrate}
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
    payload = {"ph": sample.ph, "do": sample.do, "tds": sample.tds, "turbidity": sample.turbidity, "nitrate": sample.nitrate}
    sample.wqi = calculate_wqi(payload)
    db.session.commit()
    return jsonify({"status": "ok"}), 200

@app.route('/data/sample/<int:sample_id>/delete', methods=['POST'])
def delete_sample(sample_id):
    sample = WaterSample.query.get_or_404(sample_id)
    db.session.delete(sample)
    db.session.commit()
    return jsonify({"status": "ok"}), 200

@app.route('/seed/kolkata', methods=['POST'])
def seed_kolkata():
    kolkata_points = [
        {"name": "Hooghly River - Kolkata", "latitude": 22.5726, "longitude": 88.3639, "sample": {"ph": 7.4, "do": 5.8, "tds": 300, "turbidity": 4.0, "nitrate": 20}},
        {"name": "Rabindra Sarobar", "latitude": 22.5126, "longitude": 88.3498, "sample": {"ph": 7.1, "do": 6.5, "tds": 250, "turbidity": 3.0, "nitrate": 12}},
        {"name": "East Kolkata Wetlands", "latitude": 22.55, "longitude": 88.43, "sample": {"ph": 7.3, "do": 6.2, "tds": 270, "turbidity": 3.8, "nitrate": 16}},
        {"name": "Subhas Sarovar", "latitude": 22.5787, "longitude": 88.4003, "sample": {"ph": 7.0, "do": 6.8, "tds": 230, "turbidity": 2.5, "nitrate": 10}},
        {"name": "Salt Lake (Bidhannagar) Water Body", "latitude": 22.5867, "longitude": 88.4173, "sample": {"ph": 7.2, "do": 6.1, "tds": 240, "turbidity": 2.8, "nitrate": 11}},
    ]
    created = 0
    for p in kolkata_points:
        loc = Location.query.filter_by(latitude=p["latitude"], longitude=p["longitude"]).first()
        if not loc:
            loc = Location(latitude=p["latitude"], longitude=p["longitude"], name=p["name"])
            db.session.add(loc)
            db.session.commit()
        sample = WaterSample(location_id=loc.id, **p["sample"])
        sample.wqi = calculate_wqi(p["sample"])
        db.session.add(sample)
        db.session.commit()
        created += 1
    return jsonify({"status": "ok", "created": created})

@app.route('/api/iot', methods=['POST', 'GET'])
def ingest_iot():
    if request.method == 'GET':
        latest = (IoTReading.query
                  .order_by(IoTReading.timestamp.desc())
                  .limit(20)
                  .all())
        return jsonify({
            "message": "Send POST with JSON {temperature_c, turbidity_percent} to store readings.",
            "count": len(latest),
            "latest": [
                {
                    "id": r.id,
                    "temperature_c": r.temperature_c,
                    "turbidity_percent": r.turbidity_percent,
                    "timestamp": r.timestamp.isoformat()
                } for r in latest
            ]
        })
    payload = request.get_json(silent=True) or {}
    try:
        temperature_c = float(payload.get("temperature_c"))
        turbidity_percent = float(payload.get("turbidity_percent"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid payload"}), 400
    ts = datetime.utcnow()
    rec = IoTReading(temperature_c=temperature_c, turbidity_percent=turbidity_percent, timestamp=ts)
    db.session.add(rec)
    db.session.commit()
    csv_path = os.path.join(DATA_DIR, "iot.csv")
    write_header = not os.path.exists(csv_path)
    with iot_lock:
        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["id", "temperature_c", "turbidity_percent", "timestamp"])
            writer.writerow([rec.id, temperature_c, turbidity_percent, ts.isoformat()])
    return jsonify({"status": "ok", "id": rec.id, "timestamp": ts.isoformat()})

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

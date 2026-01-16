const containerEl = document.getElementById('sensor-container');
const statTemp = document.getElementById('stat-temp');
const statPh = document.getElementById('stat-ph');
const statTurbidity = document.getElementById('stat-turbidity');
const lastUpdateEl = document.getElementById('last-update');
const statWqi = document.getElementById('stat-wqi');
const badgeWqi = document.getElementById('badge-wqi');
const sensorSafetyEl = document.getElementById('sensor-safety');
const wqiMarkerSensor = document.getElementById('wqi-marker-sensor');
const sensorWhyList = document.getElementById('sensor-why-list');

function formatIndianTimestamp(ts) {
  if (!ts) return '';
  const iso = ts.endsWith('Z') ? ts : ts + 'Z';
  const d = new Date(iso);
  const fmt = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  });
  return fmt.format(d);
}

async function fetchLatest() {
  try {
    const res = await fetch('/api/iot');
    if (!res.ok) {
      containerEl.classList.add('d-none');
      lastUpdateEl.textContent = 'Waiting for data…';
      return;
    }
    const item = await res.json();
    renderStats(item);
    containerEl.classList.remove('d-none');
    lastUpdateEl.textContent = `Last update: ${formatIndianTimestamp(item.timestamp)}`;
  } catch (e) {
    containerEl.classList.add('d-none');
    lastUpdateEl.textContent = 'Waiting for data…';
  }
}

function calculateWqi(obs) {
  const IDEAL = { ph: 7.0, do: 14.6, turbidity: 0.0, tds: 0.0, nitrate: 0.0, temperature: 25.0 };
  const STANDARD = { ph: 8.5, do: 5.0, turbidity: 5.0, tds: 500.0, nitrate: 45.0, temperature: 30.0 };
  let K = 0;
  for (const k in STANDARD) K += 1 / STANDARD[k];
  K = 1 / K;
  let total_qw = 0;
  let total_w = 0;
  for (const k in STANDARD) {
    if (obs[k] === undefined || obs[k] === null) continue;
    const observed = Number(obs[k]);
    const ideal = IDEAL[k];
    const standard = STANDARD[k];
    const weight = K / standard;
    let qi;
    if (k === 'temperature') {
      qi = Math.abs(observed - ideal) / (standard - ideal) * 100;
    } else {
      qi = (observed - ideal) / (standard - ideal) * 100;
    }
    if (qi < 0) qi = 0;
    total_qw += qi * weight;
    total_w += weight;
  }
  if (total_w === 0) return 0;
  return Math.round((total_qw / total_w) * 100) / 100;
}

function getStatus(wqi) {
  if (wqi <= 25) return { status: 'Excellent', color: 'success' };
  if (wqi <= 50) return { status: 'Good', color: 'primary' };
  if (wqi <= 75) return { status: 'Poor', color: 'warning' };
  if (wqi <= 100) return { status: 'Very Poor', color: 'danger' };
  return { status: 'Unfit for Consumption', color: 'dark' };
}

function renderStats(item) {
  if (!item) {
    statTemp.textContent = '—';
    statPh.textContent = '—';
    statTurbidity.textContent = '—';
    statWqi.textContent = '—';
    badgeWqi.textContent = '—';
    badgeWqi.className = 'badge bg-secondary';
    if (sensorSafetyEl) {
      sensorSafetyEl.textContent = 'Waiting for data from the sensor…';
    }
    return;
  }
  statTemp.textContent = item.temperature_c != null ? Number(item.temperature_c).toFixed(2) : '—';
  statPh.textContent = item.ph != null ? Number(item.ph).toFixed(2) : '—';
  const turb = item.turbidity;
  statTurbidity.textContent = turb != null ? Number(turb).toFixed(2) : '—';
  const obs = {
    ph: item.ph != null ? Number(item.ph) : 7.0,
    do: 14.6,
    turbidity: turb != null ? Number(turb) : 0.0,
    tds: 0.0,
    nitrate: 0.0,
    temperature: item.temperature_c != null ? Number(item.temperature_c) : 25.0
  };
  const wqi = calculateWqi(obs);
  const s = getStatus(wqi);
  statWqi.textContent = wqi.toFixed(2);
  badgeWqi.textContent = s.status;
  badgeWqi.className = `badge bg-${s.color}`;
  statWqi.className = `badge px-4 py-3 stat-value bg-${s.color}`;

  if (sensorSafetyEl) {
    if (wqi <= 25) {
      sensorSafetyEl.textContent = '✅ Safe for daily use.';
    } else if (wqi <= 50) {
      sensorSafetyEl.textContent = '✅ Generally safe, with minor concerns.';
    } else if (wqi <= 75) {
      sensorSafetyEl.textContent = '⚠️ Use with caution. Consider treatment before drinking.';
    } else if (wqi <= 100) {
      sensorSafetyEl.textContent = '❌ Not safe for drinking without proper treatment.';
    } else {
      sensorSafetyEl.textContent = '❌ Not safe for drinking. Water quality is very poor.';
    }
  }

  if (wqiMarkerSensor) {
    const clamped = Math.max(0, Math.min(wqi, 120));
    const position = (clamped / 120) * 100;
    wqiMarkerSensor.style.left = position + '%';
  }

  if (sensorWhyList) {
    sensorWhyList.innerHTML = '';
    const ideal = {
      temperature_c: 25.0,
      ph: 7.0,
      turbidity: 1.0
    };
    const differences = [
      {
        key: 'temperature_c',
        label: 'Temperature',
        score: item.temperature_c != null ? Math.abs(Number(item.temperature_c) - ideal.temperature_c) / 2.0 : 0
      },
      {
        key: 'ph',
        label: 'pH',
        score: item.ph != null ? Math.abs(Number(item.ph) - ideal.ph) : 0
      },
      {
        key: 'turbidity',
        label: 'Turbidity',
        score: item.turbidity != null ? Math.max(0, Number(item.turbidity) - ideal.turbidity) : 0
      }
    ];

    differences.sort((a, b) => b.score - a.score);
    const topIssues = differences.filter(d => d.score > 0.1).slice(0, 3);

    if (topIssues.length === 0) {
      const li = document.createElement('li');
      li.textContent = 'Current sensor readings are close to comfortable levels for clean water.';
      sensorWhyList.appendChild(li);
    } else {
      topIssues.forEach(issue => {
        const li = document.createElement('li');
        if (issue.key === 'temperature_c') {
          li.textContent = 'The water temperature is away from the comfortable range, which can affect how healthy the water feels.';
        } else if (issue.key === 'ph') {
          li.textContent = item.ph > ideal.ph
            ? 'The pH is higher than the ideal level, making the water slightly more basic.'
            : 'The pH is lower than the ideal level, making the water slightly more acidic.';
        } else if (issue.key === 'turbidity') {
          li.textContent = 'The water looks more cloudy (higher turbidity), which can indicate tiny floating particles.';
        }
        sensorWhyList.appendChild(li);
      });
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  fetchLatest();
  setInterval(fetchLatest, 5000);
});

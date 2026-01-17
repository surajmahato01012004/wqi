let CONFIG = null; // configuration loaded from backend
const containerEl = document.getElementById('sensor-container'); // card container for sensor UI
const statTemp = document.getElementById('stat-temp'); // temperature value label
const statPh = document.getElementById('stat-ph'); // pH value label
const statTurbidity = document.getElementById('stat-turbidity'); // turbidity value label
const lastUpdateEl = document.getElementById('last-update'); // text showing last update time
const statWqi = document.getElementById('stat-wqi'); // WQI numeric badge
const badgeWqi = document.getElementById('badge-wqi'); // status text badge
const sensorSafetyEl = document.getElementById('sensor-safety'); // safety message paragraph
const wqiMarkerSensor = document.getElementById('wqi-marker-sensor'); // triangle marker on scale
const sensorWhyList = document.getElementById('sensor-why-list'); // list explaining WQI factors

function formatLocalTimestamp(ts) {
  if (!ts) return '';
  const iso = ts.endsWith('Z') ? ts : ts + 'Z'; // ensure UTC format for Date
  const d = new Date(iso); // parse into Date object
  const fmt = new Intl.DateTimeFormat(undefined, {
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
    const res = await fetch('/api/iot'); // request latest IoT reading
    if (!res.ok) {
      containerEl.classList.add('d-none'); // hide content when no data
      lastUpdateEl.textContent = 'Waiting for data…'; // show placeholder text
      return;
    }
    const item = await res.json(); // parse JSON payload
    await renderStats(item); // render stats from payload
    containerEl.classList.remove('d-none'); // show content
    lastUpdateEl.textContent = `Last update: ${formatLocalTimestamp(item.timestamp)}`; // human readable time
  } catch (e) {
    containerEl.classList.add('d-none'); // hide if request fails
    lastUpdateEl.textContent = 'Waiting for data…'; // show placeholder text
  }
}

async function renderStats(item) {
  if (!item) {
    statTemp.textContent = '—';
    statPh.textContent = '—';
    statTurbidity.textContent = '—';
    statWqi.textContent = '—';
    badgeWqi.textContent = '—';
    badgeWqi.className = 'badge bg-secondary';
    if (sensorSafetyEl) {
      const msg = (CONFIG && CONFIG.wqi && CONFIG.wqi.messages) ? CONFIG.wqi.messages.secondary : 'Waiting for data…';
      sensorSafetyEl.textContent = msg || '';
    }
    return;
  }
  statTemp.textContent = item.temperature_c != null ? Number(item.temperature_c).toFixed(2) : '—';
  statPh.textContent = item.ph != null ? Number(item.ph).toFixed(2) : '—';
  const turb = item.turbidity;
  statTurbidity.textContent = turb != null ? Number(turb).toFixed(2) : '—';
  let wqi = null; // computed WQI result
  let status = '—'; // status text
  let color = 'secondary'; // bootstrap color name
  try {
    const payload = {
      ph: item.ph != null ? Number(item.ph) : undefined,
      turbidity: turb != null ? Number(turb) : undefined,
      temperature: item.temperature_c != null ? Number(item.temperature_c) : undefined
    };
    const res = await fetch('/calculate', { // request backend to compute WQI from sensor values
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      const out = await res.json(); // parse result
      wqi = out.wqi; // numeric score
      status = out.status; // status label text
      color = out.color; // bootstrap color class
    }
  } catch (e) {}
  statWqi.textContent = wqi != null ? Number(wqi).toFixed(2) : '—';
  badgeWqi.textContent = status;
  badgeWqi.className = `badge bg-${color}`;
  statWqi.className = `badge px-4 py-3 stat-value bg-${color}`;

  if (sensorSafetyEl) {
    if (wqi == null) {
      const msg = (CONFIG && CONFIG.wqi && CONFIG.wqi.messages) ? CONFIG.wqi.messages.secondary : 'Waiting for data…';
      sensorSafetyEl.textContent = msg || '';
    } else {
      const messages = (CONFIG && CONFIG.wqi && CONFIG.wqi.messages) ? CONFIG.wqi.messages : null;
      const text = messages ? messages[color] : '';
      sensorSafetyEl.textContent = text || '';
    }
  }

  if (wqiMarkerSensor) {
    const scaleMax = (CONFIG && CONFIG.wqi && CONFIG.wqi.scale_max) ? CONFIG.wqi.scale_max : 120;
    const clamped = wqi != null ? Math.max(0, Math.min(Number(wqi), scaleMax)) : 0; // clamp into scale range
    const position = (clamped / scaleMax) * 100; // compute marker position
    wqiMarkerSensor.style.left = position + '%';
  }

  if (sensorWhyList) {
    sensorWhyList.innerHTML = '';
    const idealCfg = (CONFIG && CONFIG.wqi && CONFIG.wqi.ideal) ? CONFIG.wqi.ideal : { temperature: 25.0, ph: 7.0, turbidity: 0.0 };
    const ideal = {
      temperature_c: idealCfg.temperature,
      ph: idealCfg.ph,
      turbidity: idealCfg.turbidity
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
  (async () => {
    try {
      const res = await fetch('/config'); // load configuration before starting polling
      CONFIG = await res.json(); // parse config JSON
    } catch (e) {
      CONFIG = {}; // fallback to defaults
    }
    fetchLatest(); // get first datapoint
    const interval = (CONFIG && CONFIG.wqi && CONFIG.wqi.poll_interval_ms) ? CONFIG.wqi.poll_interval_ms : 5000; // polling interval ms
    setInterval(fetchLatest, interval); // start automatic polling
  })();
});

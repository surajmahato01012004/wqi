let CONFIG = null; // configuration loaded from the server
let wqiChart = null; // Chart.js instance for the semi-pie
const ctx = document.getElementById('wqiChart').getContext('2d'); // canvas drawing context
function colorHexByBootstrap(name) {
    if (!CONFIG || !CONFIG.colors) return '#343a40'; // default dark if config missing
    return CONFIG.colors[name] || '#343a40'; // lookup hex color by bootstrap name
}
function getSafetyMessageByColor(color) {
    const messages = CONFIG && CONFIG.wqi && CONFIG.wqi.messages ? CONFIG.wqi.messages : null; // safety messages from config
    if (!messages) return '';
    return messages[color] || ''; // message for the current status color
}
async function initConfigAndChart() {
    try {
        const res = await fetch('/config'); // fetch config from backend
        CONFIG = await res.json(); // parse JSON config
    } catch (e) {
        CONFIG = {}; // keep defaults if request fails
    }
    const baseline = CONFIG && CONFIG.wqi && CONFIG.wqi.chart ? CONFIG.wqi.chart.baseline : 150; // total ring size
    const remainderColor = CONFIG && CONFIG.wqi && CONFIG.wqi.chart ? CONFIG.wqi.chart.remainder_color : '#e9ecef'; // background ring color
    const cutoutPercent = CONFIG && CONFIG.wqi && CONFIG.wqi.chart ? CONFIG.wqi.chart.cutout_percent : 60; // hole size in donut
    wqiChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Current Score', 'Remaining'],
            datasets: [{
                data: [0, baseline],
                backgroundColor: [remainderColor, remainderColor],
                borderWidth: 0
            }]
        },
        options: {
            rotation: -90, // start from top
            circumference: 180, // draw half circle
            cutout: cutoutPercent + '%', // inner radius
            plugins: {
                legend: { display: false }, // hide legend
                tooltip: { enabled: false } // disable tooltips
            }
        }
    });
}
initConfigAndChart();

const wqiForm = document.getElementById('wqiForm'); // form element users submit
const wqiBadge = document.getElementById('wqiBadge'); // large numeric badge over chart
const statusBadge = document.getElementById('statusBadge'); // text badge showing status
const safetyMessage = document.getElementById('safetyMessage'); // short guidance text
const wqiMarker = document.getElementById('wqiMarker'); // triangle marker on horizontal scale
const parameterSummary = document.getElementById('parameterSummary'); // summary card grid

const summaryPh = document.getElementById('summaryPh');
const summaryDo = document.getElementById('summaryDo');
const summaryTurbidity = document.getElementById('summaryTurbidity');
const summaryTds = document.getElementById('summaryTds');
const summaryNitrate = document.getElementById('summaryNitrate');
const summaryTemperature = document.getElementById('summaryTemperature');
const wqiWhyList = document.getElementById('wqiWhyList');

function getSafetyMessage(color) {
    return getSafetyMessageByColor(color) || ''; // resolve safety text based on status color
}

function updateScaleMarker(wqi) {
    if (!wqiMarker) return;
    const scaleMax = CONFIG && CONFIG.wqi && CONFIG.wqi.scale_max ? CONFIG.wqi.scale_max : 120; // right end value
    const clamped = Math.max(0, Math.min(wqi, scaleMax)); // clamp WQI into [0, scaleMax]
    const position = (clamped / scaleMax) * 100; // percent from left
    wqiMarker.style.left = position + "%";
}

function updateParameterSummary(values) {
    if (!parameterSummary) return;
    summaryPh.innerText = values.ph.toFixed(2);
    summaryDo.innerText = values.do.toFixed(2);
    summaryTurbidity.innerText = values.turbidity.toFixed(2);
    summaryTds.innerText = values.tds.toFixed(0);
    summaryNitrate.innerText = values.nitrate.toFixed(2);
    summaryTemperature.innerText = values.temperature.toFixed(1);
    parameterSummary.classList.remove("d-none");
}

function updateWhyList(values) {
    if (!wqiWhyList) return;
    wqiWhyList.innerHTML = "";

    const ideal = (CONFIG && CONFIG.wqi && CONFIG.wqi.ideal) ? CONFIG.wqi.ideal : {
        ph: 7.0,
        do: 14.6,
        turbidity: 0.0,
        tds: 0.0,
        nitrate: 0.0,
        temperature: 25.0
    };

    const differences = [
        {
            key: "ph",
            label: "pH",
            score: Math.abs(values.ph - ideal.ph)
        },
        {
            key: "do",
            label: "Dissolved Oxygen",
            score: Math.max(0, ideal.do - values.do)
        },
        {
            key: "turbidity",
            label: "Turbidity",
            score: Math.max(0, values.turbidity - ideal.turbidity)
        },
        {
            key: "tds",
            label: "TDS",
            score: Math.max(0, values.tds - ideal.tds) / 50.0
        },
        {
            key: "nitrate",
            label: "Nitrate",
            score: Math.max(0, values.nitrate - ideal.nitrate) / 2.0
        },
        {
            key: "temperature",
            label: "Temperature",
            score: Math.abs(values.temperature - ideal.temperature) / 2.0
        }
    ];

    differences.sort((a, b) => b.score - a.score);

    const topIssues = differences.filter(d => d.score > 0.1).slice(0, 3);

    if (topIssues.length === 0) {
        const li = document.createElement("li");
        li.textContent = "All measured parameters are close to ideal levels for clean water.";
        wqiWhyList.appendChild(li);
        return;
    }

    topIssues.forEach(issue => {
        const li = document.createElement("li");
        if (issue.key === "ph") {
            li.textContent = values.ph > ideal.ph
                ? "The pH is higher than the ideal level, which can make the water slightly more basic."
                : "The pH is lower than the ideal level, which can make the water slightly more acidic.";
        } else if (issue.key === "do") {
            li.textContent = "Dissolved oxygen is lower than ideal, which can be a sign of stressed water quality.";
        } else if (issue.key === "turbidity") {
            li.textContent = "The water looks more cloudy (higher turbidity), which can indicate suspended particles.";
        } else if (issue.key === "tds") {
            li.textContent = "Total dissolved solids are higher than ideal, meaning more salts and minerals in the water.";
        } else if (issue.key === "nitrate") {
            li.textContent = "Nitrate levels are higher, often linked to runoff from farms or waste.";
        } else if (issue.key === "temperature") {
            li.textContent = "The temperature is away from the comfortable range, which can affect how healthy the water is.";
        }
        wqiWhyList.appendChild(li);
    });
}

wqiForm.addEventListener('submit', async function(e) {
    e.preventDefault(); // stop normal form submission

    const values = {
        ph: parseFloat(document.getElementById('ph').value),
        do: parseFloat(document.getElementById('do').value),
        turbidity: parseFloat(document.getElementById('turbidity').value),
        tds: parseFloat(document.getElementById('tds').value),
        nitrate: parseFloat(document.getElementById('nitrate').value),
        temperature: parseFloat(document.getElementById('temperature').value)
    };

    const data = {
        ph: values.ph,
        do: values.do,
        turbidity: values.turbidity,
        tds: values.tds,
        nitrate: values.nitrate,
        temperature: values.temperature
    };

    try {
        const response = await fetch('/calculate', { // send values to backend to compute WQI
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json(); // read result { wqi, status, color }
        const wqi = result.wqi; // numeric WQI

        wqiBadge.textContent = wqi; // show WQI number
        wqiBadge.className = `badge px-4 py-3 stat-value bg-${result.color}`; // color badge by status

        statusBadge.innerText = result.status; // show status text
        statusBadge.className = `badge fs-5 px-3 py-2 bg-${result.color}`; // match status color

        const colorHex = colorHexByBootstrap(result.color); // resolve hex for chart segment
        const baseline = CONFIG && CONFIG.wqi && CONFIG.wqi.chart ? CONFIG.wqi.chart.baseline : 150; // chart total
        const remainderColor = CONFIG && CONFIG.wqi && CONFIG.wqi.chart ? CONFIG.wqi.chart.remainder_color : '#e9ecef'; // background color

        wqiChart.data.datasets[0].data = [wqi, Math.max(0, baseline - wqi)]; // current vs remaining
        wqiChart.data.datasets[0].backgroundColor = [colorHex, remainderColor]; // apply colors
        wqiChart.update(); // re-render chart

        safetyMessage.textContent = getSafetyMessage(result.color); // update guidance

        updateScaleMarker(wqi);
        updateParameterSummary(values);
        updateWhyList(values);

    } catch (err) {
        console.error(err); // log error to console
        alert("Server error!"); // show simple alert
    }
});

const ctx = document.getElementById('wqiChart').getContext('2d');

let wqiChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
        labels: ['Current Score', 'Remaining'],
        datasets: [{
            data: [0, 150],
            backgroundColor: ['#e9ecef', '#e9ecef'],
            borderWidth: 0
        }]
    },
    options: {
        rotation: -90,
        circumference: 180,
        cutout: '70%',
        plugins: {
            legend: { display: false },
            tooltip: { enabled: false }
        }
    }
});

const wqiForm = document.getElementById('wqiForm');
const wqiBadge = document.getElementById('wqiBadge');
const statusBadge = document.getElementById('statusBadge');
const safetyMessage = document.getElementById('safetyMessage');
const wqiMarker = document.getElementById('wqiMarker');
const parameterSummary = document.getElementById('parameterSummary');

const summaryPh = document.getElementById('summaryPh');
const summaryDo = document.getElementById('summaryDo');
const summaryTurbidity = document.getElementById('summaryTurbidity');
const summaryTds = document.getElementById('summaryTds');
const summaryNitrate = document.getElementById('summaryNitrate');
const summaryTemperature = document.getElementById('summaryTemperature');
const wqiWhyList = document.getElementById('wqiWhyList');

function getRangeColor(wqi) {
    if (wqi <= 25) return '#28a745';      // green
    if (wqi <= 50) return '#0d6efd';      // blue
    if (wqi <= 75) return '#ffc107';      // yellow
    if (wqi <= 100) return '#dc3545';     // red
    return '#343a40';                     // black
}

function getSafetyMessage(wqi) {
    if (wqi <= 25) return "✅ Safe for daily use.";
    if (wqi <= 50) return "✅ Generally safe, with minor concerns.";
    if (wqi <= 75) return "⚠️ Use with caution. Consider treatment before drinking.";
    if (wqi <= 100) return "❌ Not safe for drinking without proper treatment.";
    return "❌ Not safe for drinking. Water quality is very poor.";
}

function updateScaleMarker(wqi) {
    if (!wqiMarker) return;
    const clamped = Math.max(0, Math.min(wqi, 120));
    const position = (clamped / 120) * 100;
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

    const ideal = {
        ph: 7.0,
        do: 14.6,
        turbidity: 1.0,
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
    e.preventDefault();

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
        const response = await fetch('/calculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();
        const wqi = result.wqi;

        wqiBadge.textContent = wqi;

        statusBadge.innerText = result.status;
        statusBadge.className = `badge fs-5 px-3 py-2 bg-${result.color}`;

        const color = getRangeColor(wqi);

        wqiChart.data.datasets[0].data = [wqi, Math.max(0, 150 - wqi)];
        wqiChart.data.datasets[0].backgroundColor = [color, '#e9ecef'];
        wqiChart.update();

        safetyMessage.textContent = getSafetyMessage(wqi);

        updateScaleMarker(wqi);
        updateParameterSummary(values);
        updateWhyList(values);

    } catch (err) {
        console.error(err);
        alert("Server error!");
    }
});

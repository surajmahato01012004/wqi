let map; // Google Map instance
let lastMarker = null; // last highlighted marker for nearest location
let allMarkers = []; // all static markers on map
let CONFIG = null; // configuration loaded from backend

function colorHexFromCategory(color) {
    if (!CONFIG || !CONFIG.colors) return '#343a40'; // default dark if missing
    return CONFIG.colors[color] || '#343a40'; // map bootstrap color name to hex
}

function addMarker(lat, lng, wqi, status, color) {
    if (lastMarker) {
        lastMarker.setMap(null); // remove previous highlight
    }

    const icon = {
        path: google.maps.SymbolPath.CIRCLE, // simple circle symbol
        fillColor: colorHexFromCategory(color), // colored by status
        fillOpacity: 1, // solid fill
        strokeColor: '#ffffff', // white border
        strokeWeight: 2, // border thickness
        scale: 10 // size
    };

    lastMarker = new google.maps.Marker({
        position: { lat, lng }, // marker location
        map, // map instance
        icon // icon style
    });

    const info = new google.maps.InfoWindow({
        content: `
            <div style="min-width:200px">
                <div class="fw-bold mb-1">Nearest Location</div>
                <div>Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}</div>
                <div class="mt-2">WQI: <span class="fw-bold">${wqi}</span></div>
                <div>Status: <span class="badge bg-${color}">${status}</span></div>
            </div>
        `
    });
    info.open(map, lastMarker); // show info popup
}

function addLocationMarker(lat, lng, name, wqi, status, color) {
    const icon = {
        path: google.maps.SymbolPath.CIRCLE, // circle icon for static markers
        fillColor: colorHexFromCategory(color),
        fillOpacity: 1,
        strokeColor: '#ffffff',
        strokeWeight: 2,
        scale: 8
    };
    const marker = new google.maps.Marker({ position: { lat, lng }, map, icon }); // create marker
    const info = new google.maps.InfoWindow({
        content: `
            <div style="min-width:220px">
                <div class="fw-bold mb-1">${name || 'Location'}</div>
                <div>Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}</div>
                <div class="mt-2">WQI: <span class="fw-bold">${wqi ?? '-'}</span></div>
                <div>Status: <span class="badge bg-${color}">${status}</span></div>
            </div>
        `
    });
    marker.addListener('click', () => info.open(map, marker)); // open info when clicked
    allMarkers.push(marker); // keep track of marker
}

async function fetchWqi(lat, lng) {
    const url = `/api/wqi?lat=${lat}&lng=${lng}`; // ask server for nearest location's WQI
    const res = await fetch(url); // call API
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`); // show readable error
    }
    return res.json(); // parse result JSON
}

async function fetchLocations() {
    const res = await fetch('/api/locations'); // get all static/user locations and their WQI
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json(); // parse list
}

async function initMap() {
    try {
        const cfgRes = await fetch('/config'); // load configuration for map defaults
        CONFIG = await cfgRes.json();
    } catch (e) {
        CONFIG = {}; // fallback to defaults
    }
    const center = (CONFIG && CONFIG.map && CONFIG.map.default_center) ? CONFIG.map.default_center : { lat: 20.5937, lng: 78.9629 }; // initial center
    const zoom = (CONFIG && CONFIG.map && CONFIG.map.default_zoom) ? CONFIG.map.default_zoom : 5; // initial zoom
    map = new google.maps.Map(document.getElementById('map'), {
        center, // set center
        zoom, // set zoom level
        mapTypeControl: false, // hide map type selector
        streetViewControl: false // hide street view
    });

    fetchLocations()
        .then(list => {
            list.forEach(item => { // add markers for each location
                addLocationMarker(item.latitude, item.longitude, item.name, item.wqi, item.status, item.color);
            });
        })
        .catch(() => {});

    map.addListener('click', async (e) => { // when user clicks the map
        const lat = e.latLng.lat(); // clicked latitude
        const lng = e.latLng.lng(); // clicked longitude
        try {
            const result = await fetchWqi(lat, lng); // ask server for nearest location data
            addMarker(result.latitude, result.longitude, result.wqi, result.status, result.color); // highlight nearest
            map.panTo({ lat: result.latitude, lng: result.longitude }); // pan to nearest
            const clickZoom = (CONFIG && CONFIG.map && CONFIG.map.click_zoom) ? CONFIG.map.click_zoom : 10; // zoom in
            map.setZoom(clickZoom); // set zoom
        } catch (err) {
            alert(`No data available: ${err.message}`); // show error toast
        }
    });
}

window.initMap = initMap; // Google Maps callback

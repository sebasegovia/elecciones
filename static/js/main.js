// --------------------- Helpers ---------------------
function $(id){ return document.getElementById(id); }
function setTextSafe(id, text){
  const el = $(id);
  if (el) el.textContent = text;
}

// --------------------- Query + Tabla ---------------------
function buildQuery() {
  const qs = new URLSearchParams();
  const get = id => ($(id)?.value || "").trim();

  const fields = [
    "anioEleccion", "tipoRecuento", "tipoEleccion", "categoriaId",
    "distritoId", "seccionProvincialId", "seccionId", "circuitoId", "mesaId"
  ];
  for (const f of fields) {
    const v = get(f);
    if (v) qs.set(f, v);
  }
  return qs;
}

async function consultar() {
  const qs = buildQuery();
  const url = `/api/resultados?${qs.toString()}`;

  const btn = document.getElementById("btnConsultar");
  if (btn){ btn.disabled = true; btn.textContent = "Consultando..."; }
  try {
    const r = await fetch(url);
    const payload = await r.json();
    if (!r.ok) throw new Error(payload.error || "Error de API");

    const data = payload.data || {};
    const positivos = data.valoresTotalizadosPositivos || [];
    const otros = data.valoresTotalizadosOtros || [];

    // Meta (tolerante si se comenta el div#meta)
    const metaText = `Totalizado: ${data.fechaTotalizacion || "-"} | Estado: ${JSON.stringify(data.estadoRecuento || {})}`;
    setTextSafe("meta", metaText);

    // Tabla de positivos
    const tbody = document.getElementById("tbodyPositivos");
    if (tbody){
      tbody.innerHTML = "";
      if (!positivos.length) {
        tbody.innerHTML = `<tr><td colspan="3" class="text-muted">Sin datos</td></tr>`;
      } else {
        for (const x of positivos) {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${x.nombreAgrupacion || "-"}</td>
            <td class="text-end">${x.votos ?? "-"}</td>
            <td class="text-end">${(x.votosPorcentaje ?? 0).toFixed(2)}</td>
          `;
          tbody.appendChild(tr);
        }
      }
    }

    // Otros
    const otrosWrap = document.getElementById("otrosWrap");
    const otrosPre = document.getElementById("otros");
    if (otros && Array.isArray(otros) && otros.length) {
      if (otrosWrap) otrosWrap.classList.remove("d-none");
      if (otrosPre)  otrosPre.textContent = JSON.stringify(otros, null, 2);
    } else {
      if (otrosWrap) otrosWrap.classList.add("d-none");
      if (otrosPre)  otrosPre.textContent = "";
    }

    // Exports
    const q = qs.toString();
    const btnExcel = document.getElementById("btnExcel");
    const btnPDF   = document.getElementById("btnPDF");
    if (btnExcel && btnPDF){
      btnExcel.classList.remove("disabled"); btnPDF.classList.remove("disabled");
      btnExcel.href = `/export/excel?${q}`;
      btnPDF.href   = `/export/pdf?${q}`;
    }

    // Resumen del escrutinio
    const e = data.estadoRecuento;
    const resumenWrap = document.getElementById("resumenWrap");
    if (e) {
      setTextSafe("resumenFecha", data.fechaTotalizacion || "-");
      setTextSafe("resumenElectores", e.cantidadElectores?.toLocaleString("es-AR") || "-");
      setTextSafe("resumenVotantes", e.cantidadVotantes?.toLocaleString("es-AR") || "-");
      setTextSafe("resumenMesasEsperadas", e.mesasEsperadas?.toLocaleString("es-AR") || "-");
      setTextSafe("resumenMesasTotalizadas", e.mesasTotalizadas?.toLocaleString("es-AR") || "-");
      setTextSafe("resumenMesasPorcentaje", (e.mesasTotalizadasPorcentaje ?? 0).toFixed(2));
      setTextSafe("resumenParticipacion", (e.participacionPorcentaje ?? 0).toFixed(2));
      if (resumenWrap) resumenWrap.classList.remove("d-none");
    } else {
      if (resumenWrap) resumenWrap.classList.add("d-none");
    }

  } catch (err) {
    alert(err.message);
  } finally {
    if (btn){ btn.disabled = false; btn.textContent = "Consultar"; }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const b = document.getElementById("btnConsultar");
  if (b){ b.addEventListener("click", consultar); }
});

// --------------------- Leaflet + Choropleth ---------------------
let map, provinciasLayer, provinciasGeo;

function initMap() {
  if (map || !document.getElementById("map")) return;
  map = L.map('map').setView([-38.4, -63.6], 4);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution:'&copy; OpenStreetMap'
  }).addTo(map);
}

async function cargarGeoProvincias() {
  if (provinciasGeo) return provinciasGeo;
  const r = await fetch('/static/geo/provincias.geojson');
  if (!r.ok) throw new Error('No se pudo cargar /static/geo/provincias.geojson');
  provinciasGeo = await r.json();
  return provinciasGeo;
}

function getColor(p) {
  return p >= 50 ? '#084081' :
         p >= 40 ? '#0868ac' :
         p >= 30 ? '#2b8cbe' :
         p >= 20 ? '#4eb3d3' :
         p >= 10 ? '#7bccc4' :
         p >=  5 ? '#a8ddb5' :
         p >   0 ? '#ccebc5' : '#eee';
}

function renderLegend() {
  const legend = document.getElementById("legend");
  if (!legend) return;
  const grades = [0,5,10,20,30,40,50];
  let html = '<div class="card card-body p-2"><div><strong>Leyenda (% votos)</strong></div>';
  for (let i = 0; i < grades.length; i++) {
    const from = grades[i];
    const to = grades[i + 1];
    const c = getColor(from + 0.001);
    html += `<div class="d-flex align-items-center gap-2">
      <span style="display:inline-block;width:18px;height:12px;background:${c};border:1px solid #999"></span>
      <span>${from}${to ? '&ndash;' + to : '+'}</span>
    </div>`;
  }
  html += '</div>';
  legend.innerHTML = html;
}

function styleFeatureFactory(mapaPorc) {
  const filtro = (document.getElementById("distritoId")?.value || "").trim();
  return function(feat) {
    const id = String(feat.properties.id_distrito);
    const p = mapaPorc[id] ?? 0;
    const isOther = filtro && id !== filtro;
    return {
      weight: 1,
      color: '#fff',
      opacity: 1,
      fillOpacity: isOther ? 0.25 : 0.9,
      fillColor: isOther ? '#eee' : getColor(p)
    };
  };
}


function bindTooltipFactory(mapaPorc) {
  return function(feat, layer) {
    const id = String(feat.properties.id_distrito);
    const p = mapaPorc[id] ?? 0;
    const nombre = feat.properties.nombre || `Distrito ${id}`;
    layer.bindTooltip(`${nombre}: ${p.toFixed(2)}%`, { sticky: true });
  };
}

function pintarProvincias(mapaPorc) {
  if (!map || !provinciasGeo) return;
  if (provinciasLayer) provinciasLayer.remove();
  provinciasLayer = L.geoJSON(provinciasGeo, {
    style: styleFeatureFactory(mapaPorc),
    onEachFeature: bindTooltipFactory(mapaPorc)
  }).addTo(map);
  try { map.fitBounds(provinciasLayer.getBounds(), { padding: [20,20] }); } catch(e){}
}

function poblarAgrupaciones(agrupaciones) {
  const sel  = document.getElementById('agrupacionSelect');
  const logo = document.getElementById('logoPreview');
  if (!sel) return;
  sel.innerHTML = '<option value="">— seleccioná —</option>';

  (agrupaciones || []).sort((a,b) => (a.nombreAgrupacion || '').localeCompare(b.nombreAgrupacion || ''));
  for (const a of (agrupaciones || [])) {
    const opt = document.createElement('option');
    opt.value = String(a.idAgrupacion);
    opt.textContent = a.nombreAgrupacion || `Agrupación ${a.idAgrupacion}`;
    if (a.urlLogo) opt.dataset.logo = a.urlLogo;
    sel.appendChild(opt);
  }

  sel.addEventListener('change', () => {
    const o = sel.options[sel.selectedIndex];
    const src = o?.dataset?.logo;
    if (logo){
      if (src) { logo.src = src; logo.style.display = 'inline-block'; }
      else     { logo.style.display = 'none'; }
    }
  });
}

async function consultarMapa() {
  // Batch NACIONAL: eliminamos distritoId para que recorra TODAS las provincias
  const qs = buildQuery();
  qs.delete('distritoId');

  const r = await fetch(`/api/mapa/distritos?${qs.toString()}`);
  const payload = await r.json();
  if (!r.ok) throw new Error(payload.error || 'Error /api/mapa/distritos');

  poblarAgrupaciones(payload.agrupaciones || []);
  return payload.series || [];
}

function construirMapaPorcentaje(series, agrupacionId) {
  const mapa = {}; // { [distritoId]: porcentaje }
  for (const row of series) {
    const d = String(row.distritoId);
    if (!row.ok) { mapa[d] = 0; continue; }
    const match = (row.valoresTotalizadosPositivos || []).find(p => String(p.idAgrupacion) === String(agrupacionId));
    mapa[d] = match ? (+match.votosPorcentaje || 0) : 0;
  }
  return mapa;
}

// Hook al botón "Consultar" para además preparar el mapa
const _oldConsultar = consultar;
async function consultarExtendida() {
  await _oldConsultar();     // tabla, resumen, export, etc.
  initMap();
  await cargarGeoProvincias();
  renderLegend();
  window.__seriesDistritos = await consultarMapa();
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("btnConsultar");
  if (btn) {
    btn.removeEventListener("click", consultar);
    btn.addEventListener("click", consultarExtendida);
  }
  const btnPintar = document.getElementById('btnPintarMapa');
  if (btnPintar){
    btnPintar.addEventListener('click', () => {
      if (!window.__seriesDistritos || !window.__seriesDistritos.length) {
        alert('Primero hacé una consulta.');
        return;
      }
      const sel = document.getElementById('agrupacionSelect');
      const aid = sel?.value?.trim();
      if (!aid) { alert('Elegí una agrupación.'); return; }
      const mapaPorc = construirMapaPorcentaje(window.__seriesDistritos, aid);
      pintarProvincias(mapaPorc);
    });
  }
});

from dotenv import load_dotenv
import os, io, json, datetime as dt
from flask import Flask, render_template, request, jsonify, send_file
import requests
import pandas as pd


# ---------------- Configuración ----------------
load_dotenv()

API_BASE = os.getenv("API_BASE", "https://resultados.mininterior.gob.ar/api")
BEARER_TOKEN = os.getenv("BEARER_TOKEN", "").strip()

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; elecciones-app/1.0)",
    "Accept": "application/json",
}
if BEARER_TOKEN:
    DEFAULT_HEADERS["Authorization"] = f"Bearer {BEARER_TOKEN}"

# PDF engine
PDF_ENGINE = None
try:
    from xhtml2pdf import pisa  # noqa
    PDF_ENGINE = "xhtml2pdf"
except Exception:
    try:
        from weasyprint import HTML  # noqa
        PDF_ENGINE = "weasyprint"
    except Exception:
        PDF_ENGINE = None

# ---------------- App ----------------
app = Flask(__name__)

TIPOS_RECUENTO = [
    {"value": "1", "label": "Provisorio (1)"},
    {"value": "2", "label": "Definitivo (2)"},
]
TIPOS_ELECCION = [
    {"value": "1", "label": "PASO (1)"},
    {"value": "2", "label": "Generales (2)"},
    {"value": "3", "label": "Balotaje (3)"},
]
CATEGORIAS = [
    {"value": 1, "label": "Presidente/a"},
    {"value": 2, "label": "Senador/a Nacional"},
    {"value": 3, "label": "Diputado/a Nacional"},
    {"value": 8, "label": "Parlasur - Distrito Nacional"},
    {"value": 9, "label": "Parlasur - Distrito Regional"},
]
DISTRITOS = [
    {"value": "02", "label": "CABA"},
    {"value": "06", "label": "Buenos Aires"},
    {"value": "10", "label": "Catamarca"},
    {"value": "14", "label": "Córdoba"},
    {"value": "18", "label": "Corrientes"},
    {"value": "22", "label": "Chaco"},
    {"value": "26", "label": "Chubut"},
    {"value": "30", "label": "Entre Ríos"},
    {"value": "34", "label": "Formosa"},
    {"value": "38", "label": "Jujuy"},
    {"value": "42", "label": "La Pampa"},
    {"value": "46", "label": "La Rioja"},
    {"value": "50", "label": "Mendoza"},
    {"value": "54", "label": "Misiones"},
    {"value": "58", "label": "Neuquén"},
    {"value": "62", "label": "Río Negro"},
    {"value": "66", "label": "Salta"},
    {"value": "70", "label": "San Juan"},
    {"value": "74", "label": "San Luis"},
    {"value": "78", "label": "Santa Cruz"},
    {"value": "82", "label": "Santa Fe"},
    {"value": "86", "label": "Santiago del Estero"},
    {"value": "90", "label": "Tucumán"},
    {"value": "94", "label": "Tierra del Fuego"},
]
ANIOS = [str(y) for y in range(2011, dt.datetime.now().year + 1)]


# ---------------- Rutas ----------------
@app.route("/")
def index():
    return render_template(
        "index.html",
        tipos_recuento=TIPOS_RECUENTO,
        tipos_eleccion=TIPOS_ELECCION,
        categorias=CATEGORIAS,
        anios=ANIOS,
        distritos=DISTRITOS,
    )


@app.route("/api/resultados")
def api_resultados():
    params = {k: v for k, v in request.args.items() if v not in (None, "", "null")}
    if "categoriaId" not in params:
        return jsonify({"error": "categoriaId es requerido"}), 400

    try:
        r = requests.get(f"{API_BASE}/resultados/getResultados",
                         params=params,
                         headers=DEFAULT_HEADERS,
                         timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": f"Fallo consultando API: {e}"}), 502

    return jsonify({"query": params, "data": r.json()})


@app.route("/api/mapa/distritos")
def api_mapa_distritos():
    base_params = {k: v for k, v in request.args.items() if v not in (None, "", "null")}
    if "categoriaId" not in base_params:
        return jsonify({"error": "categoriaId es requerido"}), 400

    out = []
    agrup_index = {}
    for d in (x["value"] for x in DISTRITOS):
        params = dict(base_params)
        params["distritoId"] = str(d)
        try:
            r = requests.get(f"{API_BASE}/resultados/getResultados",
                             params=params,
                             headers=DEFAULT_HEADERS,
                             timeout=20)
            r.raise_for_status()
            data = r.json() or {}
            positivos = data.get("valoresTotalizadosPositivos") or []
            for p in positivos:
                aid = p.get("idAgrupacion")
                if aid and aid not in agrup_index:
                    agrup_index[aid] = {
                        "idAgrupacion": aid,
                        "nombreAgrupacion": p.get("nombreAgrupacion"),
                        "urlLogo": p.get("urlLogo"),
                    }
            out.append({"distritoId": d, "ok": True,
                        "valoresTotalizadosPositivos": positivos})
        except Exception as e:
            out.append({"distritoId": d, "ok": False, "error": str(e),
                        "valoresTotalizadosPositivos": []})

    return jsonify({"series": out, "agrupaciones": list(agrup_index.values())})


def _armar_dataframes(data_json):
    val = data_json.get("valoresTotalizadosPositivos") or []
    otros = data_json.get("valoresTotalizadosOtros") or []
    df_positivos = pd.DataFrame(val)
    df_otros = pd.DataFrame(otros)
    return df_positivos, df_otros


@app.route("/export/excel")
def export_excel():
    qs = request.query_string.decode()
    prox = requests.get(request.host_url.rstrip("/") + "/api/resultados?" + qs, timeout=30)
    prox.raise_for_status()
    data = prox.json().get("data", {})
    df_pos, df_otros = _armar_dataframes(data)

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_pos.to_excel(writer, index=False, sheet_name="Positivos")
        if not df_otros.empty:
            df_otros.to_excel(writer, index=False, sheet_name="Otros")

    out.seek(0)
    return send_file(out,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True,
                     download_name="resultados.xlsx")


@app.route("/export/pdf")
def export_pdf():
    qs = request.query_string.decode()
    prox = requests.get(request.host_url.rstrip("/") + "/api/resultados?" + qs, timeout=30)
    prox.raise_for_status()
    data = prox.json().get("data", {})
    df_pos, df_otros = _armar_dataframes(data)

    html = render_template("pdf.html",
                           fecha=data.get("fechaTotalizacion"),
                           estado=data.get("estadoRecuento"),
                           df_pos=df_pos.fillna(""),
                           df_otros=df_otros.fillna(""),
                           query=data)

    if PDF_ENGINE == "xhtml2pdf":
        pdf_io = io.BytesIO()
        pisa.CreatePDF(html, dest=pdf_io)  # type: ignore
        pdf_io.seek(0)
    elif PDF_ENGINE == "weasyprint":
        pdf_io = io.BytesIO()
        HTML(string=html, base_url=request.host_url).write_pdf(pdf_io)
        pdf_io.seek(0)
    else:
        return "No hay motor de PDF disponible", 500

    return send_file(pdf_io, mimetype="application/pdf",
                     as_attachment=True,
                     download_name="resultados.pdf")


@app.route("/ping")
def ping():
    return jsonify({"pong": True})


@app.route("/__diag")
def diag():
    return jsonify({
        "api_base": API_BASE,
        "bearer_set": bool(BEARER_TOKEN),
        "cwd": os.getcwd(),
        "python": os.sys.version,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))







# Ejemplo de ruta para obtener secciones provinciales
@app.route('/api/filtros/secciones_provinciales')
def get_secciones_provinciales():
    distrito_id = request.args.get('distritoId')
    if not distrito_id:
        return jsonify({"error": "Falta distritoId"}), 400

    # Consulta a la API de elecciones para obtener las secciones provinciales
    # Ejemplo: https://apis.datos.gob.ar/georef/api/secciones_provinciales?distritoId=X
    url = f"https://apis.datos.gob.ar/georef/api/secciones_provinciales?distritoId={distrito_id}"
    response = requests.get(url)

    if response.ok:
        return jsonify(response.json())
    else:
        return jsonify({"error": "No se pudieron obtener las secciones provinciales"}), 500

# Rutas similares para secciones, circuitos y mesas
@app.route('/api/filtros/secciones')
def get_secciones():
    seccion_provincial_id = request.args.get('seccionProvincialId')
    if not seccion_provincial_id:
        return jsonify({"error": "Falta seccionProvincialId"}), 400

    url = f"https://apis.datos.gob.ar/georef/api/secciones?seccionProvincialId={seccion_provincial_id}"
    response = requests.get(url)

    if response.ok:
        return jsonify(response.json())
    else:
        return jsonify({"error": "No se pudieron obtener las secciones"}), 500

@app.route('/api/filtros/circuitos')
def get_circuitos():
    seccion_id = request.args.get('seccionId')
    if not seccion_id:
        return jsonify({"error": "Falta seccionId"}), 400

    url = f"https://apis.datos.gob.ar/georef/api/circuitos?seccionId={seccion_id}"
    response = requests.get(url)

    if response.ok:
        return jsonify(response.json())
    else:
        return jsonify({"error": "No se pudieron obtener los circuitos"}), 500

@app.route('/api/filtros/mesas')
def get_mesas():
    circuito_id = request.args.get('circuitoId')
    if not circuito_id:
        return jsonify({"error": "Falta circuitoId"}), 400

    url = f"https://apis.datos.gob.ar/georef/api/mesas?circuitoId={circuito_id}"
    response = requests.get(url)

    if response.ok:
        return jsonify(response.json())
    else:
        return jsonify({"error": "No se pudieron obtener las mesas"}), 500

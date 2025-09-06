import io
import os
import datetime as dt
import pandas as pd
import requests

from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv

# -------------------------------------------------------------------
# Motor de PDF: preferimos xhtml2pdf (sin deps nativas en Windows).
# Si existe WeasyPrint y está correctamente instalado con sus libs,
# lo usamos como fallback (mejor soporte CSS).
# -------------------------------------------------------------------
PDF_ENGINE = None
try:
    from xhtml2pdf import pisa  # noqa: F401
    PDF_ENGINE = "xhtml2pdf"
except Exception:
    try:
        from weasyprint import HTML  # noqa: F401
        PDF_ENGINE = "weasyprint"
    except Exception:
        PDF_ENGINE = None

# -------------------------------------------------------------------
# Configuración
# -------------------------------------------------------------------
load_dotenv()
API_BASE = os.getenv("API_BASE", "https://resultados.mininterior.gob.ar/api")

app = Flask(__name__)

# Catálogos básicos (pueden reemplazarse por listas dinámicas si conseguís endpoints)
TIPOS_RECUENTO = [
    {"value": "1", "label": "Provisorio (1)"},
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

# Nuevo: distritos (IDs oficiales)
DISTRITOS = [
    {"value": "1", "label": "CABA"},
    {"value": "2", "label": "Buenos Aires"},
    {"value": "3", "label": "Catamarca"},
    {"value": "4", "label": "Córdoba"},
    {"value": "5", "label": "Corrientes"},
    {"value": "6", "label": "Chaco"},
    {"value": "7", "label": "Chubut"},
    {"value": "8", "label": "Entre Ríos"},
    {"value": "9", "label": "Formosa"},
    {"value": "10", "label": "Jujuy"},
    {"value": "11", "label": "La Pampa"},
    {"value": "12", "label": "La Rioja"},
    {"value": "13", "label": "Mendoza"},
    {"value": "14", "label": "Misiones"},
    {"value": "15", "label": "Neuquén"},
    {"value": "16", "label": "Río Negro"},
    {"value": "17", "label": "Salta"},
    {"value": "18", "label": "San Juan"},
    {"value": "19", "label": "San Luis"},
    {"value": "20", "label": "Santa Cruz"},
    {"value": "21", "label": "Santa Fe"},
    {"value": "22", "label": "Santiago del Estero"},
    {"value": "23", "label": "Tucumán"},
    {"value": "24", "label": "Tierra del Fuego A.I.A.S."},
]

ANIOS = [str(y) for y in range(2011, dt.datetime.now().year + 1)]


# -------------------------------------------------------------------
# Home
# -------------------------------------------------------------------
@app.route("/")
def index():
    return render_template(
    "index.html",
    tipos_recuento=TIPOS_RECUENTO,
    tipos_eleccion=TIPOS_ELECCION,
    categorias=CATEGORIAS,
    anios=ANIOS,
    distritos=DISTRITOS,   # <-- nuevo
)


# -------------------------------------------------------------------
# Proxy hacia la API oficial (evita CORS y permite validar params)
# -------------------------------------------------------------------
@app.route("/api/resultados")
def api_resultados():
    params = {
        "anioEleccion": request.args.get("anioEleccion"),
        "tipoRecuento": request.args.get("tipoRecuento"),
        "tipoEleccion": request.args.get("tipoEleccion"),
        "categoriaId": request.args.get("categoriaId"),
        "distritoId": request.args.get("distritoId"),
        "seccionProvincialId": request.args.get("seccionProvincialId"),
        "seccionId": request.args.get("seccionId"),
        "circuitoId": request.args.get("circuitoId"),
        "mesaId": request.args.get("mesaId"),
    }
    # Limpia vacíos
    params = {k: v for k, v in params.items() if v not in (None, "", "null")}

    # Validación mínima requerida por el swagger
    if "categoriaId" not in params:
        return jsonify({"error": "categoriaId es requerido"}), 400

    try:
        r = requests.get(f"{API_BASE}/resultados/getResultados", params=params, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": f"Fallo consultando API: {e}"}), 502

    data = r.json()
    return jsonify({"query": params, "data": data})




# -------------------------------------------------------------------
# Batch por distrito para mapa (coroplético nacional por provincia)
# -------------------------------------------------------------------
@app.route("/api/mapa/distritos")
def api_mapa_distritos():
    # Reutilizamos los mismos parámetros que ya usás:
    base_params = {
        "anioEleccion": request.args.get("anioEleccion"),
        "tipoRecuento": request.args.get("tipoRecuento"),
        "tipoEleccion": request.args.get("tipoEleccion"),
        "categoriaId": request.args.get("categoriaId"),
    }
    # Limpia vacíos
    base_params = {k: v for k, v in base_params.items() if v not in (None, "", "null")}
    if "categoriaId" not in base_params:
        return jsonify({"error": "categoriaId es requerido"}), 400

    # Si te pasan un distritoId, podrías hacer drill-down a secciones (extensión futura).
    # Por ahora, si viene distritoId lo ignoramos para mantener un coroplético nacional.
    # (Podés quitar este 'pop' y cambiar el flujo si querés otro comportamiento.)
    base_params.pop("distritoId", None)

    out = []
    agrup_index = {}  # idAgrupacion -> {id, nombre, urlLogo}
    for d in (x["value"] for x in DISTRITOS):
        params = dict(base_params)
        params["distritoId"] = str(d)
        try:
            r = requests.get(f"{API_BASE}/resultados/getResultados", params=params, timeout=20)
            r.raise_for_status()
        except requests.RequestException as e:
            # Si falla uno, seguimos, pero marcamos error vacío para ese distrito
            out.append({
                "distritoId": str(d),
                "ok": False,
                "error": str(e),
                "valoresTotalizadosPositivos": []
            })
            continue

        data = r.json() or {}
        positivos = data.get("valoresTotalizadosPositivos") or []

        # Indexamos logos/nombres una sola vez (para el selector)
        for p in positivos:
            aid = p.get("idAgrupacion")
            if aid is not None and aid not in agrup_index:
                agrup_index[aid] = {
                    "idAgrupacion": aid,
                    "nombreAgrupacion": p.get("nombreAgrupacion"),
                    "urlLogo": p.get("urlLogo")
                }

        out.append({
            "distritoId": str(d),
            "ok": True,
            "valoresTotalizadosPositivos": positivos
        })

    agrupaciones = list(agrup_index.values())
    return jsonify({"series": out, "agrupaciones": agrupaciones})





# -------------------------------------------------------------------
# Normalización para exportar (DataFrames)
# -------------------------------------------------------------------
def _armar_dataframes(data_json):
    """
    Convierte la respuesta a dos DataFrames:
    - df_positivos: valores por agrupación (id, nombre, votos, %)
    - df_otros: blancos/nulos/impugnados/etc. si vienen
    """
    val = data_json.get("valoresTotalizadosPositivos") or []
    otros = data_json.get("valoresTotalizadosOtros") or []

    df_positivos = pd.DataFrame([
        {
            "idAgrupacion": x.get("idAgrupacion"),
            "idAgrupacionTelegrama": x.get("idAgrupacionTelegrama"),
            "nombreAgrupacion": x.get("nombreAgrupacion"),
            "votos": x.get("votos"),
            "votosPorcentaje": x.get("votosPorcentaje"),
            "urlLogo": x.get("urlLogo"),
        }
        for x in val
    ])

    df_otros = pd.DataFrame(otros)
    return df_positivos, df_otros


# -------------------------------------------------------------------
# Exportar a Excel (xlsx)
# -------------------------------------------------------------------
@app.route("/export/excel")
def export_excel():
    # Repetimos la consulta para exportar exactamente lo que se ve
    qs = request.query_string.decode()
    prox = requests.get(request.host_url.rstrip("/") + "/api/resultados?" + qs, timeout=30)
    prox.raise_for_status()
    payload = prox.json()
    data = payload.get("data", {})

    df_pos, df_otros = _armar_dataframes(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_pos.to_excel(writer, index=False, sheet_name="Positivos")
        if not df_otros.empty:
            df_otros.to_excel(writer, index=False, sheet_name="Otros")

    output.seek(0)
    filename = f"resultados_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


# -------------------------------------------------------------------
# Exportar a PDF (xhtml2pdf por defecto; WeasyPrint si está disponible)
# -------------------------------------------------------------------
@app.route("/export/pdf")
def export_pdf():
    qs = request.query_string.decode()
    prox = requests.get(request.host_url.rstrip("/") + "/api/resultados?" + qs, timeout=30)
    prox.raise_for_status()
    payload = prox.json()
    data = payload.get("data", {})

    df_pos, df_otros = _armar_dataframes(data)

    html = render_template(
        "pdf.html",
        fecha=data.get("fechaTotalizacion"),
        estado=data.get("estadoRecuento"),
        df_pos=df_pos.fillna(""),
        df_otros=df_otros.fillna(""),
        query=payload.get("query", {})
    )

    if PDF_ENGINE == "xhtml2pdf":
        # Generar PDF con xhtml2pdf (sin dependencias nativas)
        pdf_io = io.BytesIO()
        result = pisa.CreatePDF(html, dest=pdf_io)  # type: ignore[name-defined]
        if result.err:
            return f"Error generando PDF (xhtml2pdf): {result.err}", 500
        pdf_io.seek(0)
    elif PDF_ENGINE == "weasyprint":
        # Generar PDF con WeasyPrint si está todo instalado
        from weasyprint import HTML  # import local para evitar errores de import global
        pdf_io = io.BytesIO()
        HTML(string=html, base_url=request.host_url).write_pdf(pdf_io)
        pdf_io.seek(0)
    else:
        return "No hay motor de PDF disponible. Instala xhtml2pdf o configura WeasyPrint con sus dependencias.", 500

    filename = f"resultados_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_io, mimetype="application/pdf", as_attachment=True, download_name=filename)


# -------------------------------------------------------------------
# Entry point local
# -------------------------------------------------------------------
if __name__ == "__main__":
    # Modo desarrollo
    app.run(debug=True)

#!/usr/bin/env python3
# Genera static/geo/provincias.geojson con contornos oficiales (Georef/IGN)
# y agrega properties.id_distrito = int(id) → (2, 6, 10, …, 94)

import json, os, sys, urllib.request, urllib.error, tempfile, shutil

OUT = os.environ.get("OUT", "static/geo/provincias.geojson")

# ✅ Ruta “base completa” (la correcta para GeoJSON con geometrías):
SRC = "https://apis.datos.gob.ar/georef/api/provincias.geojson"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3.x (elecciones)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()

def main():
    print("Descargando:", SRC)
    try:
        raw = fetch(SRC)
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP {e.code} - {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        gj = json.loads(raw.decode("utf-8"))
    except Exception as e:
        print(f"[ERROR] No se pudo parsear JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if gj.get("type") != "FeatureCollection":
        print("[ERROR] Respuesta inesperada (no FeatureCollection).", file=sys.stderr)
        sys.exit(1)

    feats = gj.get("features", [])
    print("features:", len(feats))
    if not (23 <= len(feats) <= 25):
        print("[ERROR] Cantidad de features inesperada; no sobreescribo.", file=sys.stderr)
        sys.exit(2)

    # Agrego id_distrito = int(id)
    for f in feats:
        props = f.setdefault("properties", {})
        pid = props.get("id") or props.get("provincia", {}).get("id")
        if not pid:
            print("[ERROR] Falta properties.id", file=sys.stderr)
            sys.exit(3)
        props["id_distrito"] = int(pid)
        if "nombre" not in props and "provincia" in props:
            props["nombre"] = props["provincia"]["nombre"]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".geojson")
    try:
        with open(tmp.name, "w", encoding="utf-8") as f:
            json.dump(gj, f, ensure_ascii=False)
        shutil.move(tmp.name, OUT)
    finally:
        try: os.unlink(tmp.name)
        except: pass

    print("OK →", OUT)

if __name__ == "__main__":
    main()


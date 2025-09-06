#!/usr/bin/env python3
# make_provincias_ign_v2.py
# Descarga provincias (Georef/IGN) en GeoJSON y agrega properties.id_distrito = int(id).
# Solo sobreescribe si hay 23-25 features. Imprime diagnóstico útil si falla.

import json, os, sys, urllib.request, urllib.error, tempfile, shutil

OUT = os.environ.get("OUT", "static/geo/provincias.geojson")
URL = "https://apis.datos.gob.ar/georef/api/provincias?campos=id,nombre&formato=geojson&max=200"

def fetch(url):
  req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3.x (elecciones)"})
  with urllib.request.urlopen(req, timeout=60) as resp:
    return resp.read()

def main():
  print("Descargando:", URL)
  try:
    raw = fetch(URL)
  except urllib.error.HTTPError as e:
    print(f"[ERROR] HTTP {e.code} - {e.reason}", file=sys.stderr)
    print("[SUGERENCIA] Abrí la URL en el navegador y guardá el archivo manualmente.", file=sys.stderr)
    sys.exit(1)
  except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
    print("[SUGERENCIA] Revisá conectividad/PROXY o probá descargar manualmente.", file=sys.stderr)
    sys.exit(1)

  try:
    gj = json.loads(raw.decode("utf-8"))
  except Exception as e:
    print(f"[ERROR] No se pudo parsear JSON: {e}", file=sys.stderr)
    print("Primeros 300 bytes:", raw[:300], file=sys.stderr)
    sys.exit(1)

  if gj.get("type") != "FeatureCollection":
    print("[ERROR] Respuesta inesperada (no FeatureCollection).", file=sys.stderr)
    sys.exit(1)

  feats = gj.get("features", [])
  print("features:", len(feats))
  if not feats:
    print("[ERROR] 0 features. No sobreescribo OUT.", file=sys.stderr)
    sys.exit(2)

  for f in feats:
    props = f.setdefault("properties", {})
    pid = props.get("id") or props.get("provincia", {}).get("id")
    if pid is None:
      print("[ERROR] Falta properties.id en algún feature.", file=sys.stderr)
      sys.exit(3)
    try:
      props["id_distrito"] = int(pid)  # → 2, 6, 10, …, 94
    except Exception as e:
      print(f"[ERROR] No se pudo convertir id='{pid}' a int.", file=sys.stderr)
      sys.exit(4)
    if "nombre" not in props and "provincia" in props:
      props["nombre"] = props["provincia"].get("nombre")

  # Guardar de forma segura
  os.makedirs(os.path.dirname(OUT), exist_ok=True)
  tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".geojson")
  try:
    with open(tmp.name, "w", encoding="utf-8") as f:
      json.dump(gj, f, ensure_ascii=False)
    shutil.move(tmp.name, OUT)
  finally:
    try:
      os.unlink(tmp.name)
    except Exception:
      pass
  print("OK →", OUT)

if __name__ == "__main__":
  main()

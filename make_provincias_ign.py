#!/usr/bin/env python3
# Genera /static/geo/provincias.geojson con contornos oficiales (IGN),
# y agrega properties.id_distrito = int(id) para mapear a (2,6,10,...,94).
#
# Requiere Internet. Dos métodos:
#
# A) API Georef (basada en IGN)
#    - Fuente: https://apis.datos.gob.ar/georef/  (docs)
#    - Descarga directa (GeoJSON con geometría):
#      https://apis.datos.gob.ar/georef/api/provincias?campos=id,nombre,geometria&formato=geojson&max=100
#
# B) WFS del IGN (GeoServer)
#    - GetCapabilities: http://wms.ign.gob.ar/geoserver/ows?service=wfs&version=2.0.0&request=GetCapabilities
#    - Requiere identificar el nombre de la capa de provincias en el capabilities (typeName)
#      y ejecutar una petición GetFeature con outputFormat=application/json.
#
# Por simplicidad y estabilidad, se usa el método A por defecto.

#!/usr/bin/env python3
# Genera static/geo/provincias.geojson con contornos oficiales (Georef/IGN)
# y agrega properties.id_distrito = int(id) → (2, 6, 10, …, 94)

#!/usr/bin/env python3
# Genera static/geo/provincias.geojson con contornos oficiales (Georef/IGN)
# y agrega properties.id_distrito = int(id) → (2, 6, 10, …, 94)

import json, os, sys, urllib.request, urllib.error

OUT = os.environ.get("OUT", "static/geo/provincias.geojson")

# Fuente principal (Georef). Con formato=geojson la geometría ya viene incluida.
SRC_PRIMARY = (
    "https://apis.datos.gob.ar/georef/api/provincias"
    "?campos=id,nombre,geometria&formato=geojson&max=30"
)

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3.x (elecciones)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()

def load_geojson(url):
    raw = fetch(url)
    gj = json.loads(raw.decode("utf-8"))
    if gj.get("type") != "FeatureCollection":
        raise RuntimeError("Respuesta inesperada: no es FeatureCollection")
    return gj

def attach_ids(gj):
    for feat in gj.get("features", []):
        props = feat.setdefault("properties", {})
        pid = props.get("id") or props.get("provincia", {}).get("id")
        if pid is None:
            raise RuntimeError("No se encontró 'id' en properties")
        props["id_distrito"] = int(pid)  # 2, 6, 10, …, 94
        if "nombre" not in props and "provincia" in props:
            props["nombre"] = props["provincia"].get("nombre")

def main():
    gj = load_geojson(SRC_PRIMARY)
    attach_ids(gj)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False)
    print(f"OK → {OUT}")

if __name__ == "__main__":
    main()

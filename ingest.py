
from pathlib import Path
import pandas as pd
import argparse, json, re, unicodedata

MASTER = [
    "source","source_id","url","observation_date","currency","price",
    "surface_total_m2","surface_covered_m2","property_type","condition",
    "rooms","bedrooms","bathrooms","address","province","municipality",
    "locality","neighborhood","title"
]

ALIASES = {
    "source": ["source","fuente","portal","origen"],
    "source_id": ["source_id","id","id_aviso","codigo","codigo_aviso","publication_id"],
    "url": ["url","link","enlace","publication_url"],
    "observation_date": ["observation_date","fecha","fecha_observacion","fecha_relevamiento"],
    "currency": ["currency","moneda"],
    "price": ["price","precio","precio_publicado","valor"],
    "surface_total_m2": ["surface_total_m2","superficie_total","sup_total","m2_total","metros_totales"],
    "surface_covered_m2": ["surface_covered_m2","superficie_cubierta","sup_cubierta","m2_cubiertos"],
    "property_type": ["property_type","tipo_propiedad","tipo","inmueble"],
    "condition": ["condition","estado_unidad","estado","condicion","antiguedad_estado"],
    "rooms": ["rooms","ambientes","cant_ambientes"],
    "bedrooms": ["bedrooms","dormitorios","habitaciones"],
    "bathrooms": ["bathrooms","banos","baños"],
    "address": ["address","direccion","dirección","domicilio"],
    "province": ["province","provincia","jurisdiccion","jurisdicción"],
    "municipality": ["municipality","municipio","partido"],
    "locality": ["locality","localidad","ciudad"],
    "neighborhood": ["neighborhood","barrio"],
    "title": ["title","titulo","título","descripcion_corta"]
}

def norm(s):
    s = str(s).strip().lower()
    s = ''.join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+","_",s).strip("_")

def read_table(path, sheet=0):
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".csv":
        try:
            return pd.read_csv(p)
        except UnicodeDecodeError:
            return pd.read_csv(p, encoding="latin1")
    if ext in {".xlsx",".xlsm"}:
        return pd.read_excel(p, sheet_name=sheet, engine="openpyxl")
    if ext == ".xls":
        return pd.read_excel(p, sheet_name=sheet)
    raise ValueError(f"Formato no soportado: {ext}")

def map_columns(df, explicit=None):
    explicit = explicit or {}
    original = {norm(c): c for c in df.columns}
    rename = {}
    for target in MASTER:
        if target in explicit and explicit[target] in df.columns:
            rename[explicit[target]] = target
            continue
        for alias in ALIASES[target]:
            key = norm(alias)
            if key in original:
                rename[original[key]] = target
                break
    out = df.rename(columns=rename).copy()
    for c in MASTER:
        if c not in out.columns:
            out[c] = pd.NA
    return out[MASTER], rename

def clean(df, default_source=None, observation_date=None):
    x = df.copy()
    if default_source:
        x["source"] = x["source"].fillna(default_source)
    if observation_date:
        x["observation_date"] = x["observation_date"].fillna(observation_date)

    for c in ["price","surface_total_m2","surface_covered_m2","rooms","bedrooms","bathrooms"]:
        x[c] = pd.to_numeric(
            x[c].astype(str).str.replace(r"[^0-9,.\-]","",regex=True)
                .str.replace(".","",regex=False).str.replace(",",".",regex=False),
            errors="coerce"
        )

    x["currency"] = x["currency"].astype("string").str.upper().str.strip()
    x["currency"] = x["currency"].replace({"U$S":"USD","US$":"USD","DOLARES":"USD","DÓLARES":"USD"})
    x["observation_date"] = pd.to_datetime(x["observation_date"], errors="coerce").dt.date.astype("string")
    return x

def classify(x):
    reasons = []
    status = []
    for _, r in x.iterrows():
        rr = []
        if pd.isna(r["source"]) or str(r["source"]).strip() == "": rr.append("missing_source")
        if (pd.isna(r["source_id"]) or str(r["source_id"]).strip()=="") and (pd.isna(r["url"]) or str(r["url"]).strip()==""):
            rr.append("missing_source_id_or_url")
        if pd.isna(r["price"]) or r["price"] <= 0: rr.append("invalid_price")
        if pd.isna(r["surface_total_m2"]) or r["surface_total_m2"] <= 0: rr.append("invalid_surface_total")
        if pd.isna(r["observation_date"]) or str(r["observation_date"])=="<NA>": rr.append("missing_observation_date")
        if pd.isna(r["province"]) or str(r["province"]).strip()=="": rr.append("missing_province")
        reasons.append("|".join(rr))
        status.append("valid" if not rr else "review")
    x["ingest_status"] = status
    x["ingest_reason"] = reasons
    return x

def run(input_path, output_dir, source=None, date=None, sheet=0, mapping=None):
    raw = read_table(input_path, sheet)
    mapped, used = map_columns(raw, mapping)
    cleaned = clean(mapped, source, date)
    audit = classify(cleaned)

    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    stem = Path(input_path).stem
    audit.to_csv(out/f"{stem}_ingest_audit.csv", index=False)
    audit[audit["ingest_status"]=="valid"][MASTER].to_csv(out/f"{stem}_standardized.csv", index=False)

    report = {
        "input": str(input_path),
        "rows_read": int(len(raw)),
        "rows_valid": int((audit["ingest_status"]=="valid").sum()),
        "rows_review": int((audit["ingest_status"]=="review").sum()),
        "mapped_columns": used
    }
    (out/f"{stem}_ingest_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Ingestor del Índice Federal del Precio de Publicación del m²")
    ap.add_argument("input")
    ap.add_argument("--output", default="output")
    ap.add_argument("--source")
    ap.add_argument("--date")
    ap.add_argument("--sheet", default=0)
    args = ap.parse_args()
    print(json.dumps(run(args.input,args.output,args.source,args.date,args.sheet), ensure_ascii=False, indent=2))


from pathlib import Path
import pandas as pd
import numpy as np
import hashlib, re, unicodedata, argparse, json
from ingest import run as ingest_run

def txt(v):
    if pd.isna(v): return ""
    s=str(v).strip().lower()
    s=''.join(c for c in unicodedata.normalize("NFD",s) if unicodedata.category(c)!="Mn")
    return re.sub(r"\s+"," ",s)

def fingerprint(r):
    # Conservative persistent identity: source ID wins; otherwise property characteristics.
    if txt(r.get("source_id")):
        base=f'{txt(r.get("source"))}|{txt(r.get("source_id"))}'
    else:
        base="|".join([
            txt(r.get("province")),txt(r.get("municipality")),txt(r.get("locality")),
            txt(r.get("neighborhood")),txt(r.get("address")),
            str(round(float(r["surface_total_m2"]),1)) if pd.notna(r.get("surface_total_m2")) else "",
            str(int(r["rooms"])) if pd.notna(r.get("rooms")) else ""
        ])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]

def economic_validation(df):
    x=df.copy()
    x["price_usd"]=np.where(x["currency"].eq("USD"),x["price"],np.nan)
    x["usd_m2"]=x["price_usd"]/x["surface_total_m2"]
    x["quality_status"]="valid"
    x["quality_reason"]=""
    rules = [
        (x["currency"].ne("USD"),"non_usd_without_traceable_fx"),
        (x["surface_total_m2"].lt(10) | x["surface_total_m2"].gt(2000),"implausible_surface"),
        (x["usd_m2"].lt(300) | x["usd_m2"].gt(15000),"usd_m2_review")
    ]
    for mask, reason in rules:
        idx=mask.fillna(False)
        x.loc[idx,"quality_status"]="review"
        x.loc[idx,"quality_reason"]=x.loc[idx,"quality_reason"].where(
            x.loc[idx,"quality_reason"].eq(""), x.loc[idx,"quality_reason"]+"|"
        )+reason
    return x

def cross_source_key(r):
    # Fuzzy-lite key: deliberately conservative; potential duplicates are reviewed.
    vals=[
        txt(r.get("province")),txt(r.get("municipality")),txt(r.get("locality")),
        txt(r.get("neighborhood")),txt(r.get("address")),
        str(round(float(r["surface_total_m2"]))) if pd.notna(r.get("surface_total_m2")) else "",
        str(int(r["rooms"])) if pd.notna(r.get("rooms")) else ""
    ]
    return "|".join(vals)

def build(input_path, workdir, source=None, date=None):
    work=Path(workdir); work.mkdir(parents=True,exist_ok=True)
    ingest_dir=work/"ingest"; ingest_dir.mkdir(exist_ok=True)
    rep=ingest_run(input_path, ingest_dir, source, date)
    std=ingest_dir/(Path(input_path).stem+"_standardized.csv")
    x=pd.read_csv(std)
    x=economic_validation(x)
    x["property_id"]=x.apply(fingerprint,axis=1)
    x["cross_source_key"]=x.apply(cross_source_key,axis=1)

    # Exact same-source observations
    x["duplicate_same_source"]=x.duplicated(["source","source_id","observation_date"],keep="first")
    # Cross-source candidates are flagged, not silently deleted.
    counts=x.groupby(["cross_source_key","observation_date"])["source"].transform("nunique")
    x["duplicate_cross_source_candidate"]=counts.gt(1)

    rejected=x[(x["quality_status"]!="valid") | x["duplicate_same_source"]].copy()
    valid=x[(x["quality_status"]=="valid") & ~x["duplicate_same_source"]].copy()

    observations_path=work/"observations.csv"
    if observations_path.exists():
        old=pd.read_csv(observations_path)
        observations=pd.concat([old,valid],ignore_index=True)
        observations=observations.drop_duplicates(["source","source_id","observation_date"],keep="last")
    else:
        observations=valid.copy()
    observations.to_csv(observations_path,index=False)

    # Master: latest observation per source listing; persistent historical observations remain separate.
    obs=observations.copy()
    obs["observation_date"]=pd.to_datetime(obs["observation_date"])
    master=obs.sort_values("observation_date").drop_duplicates(["source","source_id"],keep="last")
    first=obs.groupby(["source","source_id"])["observation_date"].min().rename("first_observed")
    last=obs.groupby(["source","source_id"])["observation_date"].max().rename("last_observed")
    master=master.merge(first,on=["source","source_id"],how="left").merge(last,on=["source","source_id"],how="left")
    master["days_observed"]=(master["last_observed"]-master["first_observed"]).dt.days+1
    master.to_csv(work/"master_listings.csv",index=False)

    # Rejected/review append-only audit
    rej_path=work/"rejected.csv"
    if rej_path.exists():
        rejected=pd.concat([pd.read_csv(rej_path),rejected],ignore_index=True)
    rejected.to_csv(rej_path,index=False)

    # Territorial snapshot, median USD/m2 weighted only by valid unique observations
    obs["Area"]=np.where(obs["province"].astype(str).str.upper().isin(["CABA","CIUDAD AUTONOMA DE BUENOS AIRES"]),"CABA","PBA")
    grpcols=["observation_date","source","province","municipality","locality","neighborhood"]
    snap=(obs.groupby(grpcols,dropna=False)
            .agg(USD_m2=("usd_m2","median"),N=("usd_m2","size"))
            .reset_index().rename(columns={"observation_date":"fecha","province":"Jurisdicción",
                                          "locality":"Localidad","source":"Fuente"}))
    snap.to_csv(work/"snapshots.csv",index=False)

    amba=obs[obs["Area"].isin(["CABA","PBA"])].copy()
    amba=(amba.groupby(["observation_date","Area","municipality","locality","neighborhood","source"],dropna=False)
              .agg(USD_m2=("usd_m2","median"),N=("usd_m2","size")).reset_index()
              .rename(columns={"observation_date":"fecha","municipality":"Municipio",
                               "locality":"Localidad","neighborhood":"Barrio","source":"Fuente"}))
    amba.to_csv(work/"amba.csv",index=False)

    quality=pd.DataFrame([{
        "fecha":date or pd.Timestamp.today().date().isoformat(),
        "relevadas":rep["rows_read"],
        "normalizadas":rep["rows_valid"],
        "revision_ingest":rep["rows_review"],
        "duplicados":int(x["duplicate_same_source"].sum()),
        "candidatos_dup_fuentes":int(x["duplicate_cross_source_candidate"].sum()),
        "descartadas_revision":int((x["quality_status"]!="valid").sum()),
        "validas":len(valid)
    }])
    quality.to_csv(work/"quality.csv",index=False)

    # Index history: observed median; composition-constant is enabled once >=2 dates exist.
    idx=(obs.groupby(["observation_date","source"])
            .agg(indice_observado_usd_m2=("usd_m2","median"),N=("usd_m2","size")).reset_index())
    idx["indice_base_100"]=idx.groupby("source")["indice_observado_usd_m2"].transform(lambda s: s/s.iloc[0]*100)
    idx.to_csv(work/"index_history.csv",index=False)

    summary={"ingest":rep,"valid_after_quality":len(valid),
             "review_or_rejected":len(rejected),"master_rows":len(master),
             "observation_rows":len(observations)}
    (work/"run_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("input"); ap.add_argument("--workdir",default="data")
    ap.add_argument("--source"); ap.add_argument("--date")
    a=ap.parse_args()
    print(json.dumps(build(a.input,a.workdir,a.source,a.date),ensure_ascii=False,indent=2))

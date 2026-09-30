import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from pathlib import Path
from datetime import date

st.set_page_config(page_title="Índice Federal del m²", page_icon="🏠", layout="wide")
DATA = Path(__file__).parent / "data"

# ---------------------------
# Helpers
# ---------------------------
def fmt_int(x):
    return f"{int(x):,}".replace(",", ".")

def fmt_usd(x):
    return f"{x:,.0f}".replace(",", ".")

def weighted_median(values, weights):
    s = pd.DataFrame({"v": values, "w": weights}).dropna().sort_values("v")
    if s.empty or s["w"].sum() <= 0:
        return np.nan
    return s.loc[s["w"].cumsum().ge(s["w"].sum()/2), "v"].iloc[0]

def demo_cross_section():
    # Fallback DEMOSTRATIVO: conserva la escala del prototipo original.
    capitals = {
        "CABA":"CABA","Buenos Aires":"La Plata","Catamarca":"San Fernando del Valle de Catamarca",
        "Chaco":"Resistencia","Chubut":"Rawson","Córdoba":"Córdoba","Corrientes":"Corrientes",
        "Entre Ríos":"Paraná","Formosa":"Formosa","Jujuy":"San Salvador de Jujuy","La Pampa":"Santa Rosa",
        "La Rioja":"La Rioja","Mendoza":"Mendoza","Misiones":"Posadas","Neuquén":"Neuquén",
        "Río Negro":"Viedma","Salta":"Salta","San Juan":"San Juan","San Luis":"San Luis",
        "Santa Cruz":"Río Gallegos","Santa Fe":"Santa Fe","Santiago del Estero":"Santiago del Estero",
        "Tierra del Fuego":"Ushuaia","Tucumán":"San Miguel de Tucumán"
    }
    rows=[]
    for i,(prov,cap) in enumerate(capitals.items()):
        market = 950 + ((i*83)%1250)
        bna = round(market*(0.96 + ((i%7)*0.015)))
        rows += [
            [date.today().isoformat(),prov,cap,"Mercado abierto",market,80+(i*17)%620],
            [date.today().isoformat(),prov,cap,"+Hogares BNA",bna,15+(i*11)%170],
        ]
    return pd.DataFrame(rows, columns=["fecha","Jurisdicción","Localidad","Fuente","USD_m2","N"])

def load_snapshots():
    p = DATA/"snapshots.csv"
    if p.exists():
        x = pd.read_csv(p)
        x["fecha"] = pd.to_datetime(x["fecha"])
        return x, False
    x = demo_cross_section()
    x["fecha"] = pd.to_datetime(x["fecha"])
    return x, True

def load_quality():
    p = DATA/"quality.csv"
    if p.exists():
        q = pd.read_csv(p)
        q["fecha"] = pd.to_datetime(q["fecha"])
        return q
    return pd.DataFrame()

def calc_series(x):
    # Agregado por fecha/fuente usando mediana ponderada por N.
    out=[]
    for (f,src),g in x.groupby(["fecha","Fuente"]):
        out.append([f,src,weighted_median(g["USD_m2"],g["N"]),g["N"].sum()])
    s=pd.DataFrame(out,columns=["fecha","Fuente","USD_m2","N"]).sort_values(["Fuente","fecha"])
    if s.empty:
        return s
    s["Indice_base_100"]=s.groupby("Fuente")["USD_m2"].transform(lambda z: z/z.iloc[0]*100)
    for periods,name in [(1,"Var_periodo_%"),(4,"Var_4p_%"),(12,"Var_12p_%")]:
        s[name]=s.groupby("Fuente")["USD_m2"].pct_change(periods=periods, fill_method=None)*100
    return s

# ---------------------------
# Header
# ---------------------------
st.title("Índice Federal del Precio de Publicación del m²")
st.caption("Mercado abierto (ZonaProp + Argenprop) vs. +Hogares BNA · Venta residencial")

df, demo = load_snapshots()
quality = load_quality()

with st.sidebar:
    st.header("Filtros")
    jurisdictions = ["Todas"] + sorted(df["Jurisdicción"].dropna().unique().tolist())
    jurisdiction = st.selectbox("Jurisdicción", jurisdictions)
    sources = st.multiselect(
        "Fuente",
        ["Mercado abierto","+Hogares BNA"],
        default=["Mercado abierto","+Hogares BNA"]
    )
    st.divider()
    if demo:
        st.warning("MODO DEMOSTRATIVO: todavía no hay snapshots.csv real. No se amplía artificialmente el N.")
    else:
        st.success("Datos cargados desde data/snapshots.csv")

view = df.copy()
if jurisdiction != "Todas":
    view = view[view["Jurisdicción"] == jurisdiction]
view = view[view["Fuente"].isin(sources)]

latest_date = view["fecha"].max()
latest = view[view["fecha"] == latest_date].copy()
market = latest[latest["Fuente"]=="Mercado abierto"]
bna = latest[latest["Fuente"]=="+Hogares BNA"]
market_px = weighted_median(market["USD_m2"],market["N"]) if not market.empty else np.nan
bna_px = weighted_median(bna["USD_m2"],bna["N"]) if not bna.empty else np.nan
n_total = latest["N"].sum()
brecha = (bna_px/market_px-1)*100 if pd.notna(market_px) and pd.notna(bna_px) else np.nan

c1,c2,c3,c4 = st.columns(4)
c1.metric("Mercado abierto · USD/m²", "—" if pd.isna(market_px) else fmt_usd(market_px))
c2.metric("+Hogares BNA · USD/m²", "—" if pd.isna(bna_px) else fmt_usd(bna_px))
c3.metric("Brecha BNA vs mercado", "—" if pd.isna(brecha) else f"{brecha:+.1f}%")
c4.metric("Observaciones válidas", fmt_int(n_total))

st.caption(f"Última medición: {latest_date:%d/%m/%Y}" if pd.notna(latest_date) else "Sin mediciones")

# ---------------------------
# Calidad / caudal
# ---------------------------
st.subheader("Cobertura y caudal de casos")
if not quality.empty:
    q = quality[quality["fecha"] == quality["fecha"].max()].iloc[0]
    cols = st.columns(4)
    cols[0].metric("Publicaciones relevadas", fmt_int(q["relevadas"]))
    cols[1].metric("Duplicados eliminados", fmt_int(q["duplicados"]))
    cols[2].metric("Descartadas por calidad", fmt_int(q["descartadas"]))
    cols[3].metric("Observaciones válidas", fmt_int(q["validas"]))
else:
    st.info("Al incorporar el relevamiento productivo se mostrarán: relevadas → duplicados → descartadas → válidas. El tablero no infla el N con casos sintéticos.")

# ---------------------------
# Series
# ---------------------------
series = calc_series(view)
st.subheader("Series de tiempo")
if series["fecha"].nunique() >= 2:
    tab1,tab2,tab3 = st.tabs(["USD/m²","Índice base 100","Tasas de variación"])
    with tab1:
        fig=px.line(series,x="fecha",y="USD_m2",color="Fuente",markers=True,
                    labels={"fecha":"Fecha","USD_m2":"USD/m²"})
        st.plotly_chart(fig,use_container_width=True)
    with tab2:
        fig=px.line(series,x="fecha",y="Indice_base_100",color="Fuente",markers=True,
                    labels={"fecha":"Fecha","Indice_base_100":"Índice"})
        st.plotly_chart(fig,use_container_width=True)
    with tab3:
        rate = st.selectbox("Variación",["Var_periodo_%","Var_4p_%","Var_12p_%"],
                            format_func=lambda z: {"Var_periodo_%":"Vs. período anterior","Var_4p_%":"4 períodos","Var_12p_%":"12 períodos"}[z])
        fig=px.line(series,x="fecha",y=rate,color="Fuente",markers=True,
                    labels={"fecha":"Fecha",rate":"Variación %"})
        st.plotly_chart(fig,use_container_width=True)
        st.caption("La equivalencia semanal/mensual/trimestral/interanual depende de la frecuencia efectiva de snapshots. La V2 preserva cada corte para no inventar historia.")
else:
    st.info("La serie comenzará cuando exista una segunda medición real. Cada relevamiento debe agregarse como una nueva fecha; nunca se reemplaza el anterior.")

# ---------------------------
# Federal cross-section
# ---------------------------
st.subheader("Comparación territorial · última medición")
pivot = latest.pivot_table(index=["Jurisdicción","Localidad"],columns="Fuente",values=["USD_m2","N"],aggfunc="first").reset_index()
pivot.columns = ["_".join([str(y) for y in x if y]).strip("_") if isinstance(x,tuple) else x for x in pivot.columns]
market_col = "USD_m2_Mercado abierto"
bna_col = "USD_m2_+Hogares BNA"
if market_col in pivot and bna_col in pivot:
    pivot["Brecha_%"]=(pivot[bna_col]/pivot[market_col]-1)*100

long = latest.copy()
fig=px.bar(long,x="Localidad",y="USD_m2",color="Fuente",barmode="group",height=520,
           labels={"Localidad":"Localidad","USD_m2":"USD/m²"})
st.plotly_chart(fig,use_container_width=True)

show = pivot.copy()
st.dataframe(show,use_container_width=True,hide_index=True)


# ---------------------------
# AMBA
# ---------------------------
st.subheader("AMBA · CABA y municipios de PBA")
st.caption("Lectura específica del Área Metropolitana: CABA por barrio y PBA por municipio y localidad.")

amba_path = DATA/"amba.csv"
if amba_path.exists() and amba_path.stat().st_size > 80:
    amba = pd.read_csv(amba_path)
    amba["fecha"] = pd.to_datetime(amba["fecha"])
    amba = amba[amba["Fuente"].isin(sources)]
    amba_latest = amba[amba["fecha"] == amba["fecha"].max()].copy()

    amba_tab1, amba_tab2 = st.tabs(["PBA · Municipio y localidad", "CABA · Barrio"])

    with amba_tab1:
        pba = amba_latest[amba_latest["Area"]=="PBA"].copy()
        if pba.empty:
            st.info("Todavía no hay observaciones AMBA de PBA.")
        else:
            municipios = ["Todos"] + sorted(pba["Municipio"].dropna().unique().tolist())
            muni = st.selectbox("Municipio", municipios, key="amba_municipio")
            if muni != "Todos":
                pba = pba[pba["Municipio"]==muni]
            fig = px.bar(pba, x="Localidad", y="USD_m2", color="Fuente", barmode="group",
                         labels={"USD_m2":"USD/m²","Localidad":"Localidad"}, height=480)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(pba[["Municipio","Localidad","Fuente","USD_m2","N"]]
                         .sort_values(["Municipio","Localidad","Fuente"]),
                         use_container_width=True, hide_index=True)

    with amba_tab2:
        caba = amba_latest[amba_latest["Area"]=="CABA"].copy()
        if caba.empty:
            st.info("Todavía no hay observaciones por barrio de CABA.")
        else:
            fig = px.bar(caba.sort_values("USD_m2", ascending=False), x="Barrio", y="USD_m2",
                         color="Fuente", barmode="group",
                         labels={"USD_m2":"USD/m²","Barrio":"Barrio"}, height=520)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(caba[["Barrio","Fuente","USD_m2","N"]]
                         .sort_values(["Barrio","Fuente"]),
                         use_container_width=True, hide_index=True)
else:
    st.info("La sección AMBA ya está preparada. Se activará con datos reales en data/amba.csv: PBA por municipio/localidad y CABA por barrio.")

with st.expander("Metodología y trazabilidad"):
    st.markdown("""
**Mercado abierto:** ZonaProp + Argenprop, tratados como un universo conjunto luego de deduplicar propiedades únicas.  
**+Hogares BNA:** universo separado y comparable; no se mezcla dentro del mercado abierto.  
**Medida principal:** mediana de USD/m², agregada territorialmente con ponderación por cantidad de observaciones.  
**Historia:** cada snapshot se conserva con fecha. El tablero nunca reconstruye una serie ficticia.  
**Control de muestra:** relevadas, duplicados, descartadas y observaciones válidas.  
**Próxima capa metodológica:** índice de composición constante / hedónico cuando la base tenga atributos suficientes y continuidad temporal.
""")

st.divider()
st.caption("V2 · Arquitectura preparada para ampliar muestra, preservar +Hogares BNA y construir series históricas y tasas de variación.")

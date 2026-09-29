import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title='Índice Federal del m²', page_icon='🏠', layout='wide')
st.title('Índice Federal del Precio de Publicación del m²')
st.caption('Prototipo demostrativo · Mercado abierto (ZonaProp + Argenprop) vs. +Hogares BNA · Venta residencial')

capitals = {
'CABA':'CABA','Buenos Aires':'La Plata','Catamarca':'San Fernando del Valle de Catamarca','Chaco':'Resistencia','Chubut':'Rawson','Córdoba':'Córdoba','Corrientes':'Corrientes','Entre Ríos':'Paraná','Formosa':'Formosa','Jujuy':'San Salvador de Jujuy','La Pampa':'Santa Rosa','La Rioja':'La Rioja','Mendoza':'Mendoza','Misiones':'Posadas','Neuquén':'Neuquén','Río Negro':'Viedma','Salta':'Salta','San Juan':'San Juan','San Luis':'San Luis','Santa Cruz':'Río Gallegos','Santa Fe':'Santa Fe','Santiago del Estero':'Santiago del Estero','Tierra del Fuego':'Ushuaia','Tucumán':'San Miguel de Tucumán'}
# Datos sintéticos exclusivamente para mostrar funcionamiento del dashboard.
rows=[]
for i,(prov,cap) in enumerate(capitals.items()):
    market = 950 + ((i*83)%1250)
    bna = round(market*(0.96 + ((i%7)*0.015)))
    rows.append([prov,cap,market,80+(i*17)%620,bna,15+(i*11)%170])
df=pd.DataFrame(rows,columns=['Jurisdicción','Capital','Mercado_USD_m2','N_Mercado','BNA_USD_m2','N_BNA'])
df['Brecha_%']=(df['BNA_USD_m2']/df['Mercado_USD_m2']-1)*100

with st.sidebar:
    st.header('Filtros')
    jurisdiction=st.selectbox('Jurisdicción',['Todas']+df['Jurisdicción'].tolist())
    tipo=st.selectbox('Tipo de vivienda',['Total residencial','Departamento','Casa'])
    estado=st.selectbox('Estado',['Todos','Usado','Nuevo / a estrenar','En pozo'])
    st.info('Los valores actuales son DEMOSTRATIVOS. La versión productiva se alimentará del relevamiento validado y deduplicado.')

view=df if jurisdiction=='Todas' else df[df['Jurisdicción']==jurisdiction]
c1,c2,c3,c4=st.columns(4)
c1.metric('Mercado abierto · USD/m²',f"{view['Mercado_USD_m2'].median():,.0f}")
c2.metric('+Hogares BNA · USD/m²',f"{view['BNA_USD_m2'].median():,.0f}")
c3.metric('Brecha BNA vs mercado',f"{(view['BNA_USD_m2'].median()/view['Mercado_USD_m2'].median()-1)*100:+.1f}%")
c4.metric('Observaciones válidas',f"{int(view['N_Mercado'].sum()+view['N_BNA'].sum()):,}")

st.subheader('Comparación por capital')
long=view.melt(id_vars=['Capital'],value_vars=['Mercado_USD_m2','BNA_USD_m2'],var_name='Fuente',value_name='USD/m²')
long['Fuente']=long['Fuente'].map({'Mercado_USD_m2':'Mercado ZP + AP','BNA_USD_m2':'+Hogares BNA'})
fig=px.bar(long,x='Capital',y='USD/m²',color='Fuente',barmode='group',height=500)
st.plotly_chart(fig,use_container_width=True)

st.subheader('Tabla federal')
table=view[['Jurisdicción','Capital','Mercado_USD_m2','N_Mercado','BNA_USD_m2','N_BNA','Brecha_%']].copy()
table.columns=['Jurisdicción','Capital','USD/m² mercado','N mercado','USD/m² +Hogares','N +Hogares','Brecha %']
st.dataframe(table.style.format({'USD/m² mercado':'{:,.0f}','USD/m² +Hogares':'{:,.0f}','Brecha %':'{:+.1f}%'}),use_container_width=True,hide_index=True)

st.subheader('Evolución histórica')
st.caption('La serie comenzará con la primera medición real y se actualizará quincenalmente. El prototipo no inventa historia previa.')
st.line_chart(pd.DataFrame({'Semana base':[100]},index=['Base']))

with st.expander('Metodología y trazabilidad'):
    st.markdown('''**Mercado abierto:** ZonaProp + Argenprop, deduplicados para representar propiedades únicas.  
**+Hogares BNA:** índice paralelo calculado exclusivamente con publicaciones de la plataforma.  
**Universo:** inmuebles residenciales en venta; excluye terrenos, oficinas, locales, depósitos y galpones.  
**Segmentación prevista:** casa/departamento × usado/nuevo-en-estrenar/en-pozo.  
**Control de muestra:** se informarán observaciones brutas, descartadas, duplicados y N válido; los segmentos con baja cobertura se marcarán como muestra insuficiente.''')

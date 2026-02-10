import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import math
import time
import plotly.express as px
from fpdf import FPDF
import base64
import google.generativeai as genai
from PIL import Image, ImageEnhance
import io
import json

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Ledisa v3.5", layout="wide", page_icon="🏗️")

# Estilos CSS Limpios
st.markdown("""
    <style>
        .stButton>button { width: 100%; border-radius: 5px; }
        .metric-box { padding: 10px; background-color: #f0f2f6; border-radius: 5px; text-align: center; }
        /* Ajuste para que las imágenes no se vean gigantes en móviles */
        img { max-height: 300px; object-fit: contain; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONEXIÓN Y DATOS ---
def conectar_google_sheets():
    """Conexión robusta a Google Sheets con manejo de errores."""
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        if "gcp_service_account" not in st.secrets:
            st.error("❌ Error Crítico: No se detectaron las credenciales en secrets.toml")
            st.stop()
        
        secrets_dict = dict(st.secrets["gcp_service_account"])
        secrets_dict["private_key"] = secrets_dict["private_key"].replace("\\n", "\n")
        
        creds = Credentials.from_service_account_info(secrets_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # Intenta abrir la hoja 'Inventario', si falla prueba con la default
        try: return client.open("Inventario").sheet1
        except: return client.open("inventario_db").sheet1
            
    except Exception as e:
        st.error(f"❌ Error conectando a Google: {e}")
        st.stop()

@st.cache_data(ttl=60) # Caché de 1 minuto para velocidad
def obtener_datos():
    hoja = conectar_google_sheets()
    if not hoja: return pd.DataFrame(), None
    
    try:
        datos = hoja.get_all_values()
        if not datos: return pd.DataFrame(), hoja
        
        headers = datos.pop(0)
        df = pd.DataFrame(datos, columns=headers)
        
        # Limpieza numérica vital para cálculos
        cols_num = ['stock', 'm2_caja', 'precio']
        for col in cols_num:
            if col in df.columns:
                # Elimina 'S/.', comas y espacios, convierte a float
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace('S/.', '').str.replace(',', ''), 
                    errors='coerce'
                ).fillna(0)
        
        # Métrica Calculada: Total de metros disponibles
        df['total_m2'] = df['stock'] * df['m2_caja']
        
        return df, hoja
    except Exception as e:
        st.error(f"Error procesando datos: {e}")
        return pd.DataFrame(), hoja

def subir_a_imgbb(archivo_bytes, nombre):
    """Sube imagen a ImgBB y retorna URL pública."""
    try:
        if "imgbb" not in st.secrets: return None
        api_key = st.secrets["imgbb"]["key"]
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": api_key, "name": nombre}
        files = {"image": archivo_bytes}
        res = requests.post(url, data=payload, files=files)
        if res.status_code == 200: return res.json()['data']['url']
    except: pass
    return None

# --- 3. TRUCO DE IMAGEN (MEJORA DE CALIDAD) ---
def procesar_imagen_nitidez(url_imagen):
    """
    Descarga la imagen y aplica un filtro de nitidez digital
    para compensar baja resolución.
    """
    if not url_imagen or not str(url_imagen).startswith("http"): return None
    try:
        response = requests.get(url_imagen, timeout=3)
        img = Image.open(io.BytesIO(response.content))
        
        # Truco 1: Convertir a RGB (evita errores con PNG transparentes)
        if img.mode != 'RGB': img = img.convert('RGB')
        
        # Truco 2: Aumentar Nitidez (Sharpness) un 50%
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.5) 
        
        # Truco 3: Aumentar Contraste un 10%
        enhancer_con = ImageEnhance.Contrast(img)
        img = enhancer_con.enhance(1.1)
        
        return img
    except:
        return None # Si falla, no mostramos nada para no romper la app

# --- 4. MÓDULOS DE LÓGICA DE NEGOCIO ---

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'DISTRIBUIDORA LEDISA', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, 'Materiales de Construcción y Acabados', 0, 1, 'C')
        self.ln(10)

def calculadora_obra(df):
    st.subheader("🧮 Calculadora de Materiales")
    
    # Filtramos solo lo que se puede calcular por m2
    df_rev = df[df['categoria'].isin(['Mayólica', 'Porcelanato', 'Piso', 'Pared', 'Cerámico'])]
    
    c1, c2 = st.columns([2, 1])
    with c1:
        opciones = df_rev.apply(lambda x: f"{x['nombre']} | {x['marca']}", axis=1)
        sel = st.selectbox("Selecciona Producto:", opciones)
        
        if sel:
            nombre_real = sel.split(" | ")[0]
            item = df_rev[df_rev['nombre'] == nombre_real].iloc[0]
            rendimiento = float(item['m2_caja'])
            precio = float(item['precio'])
            
            st.info(f"📦 Rendimiento: **{rendimiento} m²/caja**")
            st.success(f"💰 Precio: **S/. {precio:.2f}**")
            
            # Mostramos imagen optimizada
            img_url = str(item['imagen']).split(",")[0]
            img_obj = procesar_imagen_nitidez(img_url)
            if img_obj: st.image(img_obj, width=200)

    with c2:
        largo = st.number_input("Largo (m)", 0.0, step=0.1)
        ancho = st.number_input("Ancho (m)", 0.0, step=0.1)
        merma = st.selectbox("Merma (Cortes)", [0.05, 0.10, 0.15], index=1, format_func=lambda x: f"{int(x*100)}%")

    if largo > 0 and ancho > 0 and rendimiento > 0:
        area_real = largo * ancho
        area_total = area_real * (1 + merma)
        cajas = math.ceil(area_total / rendimiento)
        total_pagar = cajas * precio
        m2_comprados = cajas * rendimiento
        
        st.divider()
        k1, k2 = st.columns(2)
        k1.metric("Cajas Necesarias", f"{cajas} Cajas", f"Cubres {m2_comprados:.2f} m²")
        k2.metric("Total a Pagar", f"S/. {total_pagar:,.2f}")

def dashboard_gerencial(df):
    st.subheader("📊 Tablero de Control")
    if df.empty: return
    
    # KPIs
    valor_total = (df['stock'] * df['precio']).sum()
    stock_total = df['stock'].sum()
    m2_totales = df['total_m2'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Valor Inventario", f"S/. {valor_total:,.2f}")
    c2.metric("Unidades Físicas", f"{int(stock_total)}")
    c3.metric("Stock Superficie", f"{m2_totales:,.2f} m²")
    
    st.divider()
    
    # Gráficos
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Stock por Categoría (Soles)**")
        df['total_row'] = df['stock'] * df['precio']
        df_cat = df.groupby('categoria')['total_row'].sum().reset_index()
        fig = px.pie(df_cat, values='total_row', names='categoria', hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
        
    with g2:
        st.markdown("**Top Productos con más m²**")
        top_m2 = df.sort_values('total_m2', ascending=False).head(7)
        st.bar_chart(top_m2.set_index('nombre')['total_m2'])

def cotizador_pdf(df):
    st.subheader("📄 Generador de Cotizaciones")
    
    if 'carrito' not in st.session_state: st.session_state.carrito = []
    
    # Selector
    c1, c2 = st.columns([3, 1])
    with c1:
        sel_prod = st.selectbox("Agregar Producto:", df['id'] + " - " + df['nombre'])
    with c2:
        cant = st.number_input("Cant.", min_value=1, value=1)
        
    if st.button("➕ Agregar"):
        id_p = sel_prod.split(" - ")[0]
        item = df[df['id'] == id_p].iloc[0]
        subtotal = cant * float(item['precio'])
        
        st.session_state.carrito.append({
            "desc": f"{item['nombre']} ({item['marca']})",
            "cant": cant,
            "unit": float(item['precio']),
            "total": subtotal
        })
        
    # Tabla
    if st.session_state.carrito:
        df_cart = pd.DataFrame(st.session_state.carrito)
        st.dataframe(df_cart, hide_index=True)
        gran_total = df_cart['total'].sum()
        st.metric("Total Cotización", f"S/. {gran_total:,.2f}")
        
        cliente = st.text_input("Nombre Cliente:")
        if st.button("🖨️ Descargar PDF") and cliente:
            pdf = PDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, f"Cliente: {cliente}", ln=True)
            pdf.cell(0, 10, f"Fecha: {pd.Timestamp.now().strftime('%d/%m/%Y')}", ln=True)
            pdf.ln(5)
            # Tabla simple
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(100, 10, "Producto", 1); pdf.cell(20, 10, "Cant", 1); pdf.cell(30, 10, "Precio", 1); pdf.ln()
            pdf.set_font("Arial", size=10)
            for p in st.session_state.carrito:
                pdf.cell(100, 10, p['desc'][:50], 1)
                pdf.cell(20, 10, str(p['cant']), 1)
                pdf.cell(30, 10, f"{p['total']:.2f}", 1)
                pdf.ln()
            pdf.cell(150, 10, f"TOTAL: S/. {gran_total:.2f}", 1, 0, 'R')
            
            # Descarga
            b64 = base64.b64encode(pdf.output(dest='S').encode('latin-1')).decode()
            href = f'<a href="data:application/pdf;base64,{b64}" download="Cotizacion_{cliente}.pdf">📥 Bajar PDF</a>'
            st.markdown(href, unsafe_allow_html=True)
            
        if st.button("Limpiar"):
            st.session_state.carrito = []
            st.rerun()

def simulador_25d(df):
    st.header("gfa Simulador de Espacios 2.5D")
    st.info("Visualiza la combinación con efecto de profundidad.")
    
    c1, c2 = st.columns(2)
    with c1:
        # Pared
        df_p = df[df['categoria'].isin(['Pared', 'Mayólica', 'Cerámico'])]
        if df_p.empty: df_p = df
        sel_p = st.selectbox("🧱 Pared:", df_p['nombre'])
        url_p = df_p[df_p['nombre'] == sel_p].iloc[0]['imagen'].split(",")[0]
        
    with c2:
        # Piso
        df_s = df[df['categoria'].isin(['Piso', 'Porcelanato'])]
        if df_s.empty: df_s = df
        sel_s = st.selectbox("👣 Piso:", df_s['nombre'])
        url_s = df_s[df_s['nombre'] == sel_s].iloc[0]['imagen'].split(",")[0]

    st.markdown("---")
    # Inyección HTML para el efecto 3D
    html = f"""
    <div style="display:flex; flex-direction:column; align-items:center; width:100%; max-width:600px; margin:auto; perspective:800px;">
        <div style="width:100%; height:250px; background-image:url('{url_p}'); background-size:cover; background-position:center; box-shadow:0 10px 20px rgba(0,0,0,0.3); z-index:2;"></div>
        <div style="width:100%; height:250px; background-image:url('{url_s}'); background-size:contain; background-repeat:repeat; transform:rotateX(60deg) scale(1.2); transform-origin:top; margin-top:-20px; z-index:1; opacity:0.9;"></div>
    </div>
    """
    st.components.v1.html(html, height=550)

def consultor_ia_flash(df):
    st.header("🤖 Consultor IA (Flash)")
    st.info("Modelo: gemini-flash-latest")
    
    if 'tags_ia' not in df.columns:
        st.warning("⚠️ Faltan etiquetas (tags_ia). La IA puede fallar.")
    
    # Configuración Modelo
    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
        model = genai.GenerativeModel('models/gemini-flash-latest') # Tu modelo preferido
    except Exception as e:
        st.error(f"Error IA: {e}")
        return

    query = st.chat_input("¿Qué busca el cliente?")
    if query:
        with st.chat_message("user"): st.write(query)
        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                # Contexto limitado para rapidez
                inv_data = df[['id', 'nombre', 'tags_ia', 'precio']].head(80).to_dict(orient='records')
                prompt = f"""
                Recomienda 3 productos para: "{query}".
                Inventario: {json.dumps(inv_data)}
                Responde SOLO JSON válido:
                {{ "recomendaciones": [ {{ "id": "ID", "razon": "txt" }} ], "consejo": "txt" }}
                """
                
                try:
                    res = model.generate_content(prompt)
                    clean_text = res.text.replace("```json", "").replace("```", "").strip()
                    if "{" in clean_text: 
                        clean_text = clean_text[clean_text.find("{"):clean_text.rfind("}")+1]
                    
                    data = json.loads(clean_text)
                    
                    st.subheader("🏆 Sugerencias:")
                    cols = st.columns(3)
                    for i, r in enumerate(data.get('recomendaciones', [])):
                        prod = df[df['id'].astype(str) == str(r['id'])].iloc[0] if not df[df['id'].astype(str) == str(r['id'])].empty else None
                        
                        with cols[i%3]:
                            if prod is not None:
                                img_url = str(prod['imagen']).split(",")[0]
                                # Usamos la función de nitidez aquí
                                img_obj = procesar_imagen_nitidez(img_url)
                                if img_obj: st.image(img_obj)
                                
                                st.markdown(f"**{prod['nombre']}**")
                                st.caption(f"_{r['razon']}_")
                                st.markdown(f"**S/. {prod['precio']}**")
                            else:
                                st.error(f"ID {r['id']} no encontrado.")
                                
                    if 'consejo' in data: st.info(f"💡 {data['consejo']}")
                    
                except Exception as e:
                    st.error(f"La IA no pudo responder: {e}")

# --- 5. INTERFAZ PRINCIPAL Y MENÚS ---
def main():
    # Login simple
    if 'auth' not in st.session_state: st.session_state.auth = False
    
    with st.sidebar:
        st.title("🔐 Acceso")
        if not st.session_state.auth:
            pwd = st.text_input("Contraseña", type="password")
            if st.button("Entrar"):
                if pwd == st.secrets["general"]["password"]:
                    st.session_state.auth = True
                    st.rerun()
                else: st.error("Incorrecto")
            return # Detener ejecución si no está logueado
            
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False
            st.rerun()

    # App Principal
    st.title("🏭 Sistema Ledisa v3.5")
    df, hoja = obtener_datos()
    
    menu = st.sidebar.radio("Menú:", 
        ["Ver Inventario", "Registrar Nuevo", "Editar Producto", "Actualizar Stock", 
         "Calculadora Obra", "Cotizador PDF", "Simulador 2.5D", "Dashboard", "Consultor IA"])

    # 1. VER INVENTARIO (Con Doble Foto y Nitidez)
    if menu == "Ver Inventario":
        q = st.text_input("🔍 Buscar Producto:")
        if q and not df.empty:
            df = df[df.astype(str).apply(lambda x: x.str.contains(q, case=False)).any(axis=1)]
        
        if not df.empty:
            cols = st.columns(3)
            for i, row in df.iterrows():
                with cols[i%3]:
                    st.container()
                    # Gestión de fotos
                    imgs = str(row['imagen']).split(",")
                    url_p = imgs[0] if len(imgs)>0 and imgs[0].startswith("http") else None
                    url_a = imgs[1] if len(imgs)>1 and imgs[1].startswith("http") else None
                    
                    # Pestañas si hay 2 fotos
                    if url_p and url_a:
                        t1, t2 = st.tabs(["Pieza", "Ambiente"])
                        with t1: 
                            im = procesar_imagen_nitidez(url_p)
                            if im: st.image(im)
                        with t2: 
                            im = procesar_imagen_nitidez(url_a)
                            if im: st.image(im)
                    elif url_p:
                        im = procesar_imagen_nitidez(url_p)
                        if im: st.image(im)
                    else:
                        st.text("Sin imagen")
                        
                    st.markdown(f"**{row['nombre']}**")
                    st.caption(f"ID: {row['id']} | {row['marca']}")
                    
                    c1, c2 = st.columns(2)
                    c1.metric("Stock", row['stock'])
                    c2.metric("Precio", f"S/. {row['precio']}")
                    
                    if row['m2_caja'] > 0:
                        st.success(f"📦 Total: {row['total_m2']:.2f} m²")
                    elif str(row['formato']) not in ["", "0", "-"]:
                        st.info(f"⚖️ {row['formato']}")
                        
                    st.divider()

    # 2. REGISTRAR (Lógica Dinámica)
    elif menu == "Registrar Nuevo":
        st.subheader("📝 Nuevo Ingreso")
        cat = st.selectbox("Categoría Principal:", 
            ["Mayólica", "Porcelanato", "Piso", "Pared", "Pegamento", "Fragua", "Sanitario", "Grifería"])
        
        with st.form("reg"):
            c1, c2 = st.columns(2)
            id_z = c1.text_input("Código/ID *")
            nom = c2.text_input("Nombre *")
            marca = st.selectbox("Marca", ["Celima", "Trebol", "Generico", "Otro"])
            
            # Dinamismo
            fmt_val, m2_val = "-", 0.0
            c3, c4 = st.columns(2)
            
            if cat in ["Mayólica", "Porcelanato", "Piso", "Pared"]:
                fmt_val = c3.text_input("Formato (cm)")
                m2_val = c4.number_input("m² por Caja *", min_value=0.01)
            elif cat in ["Pegamento", "Fragua"]:
                fmt_val = c3.text_input("Peso/Presentación")
                st.caption("ℹ️ m² se guardará como 0")
            else:
                fmt_val = c3.text_input("Modelo/Color")
            
            c5, c6 = st.columns(2)
            stk = c5.number_input("Stock Inicial", min_value=0)
            prc = c6.number_input("Precio S/.", min_value=0.0)
            
            f1 = st.file_uploader("Foto Pieza")
            f2 = st.file_uploader("Foto Ambiente (Opcional)")
            
            if st.form_submit_button("Guardar"):
                if not id_z or not nom: st.error("Faltan datos")
                elif cat in ["Piso", "Pared"] and m2_val == 0: st.error("Falta m²")
                else:
                    u1 = subir_a_imgbb(f1.getvalue(), nom+"_1") if f1 else ""
                    u2 = subir_a_imgbb(f2.getvalue(), nom+"_2") if f2 else ""
                    # Unimos urls con coma
                    u_final = f"{u1},{u2}" if u2 else u1
                    
                    row = [id_z, nom, cat, marca, fmt_val, m2_val, "Estándar", stk, prc, u_final]
                    hoja.append_row(row)
                    st.success("Guardado!")
                    time.sleep(1)
                    st.rerun()

    # 3. EDITAR
    elif menu == "Editar Producto":
        st.subheader("✏️ Editar Datos")
        sel = st.selectbox("Producto:", df['id'] + " | " + df['nombre'])
        if sel:
            idx = df[df['id'] == sel.split(" | ")[0]].index[0]
            row = df.iloc[idx]
            
            with st.form("edit"):
                n_nom = st.text_input("Nombre", row['nombre'])
                c1, c2 = st.columns(2)
                n_cat = c1.text_input("Categoría", row['categoria'])
                n_prc = c2.number_input("Precio", value=float(row['precio']))
                n_m2 = st.number_input("m² Caja", value=float(row['m2_caja']))
                
                if st.form_submit_button("Actualizar"):
                    fila = idx + 2
                    hoja.update_cell(fila, 2, n_nom)
                    hoja.update_cell(fila, 3, n_cat)
                    hoja.update_cell(fila, 6, n_m2)
                    hoja.update_cell(fila, 9, n_prc)
                    st.success("Listo")
                    st.rerun()

    # 4. STOCK RÁPIDO
    elif menu == "Actualizar Stock":
        st.subheader("📦 Ajuste de Inventario")
        sel = st.selectbox("Producto:", df['id'] + " | " + df['nombre'])
        row = df[df['id'] == sel.split(" | ")[0]].iloc[0]
        
        st.metric("Stock Actual", int(row['stock']))
        ajuste = st.number_input("Sumar/Restar:", step=1)
        
        if st.button("Aplicar"):
            idx = df[df['id'] == sel.split(" | ")[0]].index[0]
            nuevo = int(row['stock']) + ajuste
            hoja.update_cell(idx+2, 8, nuevo)
            st.success(f"Nuevo stock: {nuevo}")
            time.sleep(1)
            st.rerun()

    # Módulos Extra
    elif menu == "Calculadora Obra": calculadora_obra(df)
    elif menu == "Cotizador PDF": cotizador_pdf(df)
    elif menu == "Dashboard": dashboard_gerencial(df)
    elif menu == "Simulador 2.5D": simulador_25d(df)
    elif menu == "Consultor IA": consultor_ia_flash(df)

if __name__ == "__main__":
    main()
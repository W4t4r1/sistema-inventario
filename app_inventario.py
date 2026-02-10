import streamlit as st
import pandas as pd
from supabase import create_client, Client
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
from datetime import datetime

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Ledisa PRO", layout="wide", page_icon="🏗️")

st.markdown("""
    <style>
        .stButton>button { width: 100%; border-radius: 5px; font-weight: bold; }
        .metric-box { padding: 15px; background-color: #f8f9fa; border-radius: 8px; text-align: center; border: 1px solid #dee2e6; }
        img { max-height: 350px; object-fit: contain; border-radius: 8px; }
        /* Ajuste sutil para tablas */
        [data-testid="stDataFrame"] { border: 1px solid #f0f0f0; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONEXIÓN SUPABASE (EL NUEVO CEREBRO) ---
@st.cache_resource
def init_supabase():
    """Inicializa la conexión única a Supabase."""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Error crítico de conexión: {e}")
        st.stop()

supabase = init_supabase()

def obtener_datos():
    """Descarga la tabla 'inventario' en milisegundos."""
    try:
        response = supabase.table("inventario").select("*").execute()
        df = pd.DataFrame(response.data)
        
        if df.empty: return pd.DataFrame(), None

        # Asegurar tipos numéricos (Postgres ya lo hace, pero por seguridad)
        cols_num = ['stock', 'm2_caja', 'precio']
        for col in cols_num:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Métrica Calculada
        df['total_m2'] = df['stock'] * df['m2_caja']
        return df
    except Exception as e:
        st.error(f"Error leyendo base de datos: {e}")
        return pd.DataFrame()

def subir_a_supabase(archivo_bytes, nombre_archivo, tipo_mime):
    """Sube imagen al Bucket 'productos' de Supabase."""
    try:
        # Generar nombre único: nombre_fecha.jpg
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_limpio = "".join(x for x in nombre_archivo if x.isalnum())
        path = f"{nombre_limpio}_{timestamp}.jpg"
        
        # Subir
        bucket = "productos"
        supabase.storage.from_(bucket).upload(
            path=path,
            file=archivo_bytes,
            file_options={"content-type": tipo_mime}
        )
        
        # Obtener URL Pública
        public_url = supabase.storage.from_(bucket).get_public_url(path)
        return public_url
    except Exception as e:
        st.error(f"Error subiendo a Storage: {e}")
        return None

# --- 3. UTILIDADES DE IMAGEN (MEJORA VISUAL) ---
def procesar_imagen_nitidez(url_imagen):
    """Mejora visual para pantallas."""
    if not url_imagen or not str(url_imagen).startswith("http"): return None
    try:
        response = requests.get(url_imagen, timeout=3)
        img = Image.open(io.BytesIO(response.content))
        if img.mode != 'RGB': img = img.convert('RGB')
        
        # Mejora sutil
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.4) # 40% más nítido
        return img
    except: return None

# --- 4. LÓGICA DE NEGOCIO ---

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'DISTRIBUIDORA LEDISA', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, 'Materiales de Construcción y Acabados', 0, 1, 'C')
        self.ln(10)

def calculadora_obra(df):
    st.subheader("🧮 Calculadora de Materiales PRO")
    df_rev = df[df['categoria'].isin(['Mayólica', 'Porcelanato', 'Piso', 'Pared', 'Cerámico'])]
    
    if df_rev.empty:
        st.warning("No hay revestimientos en la base de datos.")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        # Búsqueda inteligente
        opciones = df_rev.apply(lambda x: f"{x['nombre']} ({x['marca']})", axis=1)
        sel = st.selectbox("Producto:", opciones)
        
        if sel:
            # Recuperamos el ID real buscando en el DF
            idx = opciones[opciones == sel].index[0]
            item = df_rev.loc[idx]
            
            rendimiento = float(item['m2_caja'])
            precio = float(item['precio'])
            
            st.info(f"📦 Caja: **{rendimiento} m²** | Precio: **S/. {precio:.2f}**")
            
            # Mostrar imagen
            imgs = str(item['imagen']).split(",")
            if len(imgs) > 0 and imgs[0]:
                im = procesar_imagen_nitidez(imgs[0])
                if im: st.image(im, width=200)

    with c2:
        largo = st.number_input("Largo (m)", 0.0, step=0.1)
        ancho = st.number_input("Ancho (m)", 0.0, step=0.1)
        merma = st.selectbox("Merma", [0.05, 0.10, 0.15], index=1, format_func=lambda x: f"{int(x*100)}%")

    if largo > 0 and ancho > 0 and rendimiento > 0:
        area_real = largo * ancho
        area_total = area_real * (1 + merma)
        cajas = math.ceil(area_total / rendimiento)
        total_pagar = cajas * precio
        m2_cubiertos = cajas * rendimiento
        
        st.success(f"✅ Necesitas **{cajas} cajas**")
        st.write(f"Cubrirás {m2_cubiertos:.2f} m² (Sobra: {m2_cubiertos - area_total:.2f} m²)")
        st.metric("Total a Pagar", f"S/. {total_pagar:,.2f}")

def dashboard_gerencial(df):
    st.subheader("📊 Tablero Gerencial")
    if df.empty: return
    
    valor_total = (df['stock'] * df['precio']).sum()
    stock_total = df['stock'].sum()
    m2_totales = df['total_m2'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Valor Inventario", f"S/. {valor_total:,.2f}", delta_color="normal")
    c2.metric("Unidades Físicas", f"{int(stock_total)}")
    c3.metric("Stock Superficie", f"{m2_totales:,.2f} m²")
    
    st.divider()
    
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**💰 Valor por Marca**")
        df['valor_row'] = df['stock'] * df['precio']
        df_mar = df.groupby('marca')['valor_row'].sum().reset_index()
        fig = px.pie(df_mar, values='valor_row', names='marca', hole=0.5)
        st.plotly_chart(fig, use_container_width=True)
        
    with g2:
        st.markdown("**🏆 Top Productos (Stock m²)**")
        top = df.sort_values('total_m2', ascending=False).head(8)
        st.bar_chart(top.set_index('nombre')['total_m2'])

def simulador_25d(df):
    st.header("📐 Simulador de Espacios 2.5D")
    
    c1, c2 = st.columns(2)
    with c1:
        df_p = df[df['categoria'].isin(['Pared', 'Mayólica', 'Cerámico'])]
        if df_p.empty: df_p = df
        sel_p = st.selectbox("🧱 Pared:", df_p['nombre'])
        try:
            url_p = df_p[df_p['nombre'] == sel_p].iloc[0]['imagen'].split(",")[0]
        except: url_p = ""
        
    with c2:
        df_s = df[df['categoria'].isin(['Piso', 'Porcelanato'])]
        if df_s.empty: df_s = df
        sel_s = st.selectbox("👣 Piso:", df_s['nombre'])
        try:
            url_s = df_s[df_s['nombre'] == sel_s].iloc[0]['imagen'].split(",")[0]
        except: url_s = ""

    st.markdown("---")
    if url_p and url_s:
        html = f"""
        <div style="display:flex; flex-direction:column; align-items:center; width:100%; max-width:600px; margin:auto; perspective:800px;">
            <div style="width:100%; height:250px; background-image:url('{url_p}'); background-size:cover; background-position:center; box-shadow:0 10px 20px rgba(0,0,0,0.3); z-index:2;"></div>
            <div style="width:100%; height:250px; background-image:url('{url_s}'); background-size:contain; background-repeat:repeat; transform:rotateX(60deg) scale(1.2); transform-origin:top; margin-top:-20px; z-index:1; opacity:0.9;"></div>
        </div>
        """
        st.components.v1.html(html, height=550)
    else:
        st.warning("Selecciona productos con imagen para ver la simulación.")

def consultor_ia(df):
    st.header("🤖 Consultor Ledisa AI")
    
    if "gemini" not in st.secrets:
        st.error("⚠️ Falta API Key Gemini")
        return
        
    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
        model = genai.GenerativeModel('models/gemini-flash-latest')
    except: return

    q = st.chat_input("¿Qué necesita el cliente?")
    if q:
        with st.chat_message("user"): st.write(q)
        with st.chat_message("assistant"):
            with st.spinner("Buscando en base de datos..."):
                # Contexto optimizado
                inv = df[['id', 'nombre', 'tags_ia', 'precio', 'marca']].head(80).to_dict('records')
                prompt = f"""
                Recomienda 3 productos para: "{q}".
                Inventario: {json.dumps(inv)}
                Responde JSON: {{ "recomendaciones": [ {{ "id": "ID", "razon": "txt" }} ], "consejo": "txt" }}
                """
                try:
                    res = model.generate_content(prompt)
                    txt = res.text.replace("```json", "").replace("```", "").strip()
                    if "{" in txt: txt = txt[txt.find("{"):txt.rfind("}")+1]
                    data = json.loads(txt)
                    
                    cols = st.columns(3)
                    for i, r in enumerate(data.get('recomendaciones', [])):
                        # Búsqueda robusta por ID (string)
                        prod = df[df['id'].astype(str) == str(r['id'])]
                        
                        with cols[i%3]:
                            if not prod.empty:
                                row = prod.iloc[0]
                                imgs = str(row['imagen']).split(",")
                                if imgs[0]: 
                                    im = procesar_imagen_nitidez(imgs[0])
                                    if im: st.image(im)
                                st.markdown(f"**{row['nombre']}**")
                                st.caption(r['razon'])
                                st.write(f"**S/. {row['precio']}**")
                            else:
                                st.warning(f"Producto {r['id']} no hallado.")
                    
                    if 'consejo' in data: st.info(f"💡 {data['consejo']}")
                except: st.error("Error conectando con la IA.")

# --- 5. INTERFAZ PRINCIPAL ---
def main():
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
            return
        
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False
            st.rerun()

    st.title("🏭 Sistema Ledisa v4.0 (Cloud)")
    df = obtener_datos() # Ahora viene de Supabase
    
    menu = st.sidebar.radio("Menú:", 
        ["Ver Inventario", "Registrar Nuevo", "Editar Producto", "Actualizar Stock", 
         "Calculadora Obra", "Simulador 2.5D", "Dashboard", "Consultor IA"])

    # 1. VER INVENTARIO
    if menu == "Ver Inventario":
        q = st.text_input("🔍 Buscar:")
        if q and not df.empty:
            df = df[df.astype(str).apply(lambda x: x.str.contains(q, case=False)).any(axis=1)]
        
        if not df.empty:
            # --- REEMPLAZA DESDE AQUÍ ---
            cols = st.columns(3)
            for i, row in df.iterrows():
                with cols[i%3]:
                    st.container()
                    
                    # 1. Obtener URLs de imagen de forma segura
                    imgs = str(row['imagen']).split(",") if row['imagen'] else []
                    
                    # Limpiamos URLs vacías que puedan quedar (ej: "url1,")
                    imgs = [url.strip() for url in imgs if url and len(url.strip()) > 5]

                    # 2. Lógica de visualización (BLINDADA)
                    if len(imgs) > 0:
                        # Si hay al menos una imagen válida
                        url_p = imgs[0]
                        url_a = imgs[1] if len(imgs) > 1 else None

                        if url_p and url_a:
                            # CASO 1: Dos fotos (Pestañas)
                            t1, t2 = st.tabs(["Pieza", "Ambiente"])
                            with t1: 
                                im = procesar_imagen_nitidez(url_p)
                                st.image(im or url_p) # Si falla el proceso, usa la URL
                            with t2:
                                im = procesar_imagen_nitidez(url_a)
                                st.image(im or url_a)
                        else:
                            # CASO 2: Solo una foto
                            im = procesar_imagen_nitidez(url_p)
                            st.image(im or url_p)
                    else:
                        # CASO 3: No hay imagen (Evita el error 'None')
                        st.info("🖼️ Sin imagen")
                        
                    # 3. Datos del producto
                    st.markdown(f"**{row['nombre']}**")
                    st.caption(f"{row['id']} | {row['marca']}")
                    
                    c1, c2 = st.columns(2)
                    c1.metric("Stock", row['stock'])
                    c2.metric("Precio", f"S/. {row['precio']}")
                    
                    if row['m2_caja'] > 0:
                        st.success(f"📦 Total: {row['total_m2']:.2f} m²")
                    
                    st.divider()
                    
    # 2. REGISTRAR (INSERTAR EN SUPABASE)
    elif menu == "Registrar Nuevo":
        st.subheader("📝 Nuevo Producto")
        cat = st.selectbox("Categoría:", ["Mayólica", "Porcelanato", "Piso", "Pared", "Pegamento", "Fragua", "Sanitario", "Grifería"])
        
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
                m2_val = c4.number_input("m² por Caja", min_value=0.01)
            else:
                fmt_val = c3.text_input("Peso/Modelo")
            
            c5, c6 = st.columns(2)
            stk = c5.number_input("Stock Inicial", min_value=0, step=1)
            prc = c6.number_input("Precio S/.", min_value=0.0)
            
            f1 = st.file_uploader("Foto Pieza")
            f2 = st.file_uploader("Foto Ambiente (Opcional)")
            
            if st.form_submit_button("Guardar en Nube"):
                if not id_z or not nom: 
                    st.error("Faltan datos obligatorios")
                else:
                    # Verificar duplicado
                    existe = supabase.table("inventario").select("id").eq("id", id_z).execute()
                    if existe.data:
                        st.error("❌ Ese ID ya existe.")
                    else:
                        # Subir fotos
                        u1 = subir_a_supabase(f1.getvalue(), f1.name, f1.type) if f1 else ""
                        u2 = subir_a_supabase(f2.getvalue(), f2.name, f2.type) if f2 else ""
                        u_final = f"{u1},{u2}" if u2 else u1
                        
                        # INSERTAR EN BASE DE DATOS
                        data = {
                            "id": id_z, "nombre": nom, "categoria": cat, "marca": marca,
                            "formato": fmt_val, "m2_caja": m2_val, "calidad": "Estándar",
                            "stock": int(stk), "precio": float(prc), "imagen": u_final,
                            "tags_ia": f"{cat} {marca} {fmt_val}" # Auto-tag básico
                        }
                        supabase.table("inventario").insert(data).execute()
                        st.success("✅ Guardado en Supabase!")
                        time.sleep(1)
                        st.rerun()

    # 3. EDITAR (UPDATE)
    elif menu == "Editar Producto":
        st.subheader("✏️ Editar")
        opciones = df.apply(lambda x: f"{x['id']} | {x['nombre']}", axis=1)
        sel = st.selectbox("Buscar:", opciones)
        
        if sel:
            id_sel = sel.split(" | ")[0]
            # Recuperamos datos frescos de la BD para no editar sobre caché viejo
            item = supabase.table("inventario").select("*").eq("id", id_sel).execute().data[0]
            
            with st.form("edit"):
                n_nom = st.text_input("Nombre", item['nombre'])
                n_prc = st.number_input("Precio", value=float(item['precio']))
                n_m2 = st.number_input("m² Caja", value=float(item['m2_caja']))
                
                if st.form_submit_button("Actualizar"):
                    supabase.table("inventario").update({
                        "nombre": n_nom, "precio": n_prc, "m2_caja": n_m2
                    }).eq("id", id_sel).execute()
                    st.success("Actualizado")
                    st.rerun()

    # 4. ACTUALIZAR STOCK
    elif menu == "Actualizar Stock":
        st.subheader("📦 Ajuste Rápido")
        opciones = df.apply(lambda x: f"{x['id']} | {x['nombre']}", axis=1)
        sel = st.selectbox("Producto:", opciones)
        
        if sel:
            id_sel = sel.split(" | ")[0]
            item = supabase.table("inventario").select("stock").eq("id", id_sel).execute().data[0]
            actual = item['stock']
            
            st.metric("Stock en Sistema", actual)
            ajuste = st.number_input("Sumar / Restar:", step=1, value=0)
            
            if st.button("Aplicar Cambio"):
                nuevo = actual + ajuste
                supabase.table("inventario").update({"stock": nuevo}).eq("id", id_sel).execute()
                st.success(f"Nuevo stock: {nuevo}")
                time.sleep(0.5)
                st.rerun()

    # Módulos
    elif menu == "Calculadora Obra": calculadora_obra(df)
    elif menu == "Dashboard": dashboard_gerencial(df)
    elif menu == "Simulador 2.5D": simulador_25d(df)
    elif menu == "Consultor IA": consultor_ia(df)

if __name__ == "__main__":
    main()
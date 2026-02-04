import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import io
import math
import time
import plotly.express as px
from fpdf import FPDF
import base64
import google.generativeai as genai
from PIL import Image
import json

# --- 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(page_title="Inventario Ledisa v2", layout="wide", page_icon="🏗️")

st.markdown("""
    <style>
        div[data-testid="column"] img {
            height: 200px !important;
            object-fit: cover !important;
            border-radius: 8px;
            width: 100%;
        }
        .stButton>button {
            width: 100%;
        }
        .metric-box {
            padding: 10px;
            background-color: #f0f2f6;
            border-radius: 5px;
            text-align: center;
            margin-bottom: 10px;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONEXIÓN A GOOGLE SHEETS (ROBUSTA) ---
def conectar_google_sheets():
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        if "gcp_service_account" not in st.secrets:
            st.error("❌ No encuentro 'gcp_service_account' en secrets.toml")
            st.stop()
            
        secrets_dict = dict(st.secrets["gcp_service_account"])
        secrets_dict["private_key"] = secrets_dict["private_key"].replace("\\n", "\n")

        creds = Credentials.from_service_account_info(secrets_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        try:
            return client.open("Inventario").sheet1
        except:
            return client.open("inventario_db").sheet1

    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        st.stop()

def obtener_datos():
    hoja = conectar_google_sheets()
    if hoja:
        try:
            datos = hoja.get_all_values()
            if not datos: return pd.DataFrame(), hoja
            headers = datos.pop(0)
            df = pd.DataFrame(datos, columns=headers)
            
            # --- LIMPIEZA Y CÁLCULOS AUTOMÁTICOS ---
            # Aseguramos que los números sean números para poder multiplicar
            df['stock'] = pd.to_numeric(df['stock'], errors='coerce').fillna(0).astype(int)
            
            # Limpieza de m2_caja (cambiar comas por puntos si las hay)
            if 'm2_caja' in df.columns:
                df['m2_caja'] = df['m2_caja'].astype(str).str.replace(',', '.')
                df['m2_caja'] = pd.to_numeric(df['m2_caja'], errors='coerce').fillna(0.0)
            else:
                df['m2_caja'] = 0.0

            # CALCULO DE METRAJE TOTAL (Stock * m2/caja)
            df['total_m2'] = df['stock'] * df['m2_caja']
            
            return df, hoja
        except Exception as e:
            st.error(f"Error procesando datos: {e}")
            return pd.DataFrame(), hoja
    return pd.DataFrame(), None

# --- 3. SERVICIOS EXTERNOS (IMGBB) ---
def subir_a_imgbb(archivo_bytes, nombre):
    try:
        api_key = st.secrets["imgbb"]["key"]
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": api_key, "name": nombre}
        files = {"image": archivo_bytes}
        response = requests.post(url, data=payload, files=files)
        if response.status_code == 200:
            return response.json()['data']['url']
        else:
            return None
    except Exception as e:
        st.error(f"Error imagen: {e}")
        return None

# --- 4. CLASE PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'DISTRIBUIDORA DE ACABADOS LEDISA', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, 'Especialistas en Celima y Trebol', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

# --- 5. MÓDULOS DE LÓGICA ---

def calculadora_logica(df):
    st.subheader("🧮 Calculadora de Materiales PRO")
    st.markdown("---")
    
    df_calc = df[df['categoria'].isin(['Mayólica', 'Porcelanato', 'Piso', 'Pared', 'Cerámico', 'Mayolica'])]
    
    if df_calc.empty:
        st.warning("No hay productos de revestimiento registrados.")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        opciones = df_calc.apply(lambda x: f"{x['nombre']} ({x['formato']})", axis=1)
        producto_str = st.selectbox("1. Selecciona el Piso/Pared:", opciones)
        nombre_selec = producto_str.split(" (")[0]
        
        try:
            item = df_calc[df_calc['nombre'] == nombre_selec].iloc[0]
            rendimiento_caja = float(item['m2_caja'])
        except:
            rendimiento_caja = 0.0
            
        if rendimiento_caja == 0:
            st.warning("⚠️ Producto sin rendimiento (m²) configurado.")
        else:
            st.caption(f"✅ Rendimiento: {rendimiento_caja} m²/caja")

    with c2:
        if str(item['imagen']).startswith("http"):
            st.image(item['imagen'], width=150)

    st.markdown("### 2. Dimensiones y Precios")
    col_largo, col_ancho, col_precio = st.columns(3)
    largo = col_largo.number_input("Largo (m):", min_value=0.0, step=0.1)
    ancho = col_ancho.number_input("Ancho (m):", min_value=0.0, step=0.1)
    
    precio_bd = float(item['precio']) if item.get('precio') else 0.0
    precio_oferta = col_precio.number_input("Precio Unitario (S/.):", value=precio_bd, step=0.10)

    st.markdown("### 3. Configuración")
    c_merma, c_pegamento = st.columns(2)
    merma = c_merma.selectbox("Merma:", [0.05, 0.10, 0.15], index=1, format_func=lambda x: f"{int(x*100)}%")
    tipo_pegamento = c_pegamento.selectbox("Pegamento:", ["Estándar (Celima) - 25kg", "Trebol - 25kg"])
    rend_pegamento = 3.0 if "Estándar" in tipo_pegamento else 2.5
    
    area_real = largo * ancho
    if area_real > 0 and rendimiento_caja > 0:
        area_total = area_real * (1 + merma)
        cajas_necesarias = math.ceil(area_total / rendimiento_caja)
        metros_totales = cajas_necesarias * rendimiento_caja
        costo_total_cajas = cajas_necesarias * precio_oferta
        bolsas_pegamento = math.ceil(area_total / rend_pegamento)

        st.divider()
        st.success(f"📊 Requerimiento para {area_real:.2f} m² (+{int(merma*100)}% merma)")
        
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Cajas a Llevar", f"{cajas_necesarias} Cajas", f"{metros_totales:.2f} m² reales")
        kpi2.metric("Precio Unit", f"S/. {precio_oferta:.2f}")
        kpi3.metric("Total Piso", f"S/. {costo_total_cajas:,.2f}")
        
        st.info(f"🧱 Pegamento sugerido: **{bolsas_pegamento} bolsas**")

def dashboard_logica(df):
    st.subheader("📊 Tablero de Control Gerencial")
    st.markdown("---")
    if df.empty: return

    # Limpieza de precio
    def limpiar_precio(val):
        if isinstance(val, str):
            val = val.replace('S/.', '').replace(',', '').strip()
        return float(val) if val else 0.0
        
    df['precio_num'] = df['precio'].apply(limpiar_precio)
    df['valor_total'] = df['stock'] * df['precio_num']
    
    # KPIs Generales
    total_inventario_soles = df['valor_total'].sum()
    total_cajas = df['stock'].sum()
    total_m2_disponible = df['total_m2'].sum() # Nueva métrica solicitada

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("💰 Valor Inventario", f"S/. {total_inventario_soles:,.2f}")
    kpi2.metric("📦 Total Cajas/Unid.", f"{int(total_cajas)}")
    kpi3.metric("📐 Total Metros Cuadrados", f"{total_m2_disponible:,.2f} m²")
    
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 💵 Valor por Categoría")
        df_cat = df.groupby('categoria')['valor_total'].sum().reset_index()
        fig_cat = px.bar(df_cat, x='categoria', y='valor_total', color='valor_total', color_continuous_scale='Greens')
        st.plotly_chart(fig_cat, use_container_width=True)
    with c2:
        st.markdown("##### 🏭 Stock (Cajas) por Marca")
        df_marca = df.groupby('marca')['stock'].sum().reset_index()
        fig_pie = px.pie(df_marca, values='stock', names='marca', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

    # Tabla de productos con más m2
    st.subheader("🏆 Top Productos con más Metraje Disponible")
    top_m2 = df[['nombre', 'stock', 'm2_caja', 'total_m2']].sort_values(by='total_m2', ascending=False).head(10)
    st.dataframe(top_m2, use_container_width=True)

def cotizador_logica(df):
    st.subheader("📄 Generador de Cotizaciones")
    if 'carrito' not in st.session_state: st.session_state.carrito = []

    col_sel, col_res = st.columns([1, 1])
    with col_sel:
        # Solo productos con stock
        df_venta = df[df['stock'] > 0]
        opciones = df_venta.apply(lambda x: f"{x['id']} | {x['nombre']}", axis=1)
        producto_str = st.selectbox("Buscar Producto:", opciones, key="sel_prod_cot")
        
        if producto_str:
            id_sel = producto_str.split(" | ")[0]
            item = df[df['id'].astype(str) == id_sel].iloc[0]
            
            # Mostrar info rápida
            st.info(f"Stock actual: {item['stock']} cajas ({item['total_m2']:.2f} m²)")
            
            c1, c2 = st.columns(2)
            cantidad = c1.number_input("Cantidad (Cajas/Unid):", min_value=1, value=1)
            precio_venta = c2.number_input("Precio Final (S/.):", value=float(item['precio'] or 0), min_value=0.0)
            
            if st.button("➕ Agregar a Cotización"):
                # Calculamos m2 si aplica
                m2_total_item = cantidad * item['m2_caja']
                desc = f"{item['nombre']} ({item['marca']})"
                if item['m2_caja'] > 0:
                    desc += f" - [{m2_total_item:.2f} m²]"

                linea = {
                    "descripcion": desc,
                    "cantidad": cantidad,
                    "precio_unit": precio_venta,
                    "subtotal": cantidad * precio_venta
                }
                st.session_state.carrito.append(linea)
                st.success("Agregado")

    with col_res:
        if len(st.session_state.carrito) > 0:
            df_carrito = pd.DataFrame(st.session_state.carrito)
            st.dataframe(df_carrito, hide_index=True)
            total = df_carrito['subtotal'].sum()
            st.metric("Total Cotización", f"S/. {total:,.2f}")
            
            if st.button("🗑️ Limpiar Carrito"):
                st.session_state.carrito = []
                st.rerun()
            
            cliente = st.text_input("Cliente:")
            dni = st.text_input("DNI/RUC:")
            
            if st.button("🖨️ Generar PDF") and cliente:
                pdf = PDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                pdf.cell(0, 10, f"Cliente: {cliente} - {dni}", ln=True)
                pdf.cell(0, 10, f"Fecha: {pd.Timestamp.now().strftime('%d/%m/%Y')}", ln=True)
                pdf.ln(5)
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(100, 10, "Descripcion", 1); pdf.cell(30, 10, "Cant", 1); pdf.cell(30, 10, "Total", 1); pdf.ln()
                pdf.set_font("Arial", size=10)
                for p in st.session_state.carrito:
                    pdf.cell(100, 10, str(p['descripcion'])[:50], 1)
                    pdf.cell(30, 10, str(p['cantidad']), 1)
                    pdf.cell(30, 10, f"{p['subtotal']:.2f}", 1)
                    pdf.ln()
                pdf.cell(160, 10, f"TOTAL: S/. {total:.2f}", 1, 0, 'R')
                
                b64 = base64.b64encode(pdf.output(dest='S').encode('latin-1')).decode()
                href = f'<a href="data:application/pdf;base64,{b64}" download="Cotizacion.pdf">📥 Descargar PDF</a>'
                st.markdown(href, unsafe_allow_html=True)

# --- 6. CONSULTOR IA (VERSIÓN FLASH LATEST) ---
def consultor_ia(df):
    st.header("🤖 Consultor de Ventas IA")
    st.info("Buscando en tu inventario...")
    
    # Verificación de datos
    if 'tags_ia' not in df.columns:
        st.error("⚠️ Falta la columna 'tags_ia' en tu Excel.")
        return

    # Usamos SOLO el modelo que te funcionó
    modelo_elegido = 'models/gemini-flash-latest'

    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
        model = genai.GenerativeModel(modelo_elegido)
    except Exception as e:
        st.error(f"Error configuración IA: {e}")
        return

    # Contexto
    items = df[df['tags_ia'].astype(str).str.len() > 3]
    # Filtramos para no saturar, enviamos ID, Nombre, Tags y m2_caja para que la IA sepa el rendimiento
    inv = items[['id', 'nombre', 'tags_ia', 'm2_caja']].head(100).to_dict(orient='records')
    inv_json = json.dumps(inv, ensure_ascii=False)

    query = st.chat_input("Escribe el requerimiento del cliente...")
    
    if query:
        with st.chat_message("user"): st.write(query)
        
        with st.chat_message("assistant"):
            status = st.status(f"🧠 Conectando con {modelo_elegido}...", expanded=True)
            
            prompt = f"""
            Eres un vendedor experto de pisos. Recomienda 3 productos para: "{query}".
            INVENTARIO: {inv_json}
            
            Responde SOLO JSON válido (sin markdown):
            {{
                "recomendaciones": [
                    {{ "id": "ID_EXACTO", "razon": "Motivo breve" }}
                ],
                "consejo": "Tip breve"
            }}
            """
            
            try:
                response = model.generate_content(prompt)
                
                # Limpieza de respuesta
                texto = response.text.replace("```json", "").replace("```", "").strip()
                if "{" in texto: texto = texto[texto.find("{"):texto.rfind("}")+1]
                
                data = json.loads(texto)
                status.update(label="✅ Éxito", state="complete", expanded=False)
                
                recs = data.get('recomendaciones', [])
                if not recs:
                    st.warning("No encontré coincidencias.")
                else:
                    st.subheader("🏆 Recomendaciones:")
                    cols = st.columns(3)
                    for i, r in enumerate(recs):
                        id_str = str(r['id']).strip()
                        prod = df[df['id'].astype(str).str.strip() == id_str]
                        with cols[i%3]:
                            if not prod.empty:
                                row = prod.iloc[0]
                                if str(row['imagen']).startswith("http"):
                                    st.image(row['imagen'])
                                st.markdown(f"**{row['nombre']}**")
                                st.caption(r['razon'])
                                # Mostrar rendimiento también aquí
                                if row['m2_caja'] > 0:
                                    st.text(f"Rendimiento: {row['m2_caja']} m²/cj")
                            else:
                                st.error(f"ID {id_str} no encontrado.")
                    
                    if 'consejo' in data: st.info(f"💡 {data['consejo']}")

            except Exception as e:
                status.update(label="❌ Error", state="error")
                st.error(f"Error: {e}")

# --- 7. LOGIN ---
def sidebar_login():
    st.sidebar.title("🔐 Acceso")
    if st.session_state.get('password_correct', False):
        st.sidebar.success("ADMINISTRADOR")
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state['password_correct'] = False
            st.rerun()
        return True
    else:
        st.sidebar.info("Modo: VISITANTE")
        with st.sidebar.form("login"):
            pwd = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar"):
                if pwd == st.secrets["general"]["password"]:
                    st.session_state['password_correct'] = True
                    st.rerun()
                else:
                    st.error("Incorrecto")
        return False

# --- 8. EJECUCIÓN PRINCIPAL ---
def main():
    es_admin = sidebar_login()
    st.title("🏭 Sistema Inventario Ledisa v2.5")
    
    # Menú (Sin auto-etiquetado)
    opciones = ["Ver Inventario", "Calculadora de Obra"]
    if es_admin:
        opciones += ["Cotizador PDF", "Dashboard", "Registrar Nuevo", "Editar Completo", "Actualizar Stock", "Consultor IA"]
    
    menu = st.sidebar.radio("Navegación:", opciones)
    df, hoja = obtener_datos()

    # ---------------------------------------------------------
    # 1. VER INVENTARIO (CON DESPLIEGUE DE M2)
    # ---------------------------------------------------------
    if menu == "Ver Inventario":
        busqueda = st.text_input("🔍 Buscar:", placeholder="Nombre, código o marca...")
        
        if not df.empty and busqueda:
            df = df[df.astype(str).apply(lambda x: x.str.contains(busqueda, case=False)).any(axis=1)]
        
        if not df.empty:
            st.caption(f"Mostrando {len(df)} productos.")
            cols = st.columns(3)
            for i, row in df.iterrows():
                with cols[i % 3]:
                    st.container()
                    if str(row['imagen']).startswith("http"): st.image(row['imagen'])
                    st.markdown(f"**{row['nombre']}**")
                    
                    # DATOS CLAVE
                    st.markdown(f"🆔 `{row['id']}` | 🏷️ {row['marca']}")
                    
                    c1, c2 = st.columns(2)
                    c1.metric("Stock Cajas", row['stock'])
                    c2.metric("Precio", f"S/. {row['precio']}")
                    
                    # CÁLCULO M2 VISIBLE
                    if row['m2_caja'] > 0:
                        st.markdown(f"📦 **{row['m2_caja']} m²/caja**")
                        # Destacamos el total disponible
                        st.success(f"📐 Total: **{row['total_m2']:.2f} m²**")
                    else:
                        st.text("Unidad (Sin m²)")
                        
                    st.divider()
        else:
            st.warning("No hay productos.")

    # ---------------------------------------------------------
    # 2. CALCULADORA
    # ---------------------------------------------------------
    elif menu == "Calculadora de Obra": calculadora_logica(df)
    
    # ---------------------------------------------------------
    # 3. DASHBOARD
    # ---------------------------------------------------------
    elif menu == "Dashboard": dashboard_logica(df)
    
    # ---------------------------------------------------------
    # 4. COTIZADOR
    # ---------------------------------------------------------
    elif menu == "Cotizador PDF": cotizador_logica(df)
    
    # ---------------------------------------------------------
    # 5. CONSULTOR IA (FIXED)
    # ---------------------------------------------------------
    elif menu == "Consultor IA": consultor_ia(df)
    
    # ---------------------------------------------------------
    # 6. REGISTRAR NUEVO (CON CÓDIGO SAP MANUAL)
    # ---------------------------------------------------------
    elif menu == "Registrar Nuevo":
        st.subheader("📝 Ingreso de Mercadería")
        with st.form("new_prod"):
            # FILA 1: ID y Marca
            c1, c2 = st.columns(2)
            id_zap = c1.text_input("Código SAP / ID *", help="Ingresa el código manual")
            marca = c2.selectbox("Marca", ["Celima", "Trebol", "Generico", "Otro"])
            
            # FILA 2: Nombre y Categoría
            c3, c4 = st.columns(2)
            nombre = c3.text_input("Descripción del Producto *")
            cat = c4.selectbox("Categoría", ["Mayólica", "Porcelanato", "Piso", "Pared", "Pegamento", "Fragua", "Sanitario"])
            
            # FILA 3: Formato y M2
            c5, c6 = st.columns(2)
            fmt = c5.text_input("Formato (Ej: 60x60)")
            m2 = c6.number_input("Rendimiento (m² por caja)", 0.0, step=0.01)
            
            # FILA 4: Calidad y Stock
            c7, c8 = st.columns(2)
            calidad = c7.selectbox("Calidad", ["Comercial", "Extra", "Única", "Estándar"])
            stk = c8.number_input("Stock Inicial (Cajas/Unid)", min_value=0, step=1)
            
            # FILA 5: Precio y Foto
            c9, c10 = st.columns(2)
            prc = c9.number_input("Precio Unitario", 0.0, step=0.1)
            img = c10.file_uploader("Foto del Producto")
            
            if st.form_submit_button("Guardar Producto"):
                if not id_zap or not nombre:
                    st.error("Falta ID o Nombre.")
                else:
                    # Verificar duplicados
                    if id_zap in df['id'].astype(str).values:
                        st.error(f"Error: El código {id_zap} ya existe.")
                    else:
                        url = ""
                        if img: 
                            with st.spinner("Subiendo foto..."):
                                url = subir_a_imgbb(img.getvalue(), nombre)
                        
                        # Orden Columnas: ID, Nombre, Categoria, Marca, Formato, M2, Calidad, Stock, Precio, Imagen
                        # Asegúrate que tu Excel tenga estas columnas en este orden
                        row = [id_zap, nombre, cat, marca, fmt, m2, calidad, stk, prc, url]
                        hoja.append_row(row)
                        st.success(f"✅ Registrado: {nombre}")
                        time.sleep(1)
                        st.rerun()

    # ---------------------------------------------------------
    # 7. EDITAR COMPLETO (RESTAURADO)
    # ---------------------------------------------------------
    elif menu == "Editar Completo":
        st.subheader("✏️ Edición Total de Producto")
        
        item_sel = st.selectbox("Selecciona Producto a Editar:", df['id'] + " | " + df['nombre'])
        if item_sel:
            id_sel = item_sel.split(" | ")[0]
            # Localizar fila
            idx = df[df['id'].astype(str) == id_sel].index[0]
            row = df.iloc[idx]
            fila_sheet = idx + 2 # +1 por header, +1 por index 0
            
            with st.form("edit_full"):
                st.info(f"Editando: {row['nombre']}")
                
                # Campos editables
                c1, c2 = st.columns(2)
                n_nombre = c1.text_input("Nombre", value=row['nombre'])
                n_marca = c2.text_input("Marca", value=row['marca'])
                
                c3, c4 = st.columns(2)
                n_cat = c3.selectbox("Categoría", ["Mayólica", "Porcelanato", "Piso", "Pared", "Pegamento", "Sanitario"], index=0) # Simplificado index
                n_fmt = c4.text_input("Formato", value=row['formato'])
                
                c5, c6 = st.columns(2)
                n_m2 = c5.number_input("m²/caja", value=float(row['m2_caja']), step=0.01)
                n_precio = c6.number_input("Precio", value=float(row['precio']), step=0.1)
                
                c7, c8 = st.columns(2)
                # Calidad
                n_cal = c7.text_input("Calidad", value=row['calidad'])
                # Foto
                n_foto = c8.file_uploader("Cambiar Foto (Opcional)")

                if st.form_submit_button("💾 Guardar Cambios"):
                    # URL Imagen
                    url_fin = row['imagen']
                    if n_foto:
                        url_fin = subir_a_imgbb(n_foto.getvalue(), n_nombre)
                    
                    # Actualizar celda por celda o rango (Orden A-J)
                    # ID no se cambia (Col 1)
                    # Col 2: Nombre
                    hoja.update_cell(fila_sheet, 2, n_nombre)
                    hoja.update_cell(fila_sheet, 3, n_cat)
                    hoja.update_cell(fila_sheet, 4, n_marca)
                    hoja.update_cell(fila_sheet, 5, n_fmt)
                    hoja.update_cell(fila_sheet, 6, n_m2)
                    hoja.update_cell(fila_sheet, 7, n_cal)
                    # Stock (Col 8) lo dejamos quieto aquí, se usa Actualizar Stock
                    hoja.update_cell(fila_sheet, 9, n_precio)
                    hoja.update_cell(fila_sheet, 10, url_fin)
                    
                    st.success("Producto actualizado correctamente.")
                    time.sleep(1)
                    st.rerun()

    # ---------------------------------------------------------
    # 8. ACTUALIZAR STOCK (RÁPIDO)
    # ---------------------------------------------------------
    elif menu == "Actualizar Stock":
        st.subheader("📦 Ajuste Rápido de Inventario")
        item_sel = st.selectbox("Producto:", df['id'] + " | " + df['nombre'])
        id_sel = item_sel.split(" | ")[0]
        row = df[df['id'].astype(str) == id_sel].iloc[0]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Stock Actual", f"{row['stock']} Cajas")
        c2.metric("m² Totales", f"{row['total_m2']:.2f} m²")
        
        ajuste = c3.number_input("Sumar/Restar Cajas:", step=1, value=0)
        
        if st.button("Aplicar Ajuste"):
            idx = df[df['id'].astype(str) == id_sel].index[0]
            fila_sheet = idx + 2
            nuevo_stock = int(row['stock']) + ajuste
            hoja.update_cell(fila_sheet, 8, nuevo_stock) # Col 8 es Stock
            st.success(f"Nuevo stock: {nuevo_stock}")
            time.sleep(0.5)
            st.rerun()

if __name__ == "__main__":
    main()
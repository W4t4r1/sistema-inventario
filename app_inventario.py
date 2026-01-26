import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import io
import math # <--- IMPORTANTE PARA LA CALCULADORA
import time
import plotly.express as px
from fpdf import FPDF
import base64

# --- CONFIGURACIÓN Y CSS HACK ---
st.set_page_config(page_title="Inventario Ledisa", layout="wide", page_icon="🏗️")

st.markdown("""
    <style>
        div[data-testid="column"] img {
            height: 250px !important;
            object-fit: cover !important;
            border-radius: 8px;
            width: 100%;
        }
    </style>
""", unsafe_allow_html=True)

# --- CONEXIÓN GOOGLE SHEETS ---
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        # 1. Cargamos el diccionario de secretos
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        # 2. ARREGLO DEL ERROR PEM: Reemplazamos los saltos de línea escapados
        # Esto arregla el error "InvalidHeader" si los \n se leyeron mal
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

        # 3. Creamos las credenciales con el diccionario corregido
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open("inventario_db").sheet1
    except Exception as e:
        st.error(f"⚠️ Error conectando a Google Sheets: {e}")
        return None

# --- FUNCIÓN IMGBB ---
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
            st.error(f"Error ImgBB: {response.text}")
            return None
    except Exception as e:
        st.error(f"Error subiendo imagen: {e}")
        return None

def obtener_datos():
    hoja = conectar_google_sheets()
    if hoja:
        try:
            datos = hoja.get_all_values()
            if not datos: return pd.DataFrame(), hoja
            headers = datos.pop(0)
            return pd.DataFrame(datos, columns=headers), hoja
        except Exception:
            return pd.DataFrame(), hoja
    return pd.DataFrame(), None

# --- BARRA LATERAL DE LOGIN ---
def sidebar_login():
    st.sidebar.title("🔐 Acceso")
    if st.session_state.get('password_correct', False):
        st.sidebar.success("Modo: ADMINISTRADOR")
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state['password_correct'] = False
            st.rerun()
        return True
    else:
        st.sidebar.info("Modo: VISITANTE")
        st.sidebar.markdown("---")
        st.sidebar.subheader("Ingreso Administrativo")
        with st.sidebar.form("login_form"):
            password_input = st.text_input("Contraseña:", type="password")
            if st.form_submit_button("Ingresar"):
                try:
                    if password_input == st.secrets["general"]["password"]:
                        st.session_state['password_correct'] = True
                        st.rerun()
                    else:
                        st.error("❌ Contraseña incorrecta")
                except KeyError:
                    st.error("⚠️ Error de configuración de secretos")
        return False

# --- MÓDULO: CALCULADORA DE OBRA (VERSIÓN PRO) ---
def calculadora_logica(df):
    st.subheader("🧮 Calculadora de Materiales PRO")
    st.markdown("---")
    
    # 1. FILTRO DE PRODUCTOS
    df_calc = df[df['categoria'].isin(['Mayólica', 'Porcelanato', 'Piso', 'Pared', 'Cerámico', 'Mayolica'])]
    
    if df_calc.empty:
        st.warning("No hay productos de revestimiento registrados.")
        return

    c1, c2 = st.columns([2, 1])
    
    with c1:
        # SELECTOR DE PRODUCTO
        opciones = df_calc.apply(lambda x: f"{x['nombre']} ({x['formato']})", axis=1)
        producto_str = st.selectbox("1. Selecciona el Piso/Pared:", opciones)
        
        nombre_selec = producto_str.split(" (")[0]
        try:
            item = df_calc[df_calc['nombre'] == nombre_selec].iloc[0]
            rendimiento_caja = float(item['m2_caja']) if item.get('m2_caja') and str(item['m2_caja']).replace('.','',1).isdigit() else 0.0
        except:
            rendimiento_caja = 0.0
            
        if rendimiento_caja == 0:
            st.error("⚠️ Producto sin rendimiento (m²) configurado.")
            st.stop()
        else:
            st.caption(f"✅ Rendimiento: {rendimiento_caja} m²/caja")

    with c2:
        # FOTO DEL PRODUCTO
        if item['imagen'] and item['imagen'].startswith("http"):
            st.image(item['imagen'], width=150)

    st.markdown("### 2. Dimensiones y Precios")
    
    # --- ÁREA DE INPUTS (DIMENSIONES + PRECIO EDITABLE) ---
    col_largo, col_ancho, col_precio = st.columns(3)
    
    largo = col_largo.number_input("Largo (m):", min_value=0.0, step=0.1)
    ancho = col_ancho.number_input("Ancho (m):", min_value=0.0, step=0.1)
    
    # PRECIO EDITABLE: Cargamos el de la BD por defecto, pero permitimos cambiarlo
    precio_bd = float(item['precio']) if item.get('precio') else 0.0
    precio_oferta = col_precio.number_input("Precio Unitario (S/.):", value=precio_bd, step=0.10, help="Puedes modificar este precio solo para este cálculo")

    # --- ÁREA DE CONFIGURACIÓN TÉCNICA ---
    st.markdown("### 3. Configuración de Materiales")
    c_merma, c_pegamento, c_fragua = st.columns(3)
    
    merma = c_merma.selectbox("Merma (Cortes):", [0.05, 0.10, 0.15], index=1, format_func=lambda x: f"{int(x*100)}%")
    
    # LÓGICA DE PEGAMENTOS (TU REQUERIMIENTO)
    tipo_pegamento = c_pegamento.selectbox(
        "Tipo de Pegamento:", 
        ["Estándar (Celima/Master) - 25kg", "Trebol - 25kg"],
        help="El Trebol rinde menos (aprox 2.5 m²)"
    )
    # Definimos rendimiento según selección
    rend_pegamento = 3.0 if "Estándar" in tipo_pegamento else 2.5
    
    # LÓGICA DE FRAGUA (TU REQUERIMIENTO)
    rend_fragua = 3.5 # Estándar para cruceta 3mm
    c_fragua.info(f"Fragua: 1 bolsa / {rend_fragua} m² (Cruceta 3mm)")
    
    # --- CÁLCULOS MATEMÁTICOS ---
    area_real = largo * ancho
    
    if area_real > 0:
        area_total = area_real * (1 + merma)
        
        # 1. Cajas
        cajas_necesarias = math.ceil(area_total / rendimiento_caja)
        metros_totales = cajas_necesarias * rendimiento_caja
        costo_total_cajas = cajas_necesarias * precio_oferta
        
        # 2. Pegamento
        bolsas_pegamento = math.ceil(area_total / rend_pegamento)
        
        # 3. Fragua
        bolsas_fragua = math.ceil(area_total / rend_fragua)

        # --- RESULTADOS VISUALES ---
        st.divider()
        st.success(f"📊 Presupuesto para {area_real:.2f} m² (+{int(merma*100)}% merma)")
        
        # FILA 1: CERÁMICO PRINCIPAL
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Cajas a Llevar", f"{cajas_necesarias} Cajas", f"{metros_totales:.2f} m² reales")
        kpi2.metric("Precio Unitario", f"S/. {precio_oferta:.2f}", delta_color="off")
        kpi3.metric("Total Cerámico", f"S/. {costo_total_cajas:,.2f}")
        
        # FILA 2: COMPLEMENTOS EXACTOS
        st.subheader("Complementos Sugeridos")
        sug1, sug2 = st.columns(2)
        
        with sug1:
            st.markdown(f"🧱 **Pegamento ({tipo_pegamento}):**")
            st.write(f"Necesitas: **{bolsas_pegamento} bolsas**")
            st.caption(f"Cálculo base: {area_total:.2f} m² / {rend_pegamento}")
            
        with sug2:
            st.markdown(f"✨ **Fragua:**")
            st.write(f"Necesitas: **{bolsas_fragua} bolsas**")
            st.caption(f"Cálculo base: {area_total:.2f} m² / {rend_fragua}")

    else:
        st.info("👈 Ingresa las medidas para calcular.")
        
# --- MÓDULO: DASHBOARD BI (NUEVO) ---
def dashboard_logica(df):
    st.subheader("📊 Tablero de Control Gerencial")
    st.markdown("---")

    if df.empty:
        st.warning("No hay datos para analizar.")
        return

    # 1. LIMPIEZA DE DATOS (CRÍTICO PARA GRÁFICOS)
    # Convertimos stock y precio a números, forzando errores a 0
    df['stock_num'] = pd.to_numeric(df['stock'], errors='coerce').fillna(0)
    
    # Limpieza del precio (quitar 'S/.', espacios, etc)
    # Asumimos que el precio está en columna 'precio'
    def limpiar_precio(val):
        if isinstance(val, str):
            val = val.replace('S/.', '').replace(',', '').strip()
        return float(val) if val else 0.0
        
    df['precio_num'] = df['precio'].apply(limpiar_precio)
    
    # Calculamos Valor Total por Producto
    df['valor_total'] = df['stock_num'] * df['precio_num']

    # 2. TARJETAS KPI (INDICADORES CLAVE)
    total_inventario = df['valor_total'].sum()
    total_items = df['stock_num'].sum()
    total_skus = len(df) # Cantidad de productos únicos

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("💰 Valor del Inventario", f"S/. {total_inventario:,.2f}")
    kpi2.metric("📦 Unidades Físicas", f"{int(total_items)}")
    kpi3.metric("🔖 Productos Únicos (SKUs)", total_skus)
    
    st.divider()

    # 3. GRÁFICOS INTERACTIVOS
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("##### 💵 Dinero Inmovilizado por Categoría")
        # Agrupamos por categoría y sumamos el valor
        df_cat = df.groupby('categoria')['valor_total'].sum().reset_index()
        fig_cat = px.bar(df_cat, x='categoria', y='valor_total', 
                         text_auto='.2s', 
                         color='valor_total',
                         color_continuous_scale='Greens')
        fig_cat.update_layout(xaxis_title="", yaxis_title="Soles (S/.)")
        st.plotly_chart(fig_cat, use_container_width=True)

    with c2:
        st.markdown("##### 🏭 Distribución de Stock por Marca")
        # Contamos cuántos productos hay de cada marca
        df_marca = df.groupby('marca')['stock_num'].sum().reset_index()
        fig_pie = px.pie(df_marca, values='stock_num', names='marca', 
                         hole=0.4, # Hace que sea una dona
                         color_discrete_sequence=px.colors.qualitative.Set2)
        st.plotly_chart(fig_pie, use_container_width=True)

    # 4. ALERTA DE STOCK CRÍTICO (BAJO INVENTARIO)
    st.subheader("🚨 Alerta: Stock Crítico (< 10 unidades)")
    bajostock = df[df['stock_num'] < 10][['id', 'nombre', 'marca', 'stock']]
    
    if not bajostock.empty:
        st.dataframe(bajostock, use_container_width=True, hide_index=True)
    else:
        st.success("✅ Todo el inventario tiene niveles saludables.")

# --- CLASE PDF PERSONALIZADA ---
class PDF(FPDF):
    def header(self):
        # Título / Logo (Texto simple por ahora para evitar errores de imagen)
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'DISTRIBUIDORA DE ACABADOS LEDISA', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, 'Especialistas en Celima y Trebol', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

# --- MÓDULO: COTIZADOR PDF ---
def cotizador_logica(df):
    st.subheader("📄 Generador de Cotizaciones")
    st.markdown("---")

    # 1. INICIALIZAR CARRITO EN MEMORIA
    if 'carrito' not in st.session_state:
        st.session_state.carrito = []

    # 2. SELECCIÓN DE PRODUCTOS (LADO IZQUIERDO)
    col_sel, col_res = st.columns([1, 1])

    with col_sel:
        st.info("1. Agregar Productos")
        # Filtramos productos con stock > 0 para vender
        df_venta = df[df['stock'].astype(float) > 0]
        
        opciones = df_venta.apply(lambda x: f"{x['id']} | {x['nombre']} - S/. {x['precio']}", axis=1)
        producto_str = st.selectbox("Buscar Producto:", opciones, key="sel_prod_cot")
        
        if producto_str:
            id_sel = producto_str.split(" | ")[0]
            item = df[df['id'].astype(str) == id_sel].iloc[0]
            
            c1, c2 = st.columns(2)
            cantidad = c1.number_input("Cantidad:", min_value=1, value=1)
            precio_venta = c2.number_input("Precio Final (S/.):", value=float(item['precio']), min_value=0.0)
            
            if st.button("➕ Agregar a la Cotización"):
                # Agregamos al carrito
                linea = {
                    "id": item['id'],
                    "descripcion": f"{item['nombre']} ({item['marca']})",
                    "cantidad": cantidad,
                    "precio_unit": precio_venta,
                    "subtotal": cantidad * precio_venta
                }
                st.session_state.carrito.append(linea)
                st.success("Producto agregado")

    # 3. REVISIÓN Y DATOS CLIENTE (LADO DERECHO)
    with col_res:
        st.warning("2. Revisar y Generar")
        
        # Mostrar Tabla de Carrito
        if len(st.session_state.carrito) > 0:
            df_carrito = pd.DataFrame(st.session_state.carrito)
            st.dataframe(df_carrito[['descripcion', 'cantidad', 'precio_unit', 'subtotal']], hide_index=True)
            
            total_cotizacion = df_carrito['subtotal'].sum()
            st.metric("Total a Cotizar", f"S/. {total_cotizacion:,.2f}")
            
            if st.button("🗑️ Limpiar Carrito"):
                st.session_state.carrito = []
                st.rerun()
                
            st.markdown("---")
            cliente = st.text_input("Nombre del Cliente:")
            dni = st.text_input("DNI / RUC:")
            
            if st.button("🖨️ DESCARGAR PDF"):
                if not cliente:
                    st.error("Falta nombre del cliente")
                else:
                    # --- GENERACIÓN DEL PDF ---
                    pdf = PDF()
                    pdf.add_page()
                    pdf.set_font("Arial", size=12)
                    
                    # Datos Cliente
                    pdf.cell(0, 10, f"Cliente: {cliente}", ln=True)
                    pdf.cell(0, 10, f"DNI/RUC: {dni}", ln=True)
                    pdf.cell(0, 10, f"Fecha: {pd.Timestamp.now().strftime('%d/%m/%Y')}", ln=True)
                    pdf.ln(10)
                    
                    # Encabezados Tabla
                    pdf.set_font("Arial", 'B', 10)
                    pdf.cell(100, 10, "Descripción", 1)
                    pdf.cell(30, 10, "Cant.", 1, 0, 'C')
                    pdf.cell(30, 10, "P.Unit", 1, 0, 'C')
                    pdf.cell(30, 10, "Total", 1, 0, 'C')
                    pdf.ln()
                    
                    # Filas
                    pdf.set_font("Arial", size=10)
                    for p in st.session_state.carrito:
                        pdf.cell(100, 10, str(p['descripcion'])[:50], 1) # Cortamos nombre largo
                        pdf.cell(30, 10, str(p['cantidad']), 1, 0, 'C')
                        pdf.cell(30, 10, f"{p['precio_unit']:.2f}", 1, 0, 'R')
                        pdf.cell(30, 10, f"{p['subtotal']:.2f}", 1, 0, 'R')
                        pdf.ln()
                    
                    # Total
                    pdf.set_font("Arial", 'B', 12)
                    pdf.cell(160, 10, "TOTAL S/.", 1, 0, 'R')
                    pdf.cell(30, 10, f"{total_cotizacion:.2f}", 1, 0, 'R')
                    
                    # Guardar en memoria (buffer)
                    # FPDF devuelve string en latin-1, necesitamos bytes para streamlit
                    pdf_output = pdf.output(dest='S').encode('latin-1')
                    
                    # Botón de descarga real
                    b64 = base64.b64encode(pdf_output).decode()
                    href = f'<a href="data:application/octet-stream;base64,{b64}" download="Cotizacion_{cliente}.pdf" style="text-decoration:none;">' \
                           f'<button style="background-color:#FF4B4B;color:white;padding:10px;border:none;border-radius:5px;cursor:pointer;">' \
                           f'📥 Clic aquí para guardar PDF</button></a>'
                    st.markdown(href, unsafe_allow_html=True)
                    
        else:
            st.caption("El carrito está vacío.")

# --- FRONTEND PRINCIPAL ---
def main():
    es_admin = sidebar_login()
    st.title("🏭 Inventario: Celima & Trebol")
    
    if es_admin:
        # Nuevo orden sugerido
        menu = ["Ver Inventario", "Cotizador PDF", "Calculadora de Obra", "Dashboard Gerencial", "Registrar Nuevo", "Editar Detalles", "Actualizar Stock"]
    else:
        menu = ["Ver Inventario", "Calculadora de Obra"]

    choice = st.sidebar.selectbox("Navegación", menu)
    df, hoja = obtener_datos()

    # --- 1. VER INVENTARIO ---
    if choice == "Ver Inventario":
        col1, col2 = st.columns([3,1])
        with col1: st.subheader("📦 Stock Disponible")
        with col2: 
            if st.button("🔄 Actualizar Tabla"): st.rerun()

        busqueda = st.text_input("🔍 Buscar producto:")
        
        if not df.empty:
            if busqueda:
                mask = df.apply(lambda row: row.astype(str).str.contains(busqueda, case=False).any(), axis=1)
                df_filtered = df[mask]
            else:
                df_filtered = df
            
            st.caption(f"Mostrando {len(df_filtered)} productos.")
            cols = st.columns(3)
            for idx, row in df_filtered.iterrows():
                with cols[idx % 3]:
                    with st.container():
                        img_url = row['imagen']
                        if img_url and img_url.startswith("http"):
                            st.image(img_url)
                        else:
                            st.markdown('<div style="height: 250px; background-color: #eee; display: flex; align-items: center; justify-content: center; border-radius: 8px;">Sin Foto</div>', unsafe_allow_html=True)

                    st.markdown(f"**{row['nombre']}**")
                    # Mostramos m2 si existe
                    m2_txt = f" | {row['m2_caja']} m²/cj" if row.get('m2_caja') and row['m2_caja'] != "0" else ""
                    st.caption(f"ZAP: {row['id']} | {row['marca']}{m2_txt}")
                    st.metric("Stock", row['stock'], f"S/. {row['precio']}")
                    st.divider()
        else:
            st.warning("Inventario vacío.")

    # --- NUEVA OPCIÓN ---
    elif choice == "Dashboard Gerencial":
        if not es_admin: st.stop() # Doble seguridad
        dashboard_logica(df)

    # --- NUEVA OPCIÓN ---
    elif choice == "Cotizador PDF":
        if not es_admin: st.stop()
        cotizador_logica(df)

    # --- 2. CALCULADORA ---
    elif choice == "Calculadora de Obra":
        calculadora_logica(df)

    # --- 3. REGISTRAR ---
    elif choice == "Registrar Nuevo":
        if not es_admin: st.stop()
        st.subheader("📝 Nuevo Ingreso")
        with st.form("form_registro", clear_on_submit=True):
            c1, c2 = st.columns(2)
            id_zap = c1.text_input("Código ZAP (Opcional)")
            marca = c2.selectbox("Marca", ["Celima", "Trebol", "Generico", "Otro"])
            c3, c4 = st.columns(2)
            nombre = c3.text_input("Descripción *")
            categoria = c4.selectbox("Categoría", ["Mayólica", "Sanitario", "Grifería", "Pegamento", "Fragua"])
            
            c5, c6 = st.columns(2)
            formato = c5.text_input("Formato (Ej. 60x60)")
            # NUEVO CAMPO M2
            m2_caja = c6.number_input("Rendimiento (m² por caja)", min_value=0.0, step=0.01, help="Ej. 1.44 para 60x60")
            
            c7, c8 = st.columns(2)
            calidad = c7.selectbox("Calidad", ["Comercial", "Extra", "Única", "Estándar"])
            stock = c8.number_input("Stock Inicial", min_value=0)
            
            c9, c10 = st.columns(2)
            precio = c9.number_input("Precio Unitario", min_value=0.0, format="%.2f")
            foto = c10.file_uploader("Foto", type=['jpg','png','jpeg'])
            
            if st.form_submit_button("Guardar en Nube"):
                if nombre and hoja:
                    if id_zap and id_zap in df['id'].values:
                        st.error(f"Error: ZAP {id_zap} ya existe.")
                        st.stop()
                    
                    url_final = ""
                    if foto:
                        with st.spinner("Subiendo foto..."):
                            url_final = subir_a_imgbb(foto.getvalue(), nombre)
                    
                    final_id = id_zap.strip() if id_zap else f"INT-{pd.Timestamp.now().strftime('%M%S')}"
                    
                    # NUEVO ORDEN DE COLUMNAS (10 CAMPOS)
                    # id, nombre, cat, marca, fmt, M2, calidad, stock, precio, img
                    fila = [str(final_id), nombre, categoria, marca, formato, m2_caja, calidad, stock, precio, url_final]
                    
                    try:
                        hoja.append_row(fila)
                        st.success(f"✅ Registrado: {nombre}")
                    except Exception as e:
                        st.error(f"Error Google Sheets: {e}")
                else:
                    st.error("Falta Descripción")

    # --- 4. EDITAR ---
    elif choice == "Editar Detalles":
        if not es_admin: st.stop()
        st.subheader("✏️ Editar Producto")
        
        if df.empty: st.warning("Sin datos."); st.stop()
        
        opciones = df.apply(lambda x: f"{x['id']} | {x['nombre']}", axis=1)
        seleccion = st.selectbox("Buscar:", opciones)
        id_sel = seleccion.split(" | ")[0]
        
        idx = df.index[df['id'].astype(str) == id_sel].tolist()[0]
        fila_sheet = idx + 2
        datos = df.iloc[idx]

        with st.form("form_edicion"):
            c1, c2 = st.columns(2)
            st.text_input("ID", value=datos['id'], disabled=True)
            n_marca = c2.selectbox("Marca", ["Celima", "Trebol", "Generico", "Otro"], index=["Celima", "Trebol", "Generico", "Otro"].index(datos['marca']) if datos['marca'] in ["Celima", "Trebol", "Generico", "Otro"] else 3)
            
            c3, c4 = st.columns(2)
            n_nombre = c3.text_input("Nombre", value=datos['nombre'])
            cats = ["Mayólica", "Sanitario", "Grifería", "Pegamento", "Fragua"]
            n_cat = c4.selectbox("Categoría", cats, index=cats.index(datos['categoria']) if datos['categoria'] in cats else 0)
            
            c5, c6 = st.columns(2)
            n_fmt = c5.text_input("Formato", value=datos['formato'])
            # M2 SEGURO
            val_m2 = float(datos['m2_caja']) if datos.get('m2_caja') and datos['m2_caja'].replace('.','',1).isdigit() else 0.0
            n_m2 = c6.number_input("Rendimiento (m²)", value=val_m2, step=0.01)

            c7, c8 = st.columns(2)
            cals = ["Comercial", "Extra", "Única", "Estándar"]
            n_cal = c7.selectbox("Calidad", cals, index=cals.index(datos['calidad']) if datos['calidad'] in cals else 3)
            # STOCK NO EDITABLE AQUI
            st.text_input("Stock (Ver menú Actualizar)", value=datos['stock'], disabled=True)

            c9, c10 = st.columns(2)
            val_precio = float(datos['precio']) if datos.get('precio') and datos['precio'].replace('.','',1).isdigit() else 0.0
            n_precio = c9.number_input("Precio", value=val_precio)
            n_foto = c10.file_uploader("Nueva Foto (Opcional)", type=['jpg','png'])

            if st.form_submit_button("Guardar Cambios"):
                url_fin = datos['imagen']
                if n_foto:
                    with st.spinner("Actualizando foto..."):
                        url_fin = subir_a_imgbb(n_foto.getvalue(), n_nombre)

                # NUEVO ORDEN PARA UPDATE
                fila_new = [datos['id'], n_nombre, n_cat, n_marca, n_fmt, n_m2, n_cal, datos['stock'], n_precio, url_fin]
                
                try:
                    # Rango A hasta J (10 columnas)
                    rango = f"A{fila_sheet}:J{fila_sheet}"
                    hoja.update(range_name=rango, values=[fila_new])
                    st.success("✅ Actualizado")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# --- 5. ACTUALIZAR STOCK ---
    elif choice == "Actualizar Stock":
        if not es_admin: st.stop()
        st.subheader("🔄 Ajuste Stock")
        
        opciones = df.apply(lambda x: f"{x['id']} | {x['nombre']}", axis=1)
        seleccion = st.selectbox("Producto:", opciones)
        id_sel = seleccion.split(" | ")[0]
        
        idx = df.index[df['id'].astype(str) == id_sel].tolist()[0]
        fila_sheet = idx + 2
        item = df.iloc[idx]
        
        c1, c2 = st.columns([1,2])
        with c1:
            if item['imagen'].startswith("http"): st.image(item['imagen'])
        with c2:
            st.metric("Stock Actual", item['stock'])
            cambio = st.number_input("Ajuste (+/-):", step=1, value=0)
            
            if st.button("Aplicar"):
                nuevo = int(float(item['stock']) or 0) + cambio
                
                # CORRECCIÓN AQUÍ: Cambiamos 7 por 8
                # Col 1=ID, 2=Nom, 3=Cat, 4=Mar, 5=Fmt, 6=M2, 7=Cal, 8=STOCK
                hoja.update_cell(fila_sheet, 8, nuevo) 
                
                st.success("✅ Stock actualizado correctamente")
                time.sleep(0.5)
                st.rerun()

if __name__ == "__main__":
    main()
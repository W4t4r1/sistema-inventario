import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import io
import math # <--- IMPORTANTE PARA LA CALCULADORA
import time

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
        creds_dict = dict(st.secrets["gcp_service_account"])
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
        
# --- FRONTEND PRINCIPAL ---
def main():
    es_admin = sidebar_login()
    st.title("🏭 Inventario: Celima & Trebol")
    
    if es_admin:
        menu = ["Ver Inventario", "Calculadora de Obra", "Registrar Nuevo", "Editar Detalles", "Actualizar Stock"]
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
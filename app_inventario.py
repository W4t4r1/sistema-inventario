import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import io

# --- CONFIGURACIÓN Y CSS HACK PARA IMÁGENES ---
st.set_page_config(page_title="Inventario Ledisa", layout="wide", page_icon="🏗️")

# ESTE BLOQUE CSS FUERZA A LAS IMÁGENES A TENER EL MISMO TAMAÑO
st.markdown("""
    <style>
        /* Selecciona las imágenes dentro de las columnas de Streamlit */
        div[data-testid="column"] img {
            height: 250px !important; /* Altura fija para todas */
            object-fit: cover !important; /* Recorta la imagen para llenar el cuadro sin estirarse */
            border-radius: 8px; /* Un pequeño borde redondeado estético */
            width: 100%; /* Que ocupe todo el ancho de su columna */
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
        st.sidebar.info("Modo: VISITANTE (Solo lectura)")
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

# --- FRONTEND PRINCIPAL ---
def main():
    es_admin = sidebar_login()
    st.title("🏭 Inventario: Celima & Trebol")
    
    # MENÚ ACTUALIZADO CON NUEVA OPCIÓN
    if es_admin:
        menu = ["Ver Inventario", "Registrar Nuevo", "Editar Detalles", "Actualizar Stock"]
    else:
        menu = ["Ver Inventario"]

    choice = st.sidebar.selectbox("Navegación", menu)
    df, hoja = obtener_datos()

    # --- OPCIÓN 1: VER INVENTARIO ---
    if choice == "Ver Inventario":
        col1, col2 = st.columns([3,1])
        with col1: st.subheader("📦 Stock Disponible")
        with col2: 
            if st.button("🔄 Actualizar Tabla"): st.rerun()

        busqueda = st.text_input("🔍 Buscar producto (Nombre, Marca, ZAP):")
        
        if not df.empty:
            if busqueda:
                mask = df.apply(lambda row: row.astype(str).str.contains(busqueda, case=False).any(), axis=1)
                df_filtered = df[mask]
            else:
                df_filtered = df
            
            st.caption(f"Mostrando {len(df_filtered)} productos.")
            
            # Galería visual con CSS aplicado
            cols = st.columns(3)
            for idx, row in df_filtered.iterrows():
                with cols[idx % 3]:
                    # Usamos un contenedor para que el CSS aplique bien a la imagen dentro
                    with st.container():
                        img_url = row['imagen']
                        if img_url and img_url.startswith("http"):
                            st.image(img_url) # El CSS se encarga del tamaño
                        else:
                            # Placeholder si no hay imagen para mantener la grilla alineada
                            st.markdown('<div style="height: 250px; background-color: #f0f2f6; display: flex; align-items: center; justify-content: center; border-radius: 8px;">Sin Foto</div>', unsafe_allow_html=True)

                    st.markdown(f"**{row['nombre']}**")
                    st.caption(f"ZAP: {row['id']} | {row['marca']} | {row['formato']}")
                    st.metric("Stock", row['stock'], f"S/. {row['precio']}")
                    st.divider()
        else:
            st.warning("Inventario vacío o error de conexión.")

    # --- OPCIÓN 2: REGISTRAR NUEVO ---
    elif choice == "Registrar Nuevo":
        if not es_admin: st.stop()
        st.subheader("📝 Nuevo Ingreso")
        with st.form("form_registro", clear_on_submit=True):
            c1, c2 = st.columns(2)
            id_zap = c1.text_input("Código ZAP (Opcional)")
            marca = c2.selectbox("Marca", ["Celima", "Trebol", "Generico", "Otro"])
            c3, c4 = st.columns(2)
            nombre = c3.text_input("Descripción *", help="Obligatorio")
            categoria = c4.selectbox("Categoría", ["Mayólica", "Sanitario", "Grifería", "Pegamento", "Fragua", "Otro"])
            c5, c6 = st.columns(2)
            formato = c5.text_input("Formato (Ej. 60x60)")
            calidad = c6.selectbox("Calidad", ["Comercial", "Extra", "Única", "Estándar"])
            c7, c8 = st.columns(2)
            stock = c7.number_input("Stock Inicial", min_value=0)
            precio = c8.number_input("Precio Unitario", min_value=0.0, format="%.2f")
            foto = st.file_uploader("Foto", type=['jpg','png','jpeg'])
            
            if st.form_submit_button("Guardar en Nube"):
                if nombre and hoja:
                    if id_zap and id_zap in df['id'].values:
                        st.error(f"Error: El ZAP {id_zap} ya existe.")
                        st.stop()
                        
                    url_final = ""
                    if foto:
                        with st.spinner("Subiendo foto..."):
                            url_final = subir_a_imgbb(foto.getvalue(), nombre)
                            if not url_final: st.error("Error subiendo foto"); st.stop()

                    final_id = id_zap.strip() if id_zap else f"INT-{pd.Timestamp.now().strftime('%M%S')}"
                    # Orden exacto: id, nombre, categoria, marca, formato, calidad, stock, precio, imagen
                    fila = [str(final_id), nombre, categoria, marca, formato, calidad, stock, precio, url_final]
                    try:
                        hoja.append_row(fila)
                        st.success(f"✅ Registrado: {nombre}")
                    except Exception as e:
                        st.error(f"Error en Google Sheets: {e}")
                else:
                    st.error("La Descripción es obligatoria.")

    # --- OPCIÓN 3: EDITAR DETALLES (NUEVA FUNCIONALIDAD) ---
    elif choice == "Editar Detalles":
        if not es_admin: st.stop()
        st.subheader("✏️ Corregir Información de Producto")
        
        if df.empty: st.warning("No hay productos para editar."); st.stop()
        
        # 1. Seleccionar Producto
        opciones = df.apply(lambda x: f"{x['id']} | {x['nombre']}", axis=1)
        seleccion = st.selectbox("Buscar Producto a Editar:", opciones)
        id_sel = seleccion.split(" | ")[0]
        
        # 2. Obtener datos actuales
        idx = df.index[df['id'].astype(str) == id_sel].tolist()[0]
        fila_sheet = idx + 2 # Fila en Google Sheets (Header es 1, Pandas empieza en 0)
        datos_actuales = df.iloc[idx]

        st.info(f"Editando ZAP: {id_sel}")
        
        # 3. Formulario prepoblado con datos actuales
        with st.form("form_edicion"):
            c1, c2 = st.columns(2)
            # Nota: No dejamos editar el ID/ZAP porque es la llave primaria. Es peligroso.
            st.text_input("Código ZAP (No editable)", value=datos_actuales['id'], disabled=True)
            nuevo_marca = c2.selectbox("Marca", ["Celima", "Trebol", "Generico", "Otro"], index=["Celima", "Trebol", "Generico", "Otro"].index(datos_actuales['marca']) if datos_actuales['marca'] in ["Celima", "Trebol", "Generico", "Otro"] else 3)
            
            c3, c4 = st.columns(2)
            nuevo_nombre = c3.text_input("Descripción", value=datos_actuales['nombre'])
            # Lógica para encontrar el índice correcto del selectbox de categoría
            cats = ["Mayólica", "Sanitario", "Grifería", "Pegamento", "Fragua", "Otro"]
            cat_index = cats.index(datos_actuales['categoria']) if datos_actuales['categoria'] in cats else 5
            nueva_categoria = c4.selectbox("Categoría", cats, index=cat_index)
            
            c5, c6 = st.columns(2)
            nuevo_formato = c5.text_input("Formato", value=datos_actuales['formato'])
            # Lógica para calidades
            cals = ["Comercial", "Extra", "Única", "Estándar"]
            cal_index = cals.index(datos_actuales['calidad']) if datos_actuales['calidad'] in cals else 3
            nueva_calidad = c6.selectbox("Calidad", cals, index=cal_index)
            
            c7, c8 = st.columns(2)
            # Precio sí, Stock no (el stock se maneja en la otra pestaña)
            st.text_input("Stock (Usar menú 'Actualizar Stock' para cambiar)", value=datos_actuales['stock'], disabled=True)
            # Convertimos precio a float para el input
            precio_float = float(datos_actuales['precio'].replace("S/.", "").strip()) if datos_actuales['precio'] else 0.0
            nuevo_precio = c8.number_input("Precio Unitario", min_value=0.0, value=precio_float, format="%.2f")
            
            # Foto: Mostrar actual y opción de reemplazar
            st.markdown("---")
            col_foto_old, col_foto_new = st.columns(2)
            with col_foto_old:
                st.caption("Foto Actual:")
                if datos_actuales['imagen'].startswith("http"):
                    st.image(datos_actuales['imagen'], width=150)
                else:
                    st.write("Sin foto válida.")
            with col_foto_new:
                nueva_foto_file = st.file_uploader("Reemplazar Foto (Opcional)", type=['jpg','png','jpeg'], help="Si subes una nueva, reemplazará la anterior.")

            if st.form_submit_button("💾 Guardar Cambios"):
                if nuevo_nombre:
                    # Lógica de reemplazo de foto
                    url_final_edicion = datos_actuales['imagen'] # Por defecto mantenemos la vieja
                    if nueva_foto_file:
                        with st.spinner("Subiendo nueva foto y reemplazando..."):
                            url_nueva = subir_a_imgbb(nueva_foto_file.getvalue(), nuevo_nombre)
                            if url_nueva:
                                url_final_edicion = url_nueva
                            else:
                                st.error("Error al subir la nueva foto. No se guardaron cambios.")
                                st.stop()

                    # Preparar la fila completa para sobrescribir en Google Sheets
                    # Orden: id, nombre, categoria, marca, formato, calidad, stock, precio, imagen
                    fila_actualizada = [
                        datos_actuales['id'], # El ID no cambia
                        nuevo_nombre,
                        nueva_categoria,
                        nuevo_marca,
                        nuevo_formato,
                        nueva_calidad,
                        datos_actuales['stock'], # El stock no se toca aquí
                        nuevo_precio,
                        url_final_edicion
                    ]

                    try:
                        # Actualizamos el rango completo de la fila (A hasta I)
                        rango = f"A{fila_sheet}:I{fila_sheet}"
                        hoja.update(range_name=rango, values=[fila_actualizada])
                        st.success(f"✅ Producto {id_sel} actualizado correctamente.")
                        time.sleep(1) # Dar un segundo para leer el mensaje
                        st.rerun() # Recargar para ver los cambios
                    except Exception as e:
                        st.error(f"Error crítico actualizando Google Sheets: {e}")
                else:
                    st.error("La descripción no puede estar vacía.")

    # --- OPCIÓN 4: ACTUALIZAR STOCK (SOLO ADMIN) ---
    elif choice == "Actualizar Stock":
        if not es_admin: st.stop()
        st.subheader("🔄 Ajuste Rápido de Inventario")
        if not df.empty:
            opciones = df.apply(lambda x: f"{x['id']} | {x['nombre']}", axis=1)
            seleccion = st.selectbox("Seleccionar Producto para Ajuste:", opciones)
            id_sel = seleccion.split(" | ")[0]
            
            idx = df.index[df['id'].astype(str) == id_sel].tolist()[0]
            fila_sheet = idx + 2
            item = df.iloc[idx]
            
            c1, c2 = st.columns([1,2])
            with c1:
                if item['imagen'].startswith("http"): st.image(item['imagen'], width=200)
            with c2:
                st.metric("Stock Físico Actual", item['stock'])
                st.caption(f"ZAP: {item['id']} | Calidad: {item['calidad']}")
                cambio = st.number_input("Cantidad a Sumar (+) o Restar (-):", step=1, value=0)
                
                if st.button("Aplicar Movimiento"):
                    if cambio == 0:
                        st.warning("El ajuste es 0. No se hizo nada.")
                    else:
                        stock_actual_int = int(float(item['stock'])) if item['stock'] else 0
                        nuevo_stock = stock_actual_int + cambio
                        if nuevo_stock < 0:
                             st.error("Error: El stock no puede ser negativo.")
                        else:
                            # La columna de stock es la G (índice 7)
                            hoja.update_cell(fila_sheet, 7, nuevo_stock)
                            st.success(f"✅ Stock actualizado: {stock_actual_int} ➡️ {nuevo_stock}")
                            time.sleep(0.5)
                            st.rerun()

# Necesario para el sleep en la edición
import time

if __name__ == "__main__":
    main()
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
from PIL import Image
import io
from openpyxl.drawing.image import Image as ExcelImage

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Inventario Nube", layout="wide", page_icon="☁️")

# Crear carpeta de imágenes local (Ojo: Las imágenes siguen siendo volátiles en la nube gratuita)
if not os.path.exists("imagenes"):
    os.makedirs("imagenes")

# --- CONEXIÓN A GOOGLE SHEETS ---
def conectar_google_sheets():
    # Definimos el alcance (permisos)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Cargamos las credenciales desde los secretos de Streamlit
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        
        # Abrimos la hoja por su nombre (Asegúrate que se llame así en Google)
        sheet = client.open("inventario_db").sheet1
        return sheet
    except Exception as e:
        st.error(f"Error conectando a Google Sheets: {e}")
        return None

# --- FUNCIONES CRUD (Lógica de Negocio) ---

def obtener_datos():
    hoja = conectar_google_sheets()
    if hoja:
        # Descarga todos los datos como lista de diccionarios
        datos = hoja.get_all_records()
        df = pd.DataFrame(datos)
        return df, hoja
    return pd.DataFrame(), None

def generar_nuevo_id(df):
    if df.empty or 'id' not in df.columns:
        return 1
    else:
        # Convertimos a número por si acaso Google lo guardó como texto
        ids = pd.to_numeric(df['id'], errors='coerce').fillna(0)
        return int(ids.max()) + 1

# --- INTERFAZ GRÁFICA ---
def main():
    st.title("☁️ Sistema de Control: Google Sheets Edition")
    st.info("Conectado a la base de datos en la nube (Google Drive). Los datos NO se borrarán.")

    menu = ["Ver Inventario", "Registrar Nuevo", "Actualizar Stock"]
    choice = st.sidebar.selectbox("Menú Principal", menu)

    # Cargamos datos al inicio
    df, hoja = obtener_datos()

    # ==========================
    # 1. VER INVENTARIO
    # ==========================
    if choice == "Ver Inventario":
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader("📦 Inventario en Vivo")
        with col2:
            if st.button("🔄 Forzar Recarga"):
                st.rerun()

        busqueda = st.text_input("🔍 Buscar producto:")
        
        if not df.empty:
            # Filtro de búsqueda en Python (ya no en SQL)
            if busqueda:
                mask = df.apply(lambda row: row.astype(str).str.contains(busqueda, case=False).any(), axis=1)
                df_filtered = df[mask]
            else:
                df_filtered = df

            # KPIs
            # Limpieza de datos (Google Sheets a veces devuelve texto vacío)
            df_filtered['stock'] = pd.to_numeric(df_filtered['stock'], errors='coerce').fillna(0).astype(int)
            df_filtered['precio'] = pd.to_numeric(df_filtered['precio'], errors='coerce').fillna(0.0)

            col_kpi1, col_kpi2, col_descarga = st.columns(3)
            col_kpi1.metric("Total Unidades", df_filtered['stock'].sum())
            col_kpi2.metric("Valor Total", f"S/. {(df_filtered['stock'] * df_filtered['precio']).sum():,.2f}")

            # Generación Excel (Igual que antes)
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_filtered.to_excel(writer, index=False, sheet_name='Inventario')
                worksheet = writer.sheets['Inventario']
                # (Omitimos el código de imágenes incrustadas aquí para simplificar la prueba de conexión, 
                # pero puedes copiarlo del código anterior si lo necesitas urgente)
            
            buffer.seek(0)
            with col_descarga:
                st.download_button(label="📥 Descargar Excel", data=buffer, file_name='reporte_nube.xlsx')

            # Tabla
            st.dataframe(df_filtered, use_container_width=True)

        else:
            st.warning("La hoja de cálculo está vacía o no se pudo leer.")

    # ==========================
    # 2. REGISTRAR
    # ==========================
    elif choice == "Registrar Nuevo":
        st.subheader("📝 Nuevo Producto (Directo a la Nube)")
        
        with st.form("entry_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nombre = col1.text_input("Nombre")
            categoria = col2.selectbox("Categoría", ["Mayólica", "Sanitario", "Grifería", "Pegamento"])
            
            col3, col4, col5 = st.columns(3)
            formato = col3.text_input("Formato")
            stock = col4.number_input("Stock", min_value=0)
            precio = col5.number_input("Precio", min_value=0.0)
            
            # Nota sobre imágenes en la nube
            st.caption("⚠️ Nota: Las imágenes subidas aquí se guardan temporalmente. Para persistencia real de fotos se requiere Google Drive Storage (Fase 3).")
            imagen_archivo = st.file_uploader("Subir Foto", type=['jpg', 'png'])
            
            if st.form_submit_button("Guardar en Nube"):
                if nombre and hoja:
                    ruta_final = ""
                    if imagen_archivo:
                        # Guardamos local temporalmente
                        ruta_final = os.path.join("imagenes", imagen_archivo.name)
                        with open(ruta_final, "wb") as f:
                            f.write(imagen_archivo.getbuffer())

                    # Calculamos nuevo ID
                    nuevo_id = generar_nuevo_id(df)
                    
                    # Preparamos la fila (Orden exacto de tus columnas en Google Sheets)
                    nueva_fila = [nuevo_id, nombre, categoria, formato, stock, precio, ruta_final]
                    
                    try:
                        hoja.append_row(nueva_fila)
                        st.success(f"✅ Guardado en Google Sheets. ID asignado: {nuevo_id}")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Error escribiendo en Google: {e}")

    # ==========================
    # 3. ACTUALIZAR STOCK
    # ==========================
    elif choice == "Actualizar Stock":
        st.subheader("🔄 Modificar Stock en Nube")
        
        if not df.empty:
            producto_selec = st.selectbox("Buscar:", df['id'].astype(str) + " - " + df['nombre'])
            id_sel = int(producto_selec.split(" - ")[0])
            
            # Buscar la fila correcta
            # En Gspread, las filas empiezan en 1 (header). Así que sumamos 2 al index de pandas
            index_pandas = df[df['id'] == id_sel].index[0]
            fila_hoja = index_pandas + 2 
            
            stock_actual = df.loc[index_pandas, 'stock']
            st.info(f"Stock Actual en Nube: {stock_actual}")
            
            cantidad = st.number_input("Sumar/Restar:", step=1)
            
            if st.button("Actualizar Google Sheet"):
                nuevo_stock = int(stock_actual + cantidad)
                if nuevo_stock < 0:
                    st.error("No hay stock suficiente")
                else:
                    try:
                        # Columna 5 es stock (A=1, B=2, C=3, D=4, E=5)
                        hoja.update_cell(fila_hoja, 5, nuevo_stock)
                        st.success("✅ Nube actualizada")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error de conexión: {e}")

if __name__ == "__main__":
    main()
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import io
from openpyxl.drawing.image import Image as ExcelImage

# --- 1. CONFIGURACIÓN DE PÁGINA (SIEMPRE VA PRIMERO) ---
st.set_page_config(page_title="Inventario Seguro", layout="wide", page_icon="🔐")

# --- 2. SISTEMA DE LOGIN (SEGURIDAD) ---
def check_password():
    """Retorna True si el usuario ingresó la contraseña correcta."""
    
    # Si ya validó antes en esta sesión, pase directo
    if st.session_state.get('password_correct', False):
        return True

    # Interfaz de Login
    st.header("🔒 Acceso Restringido")
    st.caption("Sistema de Gestión de Inventarios - Solo personal autorizado")
    
    password_input = st.text_input("Ingresa la contraseña maestra:", type="password")
    
    if st.button("Ingresar al Sistema"):
        try:
            # Buscamos la clave en los secretos
            secreto = st.secrets["general"]["password"]
            if password_input == secreto:
                st.session_state['password_correct'] = True
                st.success("✅ Acceso concedido")
                st.rerun() # Recargamos la página para quitar el login
            else:
                st.error("❌ Contraseña incorrecta")
        except KeyError:
            st.error("⚠️ Error de configuración: No se encontró la clave '[general] password' en secrets.toml")

    return False

# --- 3. CONEXIÓN A GOOGLE SHEETS (BACKEND) ---
def conectar_google_sheets():
    if not os.path.exists("imagenes"):
        os.makedirs("imagenes")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        sheet = client.open("inventario_db").sheet1
        return sheet
    except Exception as e:
        st.error(f"Error crítico de conexión: {e}")
        return None

def obtener_datos():
    hoja = conectar_google_sheets()
    if hoja:
        datos = hoja.get_all_records()
        df = pd.DataFrame(datos)
        return df, hoja
    return pd.DataFrame(), None

def generar_nuevo_id(df):
    if df.empty or 'id' not in df.columns:
        return 1
    # Limpiamos IDs para asegurar que sean números
    ids = pd.to_numeric(df['id'], errors='coerce').fillna(0)
    return int(ids.max()) + 1

# --- 4. INTERFAZ PRINCIPAL (SOLO CARGA SI HAY LOGIN) ---
def main():
    # 🛑 CANDADO: Si no pasa el login, el código se detiene aquí.
    if not check_password():
        st.stop()

    # --- A PARTIR DE AQUÍ ES TU APP DE SIEMPRE ---
    st.title("☁️ Sistema de Control: Google Sheets Edition")
    st.sidebar.success(f"Sesión iniciada correctamente.")

    menu = ["Ver Inventario", "Registrar Nuevo", "Actualizar Stock"]
    choice = st.sidebar.selectbox("Menú Principal", menu)

    # Cargamos datos (Conexión a Nube)
    df, hoja = obtener_datos()

    # --- OPCIÓN A: VER INVENTARIO ---
    if choice == "Ver Inventario":
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader("📦 Inventario en Vivo")
        with col2:
            if st.button("🔄 Forzar Recarga"):
                st.rerun()

        busqueda = st.text_input("🔍 Buscar producto (Nombre o Categoría):")
        
        if not df.empty:
            # Filtros
            if busqueda:
                mask = df.apply(lambda row: row.astype(str).str.contains(busqueda, case=False).any(), axis=1)
                df_filtered = df[mask]
            else:
                df_filtered = df

            # Limpieza de datos numéricos para cálculos
            df_filtered['stock'] = pd.to_numeric(df_filtered['stock'], errors='coerce').fillna(0).astype(int)
            df_filtered['precio'] = pd.to_numeric(df_filtered['precio'], errors='coerce').fillna(0.0)

            # KPIs
            col_kpi1, col_kpi2, col_descarga = st.columns(3)
            col_kpi1.metric("Total Unidades", df_filtered['stock'].sum())
            col_kpi2.metric("Valor Total", f"S/. {(df_filtered['stock'] * df_filtered['precio']).sum():,.2f}")

            # Excel Download
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_filtered.to_excel(writer, index=False, sheet_name='Inventario')
                worksheet = writer.sheets['Inventario']
                for idx, col in enumerate(df_filtered.columns):
                    worksheet.column_dimensions[chr(65 + idx)].width = 15
            
            buffer.seek(0)
            with col_descarga:
                st.download_button(label="📥 Descargar Excel", data=buffer, file_name='reporte_nube.xlsx')

            # Tabla
            st.dataframe(df_filtered, use_container_width=True)
        else:
            st.warning("No se pudieron cargar los datos. Revisa la conexión.")

    # --- OPCIÓN B: REGISTRAR ---
    elif choice == "Registrar Nuevo":
        st.subheader("📝 Nuevo Producto")
        
        with st.form("entry_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nombre = col1.text_input("Nombre")
            categoria = col2.selectbox("Categoría", ["Mayólica", "Sanitario", "Grifería", "Pegamento", "Otros"])
            
            col3, col4, col5 = st.columns(3)
            formato = col3.text_input("Formato")
            stock = col4.number_input("Stock", min_value=0)
            precio = col5.number_input("Precio", min_value=0.0)
            
            imagen_archivo = st.file_uploader("Subir Foto (Opcional)", type=['jpg', 'png'])
            
            if st.form_submit_button("Guardar en Nube"):
                if nombre and hoja:
                    # Manejo temporal de imagen
                    ruta_final = ""
                    if imagen_archivo:
                        ruta_final = os.path.join("imagenes", imagen_archivo.name)
                        with open(ruta_final, "wb") as f:
                            f.write(imagen_archivo.getbuffer())

                    nuevo_id = generar_nuevo_id(df)
                    nueva_fila = [nuevo_id, nombre, categoria, formato, stock, precio, ruta_final]
                    
                    try:
                        hoja.append_row(nueva_fila)
                        st.success(f"✅ Guardado correctamente. ID: {nuevo_id}")
                    except Exception as e:
                        st.error(f"Error escribiendo en Google: {e}")
                else:
                    st.error("El nombre es obligatorio")

    # --- OPCIÓN C: ACTUALIZAR STOCK ---
    elif choice == "Actualizar Stock":
        st.subheader("🔄 Modificar Stock")
        
        if not df.empty:
            producto_selec = st.selectbox("Buscar Producto:", df['id'].astype(str) + " - " + df['nombre'])
            id_sel = int(producto_selec.split(" - ")[0])
            
            # Encontrar fila en Google Sheets (Index Pandas + 2 por header)
            index_pandas = df[df['id'] == id_sel].index[0]
            fila_hoja = index_pandas + 2 
            
            stock_actual = df.loc[index_pandas, 'stock']
            st.info(f"Stock en Nube: {stock_actual}")
            
            cantidad = st.number_input("Sumar / Restar:", step=1)
            
            if st.button("Actualizar"):
                nuevo_stock = int(stock_actual + cantidad)
                if nuevo_stock < 0:
                    st.error("No hay stock suficiente")
                else:
                    try:
                        # Columna 5 es stock (según orden: id, nombre, categoria, formato, stock...)
                        hoja.update_cell(fila_hoja, 5, nuevo_stock)
                        st.success("✅ Stock actualizado en la nube")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error de conexión: {e}")

if __name__ == "__main__":
    main()
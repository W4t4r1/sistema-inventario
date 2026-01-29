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
st.set_page_config(page_title="Inventario Ledisa", layout="wide", page_icon="🏗️")

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
            
        # Convertimos a diccionario y arreglamos los saltos de línea de la llave privada
        secrets_dict = dict(st.secrets["gcp_service_account"])
        secrets_dict["private_key"] = secrets_dict["private_key"].replace("\\n", "\n")

        creds = Credentials.from_service_account_info(secrets_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # Intentamos abrir la hoja. Asegúrate que se llame "Inventario" o "inventario_db"
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
            return pd.DataFrame(datos, columns=headers), hoja
        except Exception:
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
            rendimiento_caja = float(item['m2_caja']) if item.get('m2_caja') and str(item['m2_caja']).replace('.','',1).isdigit() else 0.0
        except:
            rendimiento_caja = 0.0
            
        if rendimiento_caja == 0:
            st.warning("⚠️ Producto sin rendimiento (m²) configurado.")
        else:
            st.caption(f"✅ Rendimiento: {rendimiento_caja} m²/caja")

    with c2:
        if item['imagen'] and item['imagen'].startswith("http"):
            st.image(item['imagen'], width=150)

    st.markdown("### 2. Dimensiones y Precios")
    col_largo, col_ancho, col_precio = st.columns(3)
    largo = col_largo.number_input("Largo (m):", min_value=0.0, step=0.1)
    ancho = col_ancho.number_input("Ancho (m):", min_value=0.0, step=0.1)
    
    precio_bd = float(item['precio']) if item.get('precio') else 0.0
    precio_oferta = col_precio.number_input("Precio Unitario (S/.):", value=precio_bd, step=0.10)

    st.markdown("### 3. Configuración de Materiales")
    c_merma, c_pegamento, c_fragua = st.columns(3)
    merma = c_merma.selectbox("Merma:", [0.05, 0.10, 0.15], index=1, format_func=lambda x: f"{int(x*100)}%")
    tipo_pegamento = c_pegamento.selectbox("Pegamento:", ["Estándar (Celima) - 25kg", "Trebol - 25kg"])
    rend_pegamento = 3.0 if "Estándar" in tipo_pegamento else 2.5
    rend_fragua = 3.5 # Estándar
    
    area_real = largo * ancho
    if area_real > 0 and rendimiento_caja > 0:
        area_total = area_real * (1 + merma)
        cajas_necesarias = math.ceil(area_total / rendimiento_caja)
        metros_totales = cajas_necesarias * rendimiento_caja
        costo_total_cajas = cajas_necesarias * precio_oferta
        bolsas_pegamento = math.ceil(area_total / rend_pegamento)
        bolsas_fragua = math.ceil(area_total / rend_fragua)

        st.divider()
        st.success(f"📊 Cálculo para {area_real:.2f} m² (+{int(merma*100)}% merma)")
        
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Cajas a Llevar", f"{cajas_necesarias} Cajas", f"{metros_totales:.2f} m²")
        kpi2.metric("Precio Unit", f"S/. {precio_oferta:.2f}", delta_color="off")
        kpi3.metric("Total Piso", f"S/. {costo_total_cajas:,.2f}")
        
        st.info(f"🧱 **Pegamento:** {bolsas_pegamento} bolsas | ✨ **Fragua:** {bolsas_fragua} bolsas")

def dashboard_logica(df):
    st.subheader("📊 Tablero de Control Gerencial")
    st.markdown("---")
    if df.empty: return

    df['stock_num'] = pd.to_numeric(df['stock'], errors='coerce').fillna(0)
    
    def limpiar_precio(val):
        if isinstance(val, str):
            val = val.replace('S/.', '').replace(',', '').strip()
        return float(val) if val else 0.0
        
    df['precio_num'] = df['precio'].apply(limpiar_precio)
    df['valor_total'] = df['stock_num'] * df['precio_num']

    total_inventario = df['valor_total'].sum()
    total_items = df['stock_num'].sum()
    total_skus = len(df)

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("💰 Valor Inventario", f"S/. {total_inventario:,.2f}")
    kpi2.metric("📦 Unidades", f"{int(total_items)}")
    kpi3.metric("🔖 SKUs", total_skus)
    
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        df_cat = df.groupby('categoria')['valor_total'].sum().reset_index()
        fig_cat = px.bar(df_cat, x='categoria', y='valor_total', title="Valor por Categoría")
        st.plotly_chart(fig_cat, use_container_width=True)
    with c2:
        df_marca = df.groupby('marca')['stock_num'].sum().reset_index()
        fig_pie = px.pie(df_marca, values='stock_num', names='marca', title="Stock por Marca", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

def cotizador_logica(df):
    st.subheader("📄 Generador de Cotizaciones")
    if 'carrito' not in st.session_state: st.session_state.carrito = []

    col_sel, col_res = st.columns([1, 1])
    with col_sel:
        df_venta = df[df['stock'].astype(float) > 0]
        opciones = df_venta.apply(lambda x: f"{x['id']} | {x['nombre']}", axis=1)
        producto_str = st.selectbox("Buscar Producto:", opciones, key="sel_prod_cot")
        
        if producto_str:
            id_sel = producto_str.split(" | ")[0]
            item = df[df['id'].astype(str) == id_sel].iloc[0]
            c1, c2 = st.columns(2)
            cantidad = c1.number_input("Cant:", min_value=1, value=1)
            precio_venta = c2.number_input("Precio Final:", value=float(item['precio']), min_value=0.0)
            
            if st.button("➕ Agregar"):
                linea = {
                    "descripcion": f"{item['nombre']} ({item['marca']})",
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
            st.metric("Total", f"S/. {total:,.2f}")
            
            if st.button("🗑️ Limpiar"):
                st.session_state.carrito = []
                st.rerun()
            
            cliente = st.text_input("Cliente:")
            dni = st.text_input("DNI/RUC:")
            
            if st.button("🖨️ PDF") and cliente:
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

# --- 6. MÓDULOS DE INTELIGENCIA ARTIFICIAL ---

def generar_tags_ia(df, hoja):
    # Función "Salto de Obstáculos" recuperada para el auto-etiquetado
    st.subheader("🏷️ Auto-Etiquetado IA (Salto de Obstáculos)")
    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
    except:
        st.error("Falta API Key de Gemini"); return

    # Mapeo de columnas
    try:
        col_tags = hoja.find("tags_ia").col
        col_id = hoja.find("id").col
    except:
        st.error("❌ Faltan columnas 'id' o 'tags_ia' en Google Sheets.")
        return

    # Filtro: Productos con imagen pero SIN tags
    df_pendientes = df[
        (df['imagen'].str.startswith('http', na=False)) & 
        ((df['tags_ia'].isna()) | (df['tags_ia'] == "") | (df['tags_ia'] == "FALSE"))
    ]
    
    cantidad = len(df_pendientes)
    st.write(f"📦 Pendientes de etiquetar: **{cantidad}**")
    
    equipo_modelos = ['models/gemini-2.0-flash', 'models/gemini-1.5-flash', 'models/gemini-exp-1206']
    
    if cantidad > 0 and st.button("🚀 INICIAR ETIQUETADO IA"):
        barra = st.progress(0)
        log = st.empty()
        
        # Estado para rotación de modelos
        if 'idx_modelo' not in st.session_state: st.session_state.idx_modelo = 0
        
        for i, (index, row) in enumerate(df_pendientes.iterrows()):
            nombre = row['nombre']
            id_prod = str(row['id']).strip()
            url = row['imagen']
            
            exito = False
            intentos = 0
            
            while not exito and intentos < len(equipo_modelos):
                modelo_actual = equipo_modelos[st.session_state.idx_modelo]
                model = genai.GenerativeModel(modelo_actual.replace("models/", ""))
                
                try:
                    # Descarga
                    res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                    if res.status_code != 200: break # Imagen rota, saltar
                    img = Image.open(io.BytesIO(res.content))

                    # IA
                    res_ai = model.generate_content(["3 tags visuales: Material, Color, Acabado. Solo palabras separadas por coma.", img])
                    tags = res_ai.text.strip()
                    
                    if not tags: raise Exception("Vacío")

                    # Guardar en Sheet
                    try:
                        cell = hoja.find(id_prod, in_column=col_id)
                        hoja.update_cell(cell.row, col_tags, tags)
                        log.success(f"✅ {nombre}: {tags}")
                        exito = True
                        time.sleep(1.5) # Pausa cortés
                    except:
                        exito = True # No encontrado en sheet, saltar
                        
                except Exception:
                    # Rotar modelo si falla
                    st.session_state.idx_modelo = (st.session_state.idx_modelo + 1) % len(equipo_modelos)
                    intentos += 1
                    time.sleep(1)

            barra.progress((i + 1) / cantidad)
        st.success("🏁 Proceso finalizado")

def consultor_ia(df):
    st.header("🤖 Consultor de Ventas IA")
    st.info("Describe qué busca el cliente. Ej: 'Piso rústico para patio exterior' o 'Porcelanato blanco brillante'.")

    # 1. VERIFICACIÓN DE DATOS
    if 'tags_ia' not in df.columns:
        st.error("⚠️ ERROR: No hay columna 'tags_ia'. Ejecuta el Auto-Etiquetado primero.")
        return

    # Verificar que haya datos reales
    productos_con_tags = df[df['tags_ia'].astype(str).str.len() > 3]
    if productos_con_tags.empty:
        st.warning("⚠️ La base de datos de etiquetas está vacía. Ve a 'Auto-Etiquetado IA' y procesa al menos 1 lote.")
        return

    # 2. LISTA DE CANDIDATOS (ORDEN DE PRIORIDAD)
    # Buscamos modelos estables para texto (no experimentales de limite 20)
    candidatos = [
        "models/gemini-1.5-flash",       # El estándar actual (rápido)
        "models/gemini-1.5-pro",         # El cerebro grande
        "models/gemini-pro",             # El clásico (1.0) muy estable
        "models/gemini-1.0-pro",         # Alias directo del clásico
        "models/gemini-pro-latest"       # Alias dinámico (está en tu lista)
    ]

    modelo_funcional = None
    genai.configure(api_key=st.secrets["gemini"]["api_key"])

    # Preparamos el contexto (Max 300 productos)
    inventario_util = productos_con_tags[['id', 'nombre', 'tags_ia']].to_dict(orient='records')
    if len(inventario_util) > 300:
        inventario_util = inventario_util[:300]
    inventario_txt = json.dumps(inventario_util, ensure_ascii=False)

    query = st.chat_input("Escribe el requerimiento...")
    
    if query:
        with st.chat_message("user"): st.write(query)
        
        with st.chat_message("assistant"):
            status = st.status("🧠 Buscando neurona disponible...", expanded=True)
            
            # --- BUCLE DE INTENTOS (LA RULETA) ---
            respuesta_obtenida = None
            
            for nombre_modelo in candidatos:
                try:
                    status.write(f"Intentando con: {nombre_modelo}...")
                    model = genai.GenerativeModel(nombre_modelo)
                    
                    prompt = f"""
                    Actúa como experto en pisos. INVENTARIO JSON: {inventario_txt}.
                    BUSQUEDA: "{query}".
                    Responde SOLO JSON válido:
                    {{
                        "recomendaciones": [{{ "id": "ID_EXACTO", "razon": "Breve motivo" }}],
                        "consejo": "Tip breve"
                    }}
                    """
                    
                    # Si esto falla, saltará al except y probará el siguiente modelo
                    res = model.generate_content(prompt)
                    respuesta_obtenida = res
                    modelo_funcional = nombre_modelo
                    break # ¡Éxito! Salimos del bucle
                    
                except Exception as e:
                    # Si es error 404 (no existe) o 429 (cuota), seguimos probando
                    print(f"Fallo {nombre_modelo}: {e}")
                    continue 

            # --- PROCESAMIENTO DEL RESULTADO ---
            if respuesta_obtenida:
                status.update(label=f"✅ ¡Conectado con {modelo_funcional}!", state="complete", expanded=False)
                
                try:
                    texto_limpio = respuesta_obtenida.text.replace("```json", "").replace("```", "").strip()
                    # Limpieza extra de JSON
                    idx_inicio = texto_limpio.find("{")
                    idx_fin = texto_limpio.rfind("}") + 1
                    if idx_inicio != -1 and idx_fin != -1:
                        texto_limpio = texto_limpio[idx_inicio:idx_fin]

                    data = json.loads(texto_limpio)
                    
                    recs = data.get('recomendaciones', [])
                    if not recs:
                        st.warning("El modelo analizó pero no encontró coincidencias exactas.")
                    else:
                        st.subheader("🏆 Resultados Sugeridos:")
                        cols = st.columns(3)
                        for i, rec in enumerate(recs):
                            id_buscado = str(rec['id']).strip()
                            prod = df[df['id'].astype(str).str.strip() == id_buscado]
                            
                            with cols[i % 3]:
                                if not prod.empty:
                                    row = prod.iloc[0]
                                    if str(row['imagen']).startswith("http"):
                                        st.image(row['imagen'])
                                    st.markdown(f"**{row['nombre']}**")
                                    st.caption(f"💡 {rec['razon']}")
                                else:
                                    st.error(f"ID {id_buscado} fantasma.")
                        
                        if 'consejo' in data:
                            st.info(f"💡 **Tip:** {data['consejo']}")

                except Exception as e:
                    st.error("Error leyendo el JSON de la IA. Intenta de nuevo.")
            else:
                status.update(label="💀 Muerte Súbita", state="error")
                st.error("❌ Todos los modelos fallaron. Tu API Key está exhausta por hoy o bloqueada. Intenta mañana o crea una nueva Key.")

# --- 7. LOGIN ---
def sidebar_login():
    st.sidebar.title("🔐 Acceso")
    if st.session_state.get('password_correct', False):
        st.sidebar.success("ADMINISTRADOR")
        if st.sidebar.button("Salir"):
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
    st.title("🏭 Sistema Ledisa v2.0")
    
    # Menú dinámico
    opciones = ["Ver Inventario", "Calculadora de Obra"]
    if es_admin:
        opciones += ["Cotizador PDF", "Dashboard", "Registrar", "Editar", "Stock", "Auto-Etiquetado IA", "Consultor IA"]
    
    menu = st.sidebar.radio("Ir a:", opciones)
    df, hoja = obtener_datos()

    if menu == "Ver Inventario":
        busqueda = st.text_input("🔍 Buscar:", placeholder="Nombre o código...")
        if busqueda:
            df = df[df.astype(str).apply(lambda x: x.str.contains(busqueda, case=False)).any(axis=1)]
        
        cols = st.columns(3)
        for i, row in df.iterrows():
            with cols[i % 3]:
                if row['imagen'].startswith("http"): st.image(row['imagen'])
                st.markdown(f"**{row['nombre']}**")
                st.caption(f"Stock: {row['stock']} | S/. {row['precio']}")
                st.divider()

    elif menu == "Calculadora de Obra": calculadora_logica(df)
    elif menu == "Dashboard": dashboard_logica(df)
    elif menu == "Cotizador PDF": cotizador_logica(df)
    elif menu == "Auto-Etiquetado IA": generar_tags_ia(df, hoja)
    elif menu == "Consultor IA": consultor_ia(df)
    
    elif menu == "Registrar":
        st.subheader("📝 Nuevo Producto")
        with st.form("new_prod"):
            c1, c2 = st.columns(2)
            nombre = c1.text_input("Nombre")
            marca = c2.selectbox("Marca", ["Celima", "Trebol", "Otro"])
            c3, c4 = st.columns(2)
            cat = c3.selectbox("Categoría", ["Mayólica", "Piso", "Pegamento", "Fragua"])
            fmt = c4.text_input("Formato")
            c5, c6 = st.columns(2)
            m2 = c5.number_input("m²/caja", 0.0)
            stk = c6.number_input("Stock", 0)
            c7, c8 = st.columns(2)
            prc = c7.number_input("Precio", 0.0)
            img = c8.file_uploader("Foto")
            
            if st.form_submit_button("Guardar"):
                url = ""
                if img: url = subir_a_imgbb(img.getvalue(), nombre)
                id_new = f"P-{int(time.time())}"
                # Orden exacto columnas: ID, Nombre, Cat, Marca, Fmt, M2, Cal, Stock, Precio, Img
                row = [id_new, nombre, cat, marca, fmt, m2, "Estándar", stk, prc, url]
                hoja.append_row(row)
                st.success("Guardado!"); st.rerun()

    elif menu == "Editar":
        item_sel = st.selectbox("Editar:", df['nombre'])
        row = df[df['nombre'] == item_sel].iloc[0]
        with st.form("edit"):
            new_prc = st.number_input("Precio", value=float(row['precio']))
            if st.form_submit_button("Actualizar"):
                idx = df[df['id'] == row['id']].index[0] + 2
                hoja.update_cell(idx, 9, new_prc) # Col 9 es Precio
                st.success("Hecho"); st.rerun()

    elif menu == "Stock":
        item_sel = st.selectbox("Producto:", df['nombre'])
        row = df[df['nombre'] == item_sel].iloc[0]
        col1, col2 = st.columns(2)
        col1.metric("Actual", row['stock'])
        ajuste = col2.number_input("Ajuste (+/-)", step=1)
        if st.button("Aplicar"):
            idx = df[df['id'] == row['id']].index[0] + 2
            nuevo = int(row['stock']) + ajuste
            hoja.update_cell(idx, 8, nuevo) # Col 8 es Stock
            st.success("Stock actualizado"); st.rerun()

if __name__ == "__main__":
    main()
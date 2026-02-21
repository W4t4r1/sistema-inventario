import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN INICIAL Y CONEXIÓN ---
st.set_page_config(page_title="LEDISA - Sistema Interno", page_icon="📦", layout="wide")

# Instanciamos el cliente de forma encapsulada
@st.cache_resource
def get_supabase() -> Client:
    # Ahora le indicamos que entre primero a la sección "supabase"
    url = st.secrets["supabase"]["SUPABASE_URL"]
    key = st.secrets["supabase"]["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = get_supabase()
except Exception as e:
    st.error("❌ Error de credenciales. Revisa tu archivo secrets.toml")
    st.stop()

def procesar_imagen_nitidez(url):
    return url.strip() if url else None

# OPTIMIZACIÓN CLAVE: Apagamos el spinner automático (show_spinner=False)
# Esto evita el error "Cursor is not set" al arrancar el servidor
@st.cache_data(ttl=60, show_spinner=False)
def cargar_inventario():
    # Usamos la conexión directamente dentro de la función
    cliente = get_supabase()
    respuesta = cliente.table('inventario').select('*').execute()
    df = pd.DataFrame(respuesta.data)
    if 'color' not in df.columns:
        df['color'] = None
    return df

def limpiar_cache():
    st.cache_data.clear()

# --- 2. INTERFAZ DE USUARIO Y MENÚ ---
st.sidebar.image("https://via.placeholder.com/150x50.png?text=LEDISA", use_container_width=True) # Reemplaza con tu logo si tienes
st.sidebar.title("Menú:")
menu = st.sidebar.radio("", [
    "Ver Inventario", 
    "Registrar Nuevo", 
    "Editar Producto", 
    "Actualizar Stock", 
    "Calculadora Obra", 
    "Dashboard", 
    "Consultor IA"
])

df = cargar_inventario()

# ==========================================
# 1. VER INVENTARIO
# ==========================================
if menu == "Ver Inventario":
    st.subheader("🛒 Catálogo de Productos")
    
    with st.expander("🔎 Filtros Avanzados", expanded=True):
        f1, f2, f3, f4 = st.columns(4)
        
        categorias_disp = sorted(df['categoria'].dropna().astype(str).unique()) if not df.empty else []
        marcas_disp = sorted(df['marca'].dropna().astype(str).unique()) if not df.empty else []
        colores_disp = sorted(df['color'].dropna().astype(str).unique()) if not df.empty and 'color' in df.columns else []
        
        min_p = float(df['precio'].min()) if not df.empty else 0.0
        max_p = float(df['precio'].max()) if not df.empty else 1000.0
        if min_p == max_p: max_p = min_p + 1.0 
        
        sel_cat = f1.multiselect("Categoría", categorias_disp)
        sel_mar = f2.multiselect("Marca", marcas_disp)
        sel_col = f3.multiselect("Color", colores_disp)
        rango_precio = f4.slider("Precio (S/.)", min_value=min_p, max_value=max_p, value=(min_p, max_p))
        
        q = st.text_input("Búsqueda rápida (Nombre o Código):", placeholder="Ej. Gris, Varilla, Celima...")

    if not df.empty:
        mask = (df['precio'] >= rango_precio[0]) & (df['precio'] <= rango_precio[1])
        if sel_cat: mask &= df['categoria'].isin(sel_cat)
        if sel_mar: mask &= df['marca'].isin(sel_mar)
        if sel_col: mask &= df['color'].isin(sel_col)
        if q: mask &= df.astype(str).apply(lambda x: x.str.contains(q, case=False)).any(axis=1)
        df_filtrado = df[mask]
    else:
        df_filtrado = pd.DataFrame()

    st.markdown(f"**Mostrando {len(df_filtrado)} productos**")
    st.markdown("---")
    
    if not df_filtrado.empty:
        cols = st.columns(3)
        for i, row in enumerate(df_filtrado.itertuples()):
            with cols[i % 3]:
                st.container()
                imgs = str(row.imagen).split(",") if pd.notna(row.imagen) and str(row.imagen).strip() else []
                imgs = [url.strip() for url in imgs if len(url.strip()) > 5]

                if imgs:
                    st.image(procesar_imagen_nitidez(imgs[0]) or imgs[0], use_container_width=True)
                else:
                    st.info("🖼️ Sin foto")
                    
                st.markdown(f"**{row.nombre}**")
                color_tag = f" | Color: {row.color}" if pd.notna(row.color) and str(row.color).strip() else ""
                st.caption(f"{row.id} | {row.marca}{color_tag}")
                
                c1, c2 = st.columns(2)
                c1.metric("Stock", row.stock)
                c2.metric("Precio", f"S/. {row.precio}")
                st.divider()
    else:
        st.warning("⚠️ No se encontraron productos.")

# ==========================================
# 2. REGISTRAR NUEVO
# ==========================================
elif menu == "Registrar Nuevo":
    st.subheader("➕ Registrar Nuevo Producto")
    with st.form("form_nuevo_producto", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            codigo = st.text_input("Código (ID)*")
            nombre = st.text_input("Nombre / Descripción*")
            categoria = st.selectbox("Categoría*", ["Porcelanato", "Cerámico", "Sanitario", "Pegamento", "Varillas", "Otros"])
            marca = st.text_input("Marca*")
            color = st.text_input("Color / Acabado (Opcional)")
        
        with c2:
            precio = st.number_input("Precio Venta (S/.)*", min_value=0.0, step=0.5)
            stock = st.number_input("Stock Inicial*", min_value=0, step=1)
            m2_caja = st.number_input("m² por Caja (0 si no aplica)*", min_value=0.0, step=0.01)
            imagen = st.text_area("URLs Imágenes (Separadas por coma)")
            
        if st.form_submit_button("Guardar Producto", type="primary"):
            if not codigo or not nombre or not marca:
                st.error("⚠️ Los campos con asterisco (*) son obligatorios.")
            else:
                nuevo = {
                    "id": codigo.strip(), "nombre": nombre.strip(), "categoria": categoria.strip(),
                    "marca": marca.strip(), "precio": float(precio), "stock": int(stock),
                    "m2_caja": float(m2_caja), "imagen": imagen.strip() if imagen.strip() else None,
                    "color": color.strip() if color.strip() else None 
                }
                try:
                    supabase.table('inventario').insert(nuevo).execute()
                    st.success(f"✅ Producto guardado.")
                    limpiar_cache()
                except Exception as e:
                    st.error(f"❌ Error BD: {e}")

# ==========================================
# 3. EDITAR PRODUCTO
# ==========================================
elif menu == "Editar Producto":
    st.subheader("✏️ Modificar o Eliminar Producto")
if not df.empty:
        # Creamos una lista combinada "ID - Nombre"
        opciones = [""] + (df['id'].astype(str) + " - " + df['nombre']).tolist()
        seleccion = st.selectbox("Buscar Producto a Editar/Eliminar:", opciones)
        
        if seleccion:
            # Extraemos solo el ID (lo que está antes del guion) para buscar en la BD
            id_selec = seleccion.split(" - ")[0].strip()
            p = df[df['id'] == id_selec].iloc[0]
            
            with st.form("form_editar_producto"):
                c1, c2 = st.columns(2)
                with c1:
                    n_nombre = st.text_input("Nombre", p['nombre'])
                    n_cat = st.text_input("Categoría", p['categoria'])
                    n_marca = st.text_input("Marca", p['marca'])
                    n_color = st.text_input("Color", p['color'] if pd.notna(p['color']) else "")
                with c2:
                    n_precio = st.number_input("Precio", value=float(p['precio']), min_value=0.0, step=0.5)
                    n_stock = st.number_input("Stock", value=int(p['stock']), step=1)
                    n_m2 = st.number_input("m² Caja", value=float(p['m2_caja'] if pd.notna(p['m2_caja']) else 0.0), step=0.01)
                    n_img = st.text_area("URLs Imágenes", p['imagen'] if pd.notna(p['imagen']) else "")
                
                col_btn1, col_btn2 = st.columns(2)
                guardar = col_btn1.form_submit_button("💾 Guardar Cambios", type="primary")
                eliminar = col_btn2.form_submit_button("🗑️ Eliminar Producto")
                
                if guardar:
                    actualizado = {
                        "nombre": n_nombre.strip(), "categoria": n_cat.strip(), "marca": n_marca.strip(),
                        "precio": float(n_precio), "stock": int(n_stock), "m2_caja": float(n_m2),
                        "imagen": n_img.strip() if n_img.strip() else None,
                        "color": n_color.strip() if n_color.strip() else None
                    }
                    supabase.table('inventario').update(actualizado).eq('id', id_selec).execute()
                    st.success("✅ Actualizado.")
                    limpiar_cache()
                    st.rerun()
                
                if eliminar:
                    supabase.table('inventario').delete().eq('id', id_selec).execute()
                    st.success("✅ Eliminado.")
                    limpiar_cache()
                    st.rerun()

# ==========================================
# 4. ACTUALIZAR STOCK (Carga Rápida)
# ==========================================
elif menu == "Actualizar Stock":
    st.subheader("📦 Ajuste Rápido de Inventario")
    st.caption("Usa esta pantalla para sumar o restar stock rápidamente cuando llega mercadería o hay mermas.")
if not df.empty:
        opciones = [""] + (df['id'].astype(str) + " - " + df['nombre']).tolist()
        seleccion = st.selectbox("Selecciona Producto:", opciones)
        
        if seleccion:
            id_selec = seleccion.split(" - ")[0].strip()
            p = df[df['id'] == id_selec].iloc[0]
            
            st.info(f"**{p['nombre']}** | Stock Actual: **{p['stock']}** unidades")
            
            with st.form("form_stock"):
                operacion = st.radio("Operación", ["Sumar (Entrada)", "Restar (Salida/Venta)"])
                cantidad = st.number_input("Cantidad", min_value=1, step=1)
                
                if st.form_submit_button("Confirmar Ajuste", type="primary"):
                    nuevo_stock = p['stock'] + cantidad if operacion == "Sumar (Entrada)" else p['stock'] - cantidad
                    if nuevo_stock < 0:
                        st.error("El stock no puede ser negativo.")
                    else:
                        supabase.table('inventario').update({"stock": int(nuevo_stock)}).eq('id', id_selec).execute()
                        st.success(f"✅ Stock actualizado a {nuevo_stock}.")
                        limpiar_cache()
                        st.rerun()

# ==========================================
# 5. CALCULADORA OBRA
# ==========================================
elif menu == "Calculadora Obra":
    st.subheader("📏 Calculadora de Cajas y Mermas")
    if not df.empty:
        df_pisos = df[df['m2_caja'] > 0] # Solo productos que se venden por m2
        id_selec = st.selectbox("Cerámico/Porcelanato:", [""] + df_pisos['nombre'].tolist())
        
        if id_selec:
            p = df_pisos[df_pisos['nombre'] == id_selec].iloc[0]
            st.write(f"**Rendimiento por caja:** {p['m2_caja']} m²")
            
            area = st.number_input("Área a cubrir (m²):", min_value=0.0, step=0.5)
            merma = st.slider("Porcentaje de Merma (Desperdicio por cortes):", 0, 15, 5)
            
            if area > 0:
                area_total = area * (1 + (merma/100))
                cajas_exactas = area_total / p['m2_caja']
                import math
                cajas_comprar = math.ceil(cajas_exactas)
                costo_total = cajas_comprar * p['precio']
                
                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                c1.metric("Área Real + Merma", f"{area_total:.2f} m²")
                c2.metric("Cajas a Vender", f"{cajas_comprar} cajas")
                c3.metric("Presupuesto", f"S/. {costo_total:.2f}")

# ==========================================
# 6. DASHBOARD (Inteligencia de Negocio)
# ==========================================
elif menu == "Dashboard":
    st.subheader("📊 Inteligencia Comercial LEDISA")
    if not df.empty:
        total_items = len(df)
        df['valor_total'] = df['precio'] * df['stock']
        capital_inmovilizado = df['valor_total'].sum()
        productos_criticos = df[df['stock'] < 10]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Variedad de Productos", total_items)
        c2.metric("Capital en Almacén", f"S/. {capital_inmovilizado:,.2f}")
        c3.metric("Alertas Quiebre Stock", len(productos_criticos), delta="- Bajo 10 unidades", delta_color="inverse")
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Distribución del Inventario por Categoría**")
            conteo_cat = df['categoria'].value_counts()
            st.bar_chart(conteo_cat)
        
        with col2:
            st.write("⚠️ **Top 10 Productos por Agotarse**")
            st.dataframe(productos_criticos[['id', 'nombre', 'stock']].sort_values('stock').head(10), use_container_width=True)

# ==========================================
# 7. CONSULTOR IA
# ==========================================
elif menu == "Consultor IA":
    st.subheader("🤖 Asistente de Ventas y Diseño")
    st.info("Espacio reservado para integración con API de Inteligencia Artificial.")
    prompt = st.text_area("Escribe la consulta del cliente:", placeholder="Ej. ¿Qué colores de porcelanato combinan con paredes grises?")
    if st.button("Consultar IA"):
        st.warning("La clave API de tu IA aún no está configurada en este bloque.") 
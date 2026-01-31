import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta

# --- CONFIGURACIÓN DE BASE DE DATOS ---
conn = sqlite3.connect('finanzas.db', check_same_thread=False)
c = conn.cursor()

# Creación de tablas con columna STOCK
c.execute('''CREATE TABLE IF NOT EXISTS productos 
             (id INTEGER PRIMARY KEY, nombre TEXT, costo REAL, venta REAL, stock INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS ventas 
             (id INTEGER PRIMARY KEY, fecha TEXT, producto_id INTEGER, vendidos INTEGER, mermas INTEGER, metodo TEXT)''')

# Migración: Agregar columna stock si no existe (para no romper tu DB actual)
try:
    c.execute("ALTER TABLE productos ADD COLUMN stock INTEGER DEFAULT 0")
except:
    pass
conn.commit()

st.set_page_config(page_title="Control de Caja PRO", layout="wide")

# --- MENÚ DE PESTAÑAS ---
tab_reg, tab_alm, tab_bal, tab_list, tab_conf = st.tabs(["📝 REGISTRAR", "📦 ALMACÉN", "💰 BALANCE", "📋 HISTORIAL", "⚙️ CONFIG"])

# --- PESTAÑA 1: REGISTRAR VENTA ---
with tab_reg:
    st.header("Registrar Venta")
    # Solo mostrar productos que tengan stock > 0
    productos = pd.read_sql("SELECT * FROM productos WHERE stock > 0", conn)
    
    if not productos.empty:
        with st.form("venta_form", clear_on_submit=True):
            p_sel = st.selectbox("Producto", productos['nombre'])
            v_cant = st.number_input("Cantidad vendida", min_value=1, step=1)
            v_mer = st.number_input("Mermas (pérdidas)", min_value=0, step=1)
            metodo = st.radio("Método de Pago", ["Efectivo", "Transferencia"], horizontal=True)
            
            if st.form_submit_button("REGISTRAR VENTA"):
                p_data = productos[productos['nombre'] == p_sel].iloc[0]
                p_id = p_data['id']
                stock_actual = p_data['stock']
                
                if v_cant <= stock_actual:
                    # Insertar venta
                    c.execute("INSERT INTO ventas (fecha, producto_id, vendidos, mermas, metodo) VALUES (?, ?, ?, ?, ?)",
                              (date.today().isoformat(), int(p_id), v_cant, v_mer, metodo))
                    # Descontar del almacén
                    nuevo_stock = stock_actual - v_cant
                    c.execute("UPDATE productos SET stock = ? WHERE id = ?", (nuevo_stock, int(p_id)))
                    conn.commit()
                    st.success(f"Venta registrada. Quedan {nuevo_stock} unidades.")
                    st.rerun()
                else:
                    st.error(f"No hay suficiente stock. Solo quedan {stock_actual} unidades.")
    else:
        st.warning("No hay productos con stock disponible.")

# --- PESTAÑA 2: ALMACÉN ---
with tab_alm:
    st.header("Inventario de Productos")
    df_alm = pd.read_sql("SELECT nombre as Producto, stock as 'Cantidad Disponible' FROM productos", conn)
    if not df_alm.empty:
        st.dataframe(df_alm, width='stretch', hide_index=True)
    else:
        st.info("El almacén está vacío.")

# --- PESTAÑA 3: BALANCE ---
with tab_bal:
    st.header("Resumen de Ganancias")
    ver_30 = st.checkbox("Ver últimos 30 días")
    filtro = (date.today() - timedelta(days=30)).isoformat() if ver_30 else date.today().isoformat()
    
    df = pd.read_sql(f"SELECT p.*, v.* FROM ventas v JOIN productos p ON v.producto_id = p.id WHERE v.fecha >= '{filtro}'", conn)
    
    if not df.empty:
        inv = (df['vendidos'] * df['costo']).sum()
        total_v = (df['vendidos'] * df['venta']).sum()
        gan_t = total_v - inv
        gan_n = gan_t / 2
        
        st.metric("🛒 TOTAL VENDIDO", f"${total_v:,.2f}")
        c1, c2 = st.columns(2)
        c1.metric("📦 TU INVERSIÓN", f"${inv:,.2f}")
        c2.metric("📈 TU GANANCIA (50%)", f"${gan_n:,.2f}")
        st.divider()
        st.success(f"### 💵 TOTAL A RECOGER: ${inv + gan_n:,.2f}")
    else:
        st.info("Sin datos en este periodo.")

# --- PESTAÑA 4: HISTORIAL (CON INVERSIÓN Y GANANCIA) ---
with tab_list:
    st.header("Detalle de Ventas")
    query_h = """
        SELECT v.fecha as Fecha, p.nombre as Producto, v.vendidos as Cant,
               (v.vendidos * p.costo) as 'Inversión',
               (v.vendidos * (p.venta - p.costo)) as 'Ganancia Total',
               v.metodo as Pago
        FROM ventas v JOIN productos p ON v.producto_id = p.id ORDER BY v.id DESC
    """
    df_h = pd.read_sql(query_h, conn)
    if not df_h.empty:
        st.dataframe(df_h, width='stretch', hide_index=True)
    else:
        st.info("No hay ventas registradas.")

# --- PESTAÑA 5: CONFIGURACIÓN (AÑADIR Y ELIMINAR) ---
with tab_conf:
    st.header("Gestión de Catálogo")
    
    with st.expander("➕ AÑADIR NUEVO PRODUCTO"):
        with st.form("nuevo_p"):
            n = st.text_input("Nombre")
            c_p = st.number_input("Costo", min_value=0.0)
            v_p = st.number_input("Precio Venta", min_value=0.0)
            s_p = st.number_input("Stock Inicial", min_value=0, step=1)
            if st.form_submit_button("Guardar"):
                c.execute("INSERT INTO productos (nombre, costo, venta, stock) VALUES (?,?,?,?)", (n, c_p, v_p, s_p))
                conn.commit()
                st.rerun()

    st.subheader("Lista de Productos Actuales")
    prods = pd.read_sql("SELECT id, nombre, stock FROM productos", conn)
    for index, row in prods.iterrows():
        col1, col2 = st.columns([3, 1])
        col1.write(f"**{row['nombre']}** ({row['stock']} unid.)")
        if col2.button("Eliminar", key=f"del_{row['id']}"):
            c.execute("DELETE FROM productos WHERE id = ?", (row['id'],))
            conn.commit()
            st.rerun()

    st.divider()
    if st.button("🚨 RESET TOTAL"):
        c.execute("DELETE FROM ventas"); c.execute("DELETE FROM productos")
        conn.commit(); st.rerun()

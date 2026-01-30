import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta

# Base de Datos
conn = sqlite3.connect('finanzas.db', check_same_thread=False)
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY, nombre TEXT, costo REAL, venta REAL)')
c.execute('CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY, fecha TEXT, producto_id INTEGER, vendidos INTEGER, mermas INTEGER, metodo TEXT)')
conn.commit()

st.set_page_config(page_title="Control de Caja", layout="centered")

# --- LAS 4 PESTAÑAS ---
tab_reg, tab_bal, tab_list, tab_conf = st.tabs(["📝 REGISTRAR", "💰 BALANCE", "📋 LISTA DE VENTAS", "⚙️ CONFIGURACIÓN"])

# --- PESTAÑA 1: REGISTRAR ---
with tab_reg:
    st.header("Nueva Venta")
    productos = pd.read_sql("SELECT * FROM productos", conn)
    if not productos.empty:
        with st.form("venta_form", clear_on_submit=True):
            p_sel = st.selectbox("Producto", productos['nombre'])
            v_cant = st.number_input("Cantidad", min_value=1, step=1)
            v_mer = st.number_input("Mermas", min_value=0, step=1)
            metodo = st.radio("Pago", ["Efectivo", "Transferencia"], horizontal=True)
            if st.form_submit_button("REGISTRAR"):
                p_id = productos[productos['nombre'] == p_sel]['id'].values[0]
                c.execute("INSERT INTO ventas (fecha, producto_id, vendidos, mermas, metodo) VALUES (?, ?, ?, ?, ?)",
                          (date.today().isoformat(), int(p_id), v_cant, v_mer, metodo))
                conn.commit()
                st.success("Registrado con éxito")
    else:
        st.info("Ve a la pestaña de CONFIGURACIÓN para añadir productos.")

# --- PESTAÑA 2: BALANCE (CON FILTRO DE 30 DÍAS) ---
with tab_bal:
    st.header("Resumen Financiero")
    
    # Opción para cambiar el periodo
    ver_30_dias = st.checkbox("Ver balance de los últimos 30 días")
    
    if ver_30_dias:
        fecha_limite = (date.today() - timedelta(days=30)).isoformat()
        query = f"SELECT p.*, v.* FROM ventas v JOIN productos p ON v.producto_id = p.id WHERE v.fecha >= '{fecha_limite}'"
        st.subheader("📅 Periodo: Últimos 30 días")
    else:
        fecha_hoy = date.today().isoformat()
        query = f"SELECT p.*, v.* FROM ventas v JOIN productos p ON v.producto_id = p.id WHERE v.fecha = '{fecha_hoy}'"
        st.subheader("☀️ Periodo: Solo Hoy")

    df = pd.read_sql(query, conn)
    
    if not df.empty:
        total_vendido = (df['vendidos'] * df['venta']).sum()
        inversion = (df['vendidos'] * df['costo']).sum()
        ganancia_total = ((df['venta'] - df['costo']) * df['vendidos']).sum()
        ganancia_neta = ganancia_total / 2

        st.metric("🛒 TOTAL VENDIDO", f"${total_vendido:,.2f}")
        
        col1, col2 = st.columns(2)
        col1.metric("📦 INVERSIÓN (Tuya)", f"${inversion:,.2f}")
        col2.metric("📈 GANANCIA MÍA (50%)", f"${ganancia_neta:,.2f}")
        
        st.metric("🤝 GANANCIA DUEÑO (50%)", f"${ganancia_neta:,.2f}")
        
        st.divider()
        st.success(f"### 💵 TOTAL A COBRAR: ${inversion + ganancia_neta:,.2f}")
    else:
        st.info("No hay ventas registradas en este periodo.")

# --- PESTAÑA 3: LISTA DE VENTAS ---
with tab_list:
    st.header("Historial de Productos Vendidos")
    df_lista = pd.read_sql("""
        SELECT v.fecha as Fecha, p.nombre as Producto, v.vendidos as Cantidad, 
               p.venta as 'Precio Unit.', (v.vendidos * p.venta) as 'Total Venta',
               v.metodo as 'Pago'
        FROM ventas v 
        JOIN productos p ON v.producto_id = p.id 
        ORDER BY v.id DESC
    """, conn)
    
    if not df_lista.empty:
        st.dataframe(df_lista, width='stretch', hide_index=True)
    else:
        st.info("La lista está vacía.")

# --- PESTAÑA 4: CONFIGURACIÓN ---
with tab_conf:
    st.header("Ajustes del Sistema")
    with st.expander("➕ AÑADIR NUEVO PRODUCTO", expanded=True):
        n = st.text_input("Nombre del Producto")
        cos = st.number_input("Costo de compra", min_value=0.0)
        ven = st.number_input("Precio de venta", min_value=0.0)
        if st.button("Guardar Producto"):
            c.execute("INSERT INTO productos (nombre, costo, venta) VALUES (?, ?, ?)", (n, cos, ven))
            conn.commit()
            st.success("Producto guardado")
            st.rerun()
    
    st.divider()
    if st.button("🚨 BORRAR TODO EL SISTEMA (RESET)"):
        c.execute("DELETE FROM ventas"); c.execute("DELETE FROM productos")
        conn.commit(); st.rerun()
import streamlit as st
import sqlite3
import pandas as pd
from datetime import date

# --- CONFIGURACIÓN BASE DE DATOS ---
conn = sqlite3.connect('negocio.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS productos 
             (id INTEGER PRIMARY KEY, nombre TEXT, costo REAL, venta REAL, stock INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS ventas 
             (id INTEGER PRIMARY KEY, fecha TEXT, p_id INTEGER, cant INTEGER, metodo TEXT)''')
conn.commit()

st.set_page_config(page_title="Caja Maestra", layout="wide")

# --- PESTAÑAS ---
t_reg, t_alm, t_hist, t_conf = st.tabs(["🛒 VENTA", "📦 ALMACÉN", "💰 BALANCE", "⚙️ CONFIG"])

# --- 1. PESTAÑA VENTA ---
with t_reg:
    prods = pd.read_sql("SELECT * FROM productos WHERE stock > 0", conn)
    if not prods.empty:
        with st.form("v"):
            p_sel = st.selectbox("Producto", prods['nombre'])
            cant = st.number_input("Cantidad", min_value=1, step=1)
            p_pago = st.radio("Pago", ["Efectivo", "Transferencia"], horizontal=True)
            if st.form_submit_button("REGISTRAR VENTA"):
                p_data = prods[prods['nombre'] == p_sel].iloc[0]
                if cant <= p_data['stock']:
                    c.execute("INSERT INTO ventas (fecha, p_id, cant, metodo) VALUES (?,?,?,?)",
                              (date.today().isoformat(), int(p_data['id']), cant, p_pago))
                    c.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (cant, int(p_data['id'])))
                    conn.commit()
                    st.success("✅ Venta registrada")
                    st.rerun()
                else: st.error("❌ No hay suficiente stock")
    else: st.warning("⚠️ Agrega stock en Configuración para vender.")

# --- 2. PESTAÑA ALMACÉN ---
with t_alm:
    st.subheader("Inventario Actual")
    df_a = pd.read_sql("SELECT nombre as Producto, stock as Cantidad, costo, venta FROM productos", conn)
    st.dataframe(df_a, use_container_width=True, hide_index=True)

# --- 3. PESTAÑA BALANCE (MODIFICADA CON TU REGLA DEL 20%) ---
with t_hist:
    st.header("📈 Reparto de Ganancias")
    
    # Traemos los datos
    df_h = pd.read_sql("""SELECT v.fecha, p.nombre, v.cant, 
                          (v.cant * p.costo) as inversion,
                          (v.cant * (p.venta - p.costo)) as ganancia
                          FROM ventas v JOIN productos p ON v.p_id = p.id""", conn)
    
    if not df_h.empty:
        # 1. Cálculos Base
        total_ganancia = df_h['ganancia'].sum()
        
        # 2. Primera División (50% Vendedor / 50% Dueños)
        pago_vendedor = total_ganancia * 0.50
        pozo_duenos = total_ganancia * 0.50
        
        # 3. Tu Regla Especial (20% del pozo de dueños para TI por la idea)
        tu_recompensa = pozo_duenos * 0.20
        resto_socios = pozo_duenos - tu_recompensa

        # --- MOSTRAR RESULTADOS ---
        st.dataframe(df_h, use_container_width=True) # Tabla de ventas
        
        st.divider()
        
        # Métricas Grandes
        kpi1, kpi2 = st.columns(2)
        kpi1.metric("💵 Ganancia TOTAL", f"${total_ganancia:,.2f}")
        kpi2.metric("🤝 Parte Vendedor (50%)", f"${pago_vendedor:,.2f}")
        
        st.subheader("💼 Bolsillo de los Dueños")
        col_A, col_B = st.columns(2)
        
        # Aquí sale tu dinero apartado
        col_A.success(f"👑 **TU BONO (20%):** ${tu_recompensa:,.2f}")
        col_B.info(f"🏢 Resto Negocio: ${resto_socios:,.2f}")
        
    else:
        st.info("No hay ventas registradas aún para calcular ganancias.")

# --- 4. PESTAÑA CONFIGURACIÓN ---
with t_conf:
    with st.expander("➕ Añadir Producto Nuevo"):
        with st.form("n"):
            nom = st.text_input("Nombre")
            co = st.number_input("Costo Unitario")
            ve = st.number_input("Precio Venta")
            stk = st.number_input("Stock Inicial", step=1)
            if st.form_submit_button("Guardar Producto"):
                c.execute("INSERT INTO productos (nombre, costo, venta, stock) VALUES (?,?,?,?)", (nom, co, ve, stk))
                conn.commit(); st.rerun()

    st.subheader("🗑️ Eliminar Productos")
    p_list = pd.read_sql("SELECT id, nombre FROM productos", conn)
    for i, r in p_list.iterrows():
        c1, c2 = st.columns([4,1])
        c1.write(r['nombre'])
        if c2.button("Borrar", key=r['id']):
            c.execute("DELETE FROM productos WHERE id=?", (r['id'],))
            conn.commit(); st.rerun()

import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta
from contextlib import contextmanager

# --- CONFIGURACIÓN ---
DB_NAME = 'finanzas.db'

# --- UTILIDADES DE BASE DE DATOS ---
@contextmanager
def get_db_connection():
    """Context manager para manejar conexiones de DB de forma segura"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Inicializa la base de datos y crea las tablas necesarias"""
    with get_db_connection() as conn:
        c = conn.cursor()
        
        # Crear tablas
        c.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                costo REAL NOT NULL CHECK(costo >= 0),
                venta REAL NOT NULL CHECK(venta >= 0),
                stock INTEGER DEFAULT 0 CHECK(stock >= 0)
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                producto_id INTEGER NOT NULL,
                vendidos INTEGER NOT NULL CHECK(vendidos > 0),
                mermas INTEGER DEFAULT 0 CHECK(mermas >= 0),
                metodo TEXT NOT NULL,
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            )
        ''')
        
        # Tabla para controlar el capital de inversión
        c.execute('''
            CREATE TABLE IF NOT EXISTS capital_inversion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                efectivo REAL DEFAULT 0 CHECK(efectivo >= 0),
                transferencia REAL DEFAULT 0 CHECK(transferencia >= 0),
                fecha_actualizacion TEXT NOT NULL
            )
        ''')
        
        # Tabla para registrar compras de inventario
        c.execute('''
            CREATE TABLE IF NOT EXISTS compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                producto_id INTEGER NOT NULL,
                cantidad INTEGER NOT NULL CHECK(cantidad > 0),
                costo_unitario REAL NOT NULL CHECK(costo_unitario >= 0),
                total REAL NOT NULL CHECK(total >= 0),
                metodo_pago TEXT NOT NULL,
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            )
        ''')
        
        # Migración: Agregar columna stock si no existe
        try:
            c.execute("ALTER TABLE productos ADD COLUMN stock INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # La columna ya existe
        
        # Inicializar capital si no existe
        c.execute("SELECT COUNT(*) FROM capital_inversion")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO capital_inversion (efectivo, transferencia, fecha_actualizacion) VALUES (0, 0, ?)",
                     (date.today().isoformat(),))
        
        conn.commit()

# --- FUNCIONES DE DATOS ---
def obtener_productos_con_stock():
    """Obtiene todos los productos que tienen stock disponible"""
    with get_db_connection() as conn:
        return pd.read_sql(
            "SELECT * FROM productos WHERE stock > 0 ORDER BY nombre", 
            conn
        )

def obtener_todos_productos():
    """Obtiene todos los productos"""
    with get_db_connection() as conn:
        return pd.read_sql(
            "SELECT id, nombre, costo, venta, stock FROM productos ORDER BY nombre", 
            conn
        )

def obtener_inventario():
    """Obtiene el inventario para mostrar en almacén"""
    with get_db_connection() as conn:
        df = pd.read_sql(
            "SELECT nombre as Producto, stock as 'Cantidad Disponible' FROM productos ORDER BY nombre", 
            conn
        )
        # Forzar conversión a enteros para evitar problemas de tipo
        if not df.empty:
            df['Cantidad Disponible'] = pd.to_numeric(df['Cantidad Disponible'], errors='coerce').fillna(0).astype(int)
        return df

def registrar_venta(producto_id, cantidad, mermas, metodo):
    """Registra una venta y actualiza el stock"""
    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            # Verificar stock actual
            c.execute("SELECT stock FROM productos WHERE id = ?", (producto_id,))
            stock_actual = c.fetchone()[0]
            
            if cantidad > stock_actual:
                return False, f"Stock insuficiente. Solo hay {stock_actual} unidades disponibles."
            
            # Insertar venta
            c.execute(
                "INSERT INTO ventas (fecha, producto_id, vendidos, mermas, metodo) VALUES (?, ?, ?, ?, ?)",
                (date.today().isoformat(), producto_id, cantidad, mermas, metodo)
            )
            
            # Actualizar stock
            nuevo_stock = stock_actual - cantidad
            c.execute("UPDATE productos SET stock = ? WHERE id = ?", (nuevo_stock, producto_id))
            
            conn.commit()
            return True, f"Venta registrada exitosamente. Quedan {nuevo_stock} unidades en stock."
        
        except Exception as e:
            conn.rollback()
            return False, f"Error al registrar venta: {str(e)}"

def agregar_producto(nombre, costo, venta, stock):
    """Agrega un nuevo producto al catálogo"""
    if not nombre.strip():
        return False, "El nombre del producto no puede estar vacío."
    
    if costo < 0 or venta < 0:
        return False, "Los precios no pueden ser negativos."
    
    if venta < costo:
        return False, "El precio de venta debe ser mayor o igual al costo."
    
    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO productos (nombre, costo, venta, stock) VALUES (?, ?, ?, ?)",
                (nombre.strip(), costo, venta, stock)
            )
            conn.commit()
            return True, "Producto agregado exitosamente."
        except sqlite3.IntegrityError:
            return False, f"Ya existe un producto con el nombre '{nombre}'."
        except Exception as e:
            return False, f"Error al agregar producto: {str(e)}"

def eliminar_producto(producto_id):
    """Elimina un producto del catálogo"""
    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            # Verificar si hay ventas asociadas
            c.execute("SELECT COUNT(*) FROM ventas WHERE producto_id = ?", (producto_id,))
            ventas_count = c.fetchone()[0]
            
            if ventas_count > 0:
                return False, "No se puede eliminar un producto con ventas registradas."
            
            c.execute("DELETE FROM productos WHERE id = ?", (producto_id,))
            conn.commit()
            return True, "Producto eliminado exitosamente."
        except Exception as e:
            return False, f"Error al eliminar producto: {str(e)}"

def obtener_ventas_periodo(fecha_inicio):
    """Obtiene las ventas desde una fecha específica"""
    with get_db_connection() as conn:
        query = """
            SELECT p.nombre, p.costo, p.venta, v.vendidos, v.mermas, v.metodo
            FROM ventas v 
            JOIN productos p ON v.producto_id = p.id 
            WHERE v.fecha >= ?
        """
        return pd.read_sql(query, conn, params=(fecha_inicio,))

def obtener_historial_ventas():
    """Obtiene el historial completo de ventas"""
    with get_db_connection() as conn:
        query = """
            SELECT 
                v.fecha as Fecha, 
                p.nombre as Producto, 
                v.vendidos as Cantidad,
                p.costo as 'Costo Unit.',
                p.venta as 'Precio Unit.',
                (v.vendidos * p.costo) as 'Inversión',
                (v.vendidos * p.venta) as 'Venta Total',
                (v.vendidos * (p.venta - p.costo)) as 'Ganancia Total',
                v.metodo as 'Método Pago'
            FROM ventas v 
            JOIN productos p ON v.producto_id = p.id 
            ORDER BY v.id DESC
        """
        return pd.read_sql(query, conn)

def reset_sistema():
    """Elimina todos los datos del sistema"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM ventas")
        c.execute("DELETE FROM compras")
        c.execute("DELETE FROM productos")
        c.execute("UPDATE capital_inversion SET efectivo = 0, transferencia = 0, fecha_actualizacion = ?",
                 (date.today().isoformat(),))
        conn.commit()

def limpiar_datos_corruptos():
    """Limpia y corrige datos corruptos en la base de datos"""
    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            # Obtener todos los productos
            c.execute("SELECT id, stock FROM productos")
            productos = c.fetchall()
            
            corregidos = 0
            for prod_id, stock in productos:
                # Intentar convertir a entero
                try:
                    if isinstance(stock, bytes):
                        stock_limpio = 0
                        corregidos += 1
                    elif stock is None:
                        stock_limpio = 0
                        corregidos += 1
                    else:
                        stock_limpio = int(stock)
                    
                    c.execute("UPDATE productos SET stock = ? WHERE id = ?", (stock_limpio, prod_id))
                except:
                    c.execute("UPDATE productos SET stock = 0 WHERE id = ?", (prod_id,))
                    corregidos += 1
            
            conn.commit()
            return True, f"Se corrigieron {corregidos} registros."
        except Exception as e:
            conn.rollback()
            return False, f"Error al limpiar datos: {str(e)}"

# --- FUNCIONES DE INVERSIÓN ---
def obtener_capital_actual():
    """Obtiene el capital de inversión disponible"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT efectivo, transferencia FROM capital_inversion ORDER BY id DESC LIMIT 1")
        resultado = c.fetchone()
        if resultado:
            return {"efectivo": resultado[0], "transferencia": resultado[1]}
        return {"efectivo": 0, "transferencia": 0}

def actualizar_capital(efectivo, transferencia):
    """Actualiza el capital de inversión disponible"""
    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            c.execute("""
                UPDATE capital_inversion 
                SET efectivo = ?, transferencia = ?, fecha_actualizacion = ?
                WHERE id = (SELECT id FROM capital_inversion ORDER BY id DESC LIMIT 1)
            """, (efectivo, transferencia, date.today().isoformat()))
            conn.commit()
            return True, "Capital actualizado correctamente."
        except Exception as e:
            conn.rollback()
            return False, f"Error al actualizar capital: {str(e)}"

def registrar_compra(producto_id, cantidad, costo_unitario, metodo_pago):
    """Registra una compra de inventario y actualiza el stock y capital"""
    with get_db_connection() as conn:
        c = conn.cursor()
        try:
            total_compra = cantidad * costo_unitario
            
            # Verificar que hay capital suficiente
            capital = obtener_capital_actual()
            if metodo_pago == "Efectivo":
                if capital["efectivo"] < total_compra:
                    return False, f"Capital insuficiente en efectivo. Disponible: ${capital['efectivo']:.2f}"
            else:
                if capital["transferencia"] < total_compra:
                    return False, f"Capital insuficiente en transferencia. Disponible: ${capital['transferencia']:.2f}"
            
            # Registrar la compra
            c.execute("""
                INSERT INTO compras (fecha, producto_id, cantidad, costo_unitario, total, metodo_pago)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (date.today().isoformat(), producto_id, cantidad, costo_unitario, total_compra, metodo_pago))
            
            # Actualizar stock del producto
            c.execute("SELECT stock FROM productos WHERE id = ?", (producto_id,))
            stock_actual = c.fetchone()[0]
            nuevo_stock = stock_actual + cantidad
            c.execute("UPDATE productos SET stock = ? WHERE id = ?", (nuevo_stock, producto_id))
            
            # Descontar del capital
            if metodo_pago == "Efectivo":
                nuevo_efectivo = capital["efectivo"] - total_compra
                c.execute("""
                    UPDATE capital_inversion 
                    SET efectivo = ?, fecha_actualizacion = ?
                    WHERE id = (SELECT id FROM capital_inversion ORDER BY id DESC LIMIT 1)
                """, (nuevo_efectivo, date.today().isoformat()))
            else:
                nueva_transferencia = capital["transferencia"] - total_compra
                c.execute("""
                    UPDATE capital_inversion 
                    SET transferencia = ?, fecha_actualizacion = ?
                    WHERE id = (SELECT id FROM capital_inversion ORDER BY id DESC LIMIT 1)
                """, (nueva_transferencia, date.today().isoformat()))
            
            conn.commit()
            return True, f"Compra registrada. Nuevo stock: {nuevo_stock} unidades. Total invertido: ${total_compra:.2f}"
        
        except Exception as e:
            conn.rollback()
            return False, f"Error al registrar compra: {str(e)}"

def obtener_inversion_por_producto():
    """Calcula la inversión actual por producto (dinero invertido en stock actual)"""
    with get_db_connection() as conn:
        query = """
            SELECT 
                p.nombre as Producto,
                p.stock as 'Stock Actual',
                p.costo as 'Costo Unitario',
                (p.stock * p.costo) as 'Inversión Actual'
            FROM productos p
            WHERE p.stock > 0
            ORDER BY p.nombre
        """
        return pd.read_sql(query, conn)

def obtener_historial_compras():
    """Obtiene el historial de compras realizadas"""
    with get_db_connection() as conn:
        query = """
            SELECT 
                c.fecha as Fecha,
                p.nombre as Producto,
                c.cantidad as Cantidad,
                c.costo_unitario as 'Costo Unit.',
                c.total as 'Total Invertido',
                c.metodo_pago as 'Método Pago'
            FROM compras c
            JOIN productos p ON c.producto_id = p.id
            ORDER BY c.id DESC
        """
        return pd.read_sql(query, conn)

def calcular_resumen_inversion():
    """Calcula el resumen total de la inversión"""
    with get_db_connection() as conn:
        c = conn.cursor()
        
        # Total invertido actualmente en productos (stock * costo)
        c.execute("SELECT SUM(stock * costo) FROM productos WHERE stock > 0")
        inversion_actual = c.fetchone()[0] or 0
        
        # Total de compras históricas
        c.execute("SELECT SUM(total) FROM compras")
        total_comprado = c.fetchone()[0] or 0
        
        # Capital disponible
        capital = obtener_capital_actual()
        
        return {
            "inversion_actual": inversion_actual,
            "total_comprado": total_comprado,
            "capital_disponible": capital["efectivo"] + capital["transferencia"],
            "capital_efectivo": capital["efectivo"],
            "capital_transferencia": capital["transferencia"]
        }

# --- CONFIGURACIÓN DE LA APLICACIÓN ---
st.set_page_config(
    page_title="Control de Caja PRO",
    page_icon="💰",
    layout="wide"
)

# Inicializar base de datos
init_database()

# --- ESTILO PERSONALIZADO ---
st.markdown("""
    <style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    </style>
""", unsafe_allow_html=True)

# --- MENÚ DE PESTAÑAS ---
tab_inv, tab_reg, tab_alm, tab_bal, tab_list, tab_conf = st.tabs([
    "💰 INVERSIÓN",
    "📝 REGISTRAR", 
    "📦 ALMACÉN", 
    "💵 BALANCE", 
    "📋 HISTORIAL", 
    "⚙️ CONFIG"
])

# --- PESTAÑA 0: INVERSIÓN ---
with tab_inv:
    st.header("💰 Gestión de Inversión")
    st.markdown("---")
    
    # Obtener resumen
    resumen = calcular_resumen_inversion()
    
    # Mostrar resumen general
    st.subheader("📊 Resumen General")
    col1, col2, col3 = st.columns(3)
    
    col1.metric(
        "💵 Capital Disponible",
        f"${resumen['capital_disponible']:,.2f}",
        help="Dinero disponible para invertir"
    )
    col2.metric(
        "📦 Inversión Actual en Stock",
        f"${resumen['inversion_actual']:,.2f}",
        help="Dinero invertido en productos en inventario"
    )
    col3.metric(
        "💰 Total Invertido Histórico",
        f"${resumen['total_comprado']:,.2f}",
        help="Total de dinero invertido en compras"
    )
    
    st.markdown("---")
    
    # Desglose de capital disponible
    col1, col2 = st.columns(2)
    col1.metric("💵 Efectivo Disponible", f"${resumen['capital_efectivo']:,.2f}")
    col2.metric("💳 Transferencia Disponible", f"${resumen['capital_transferencia']:,.2f}")
    
    st.markdown("---")
    
    # Sección para agregar capital
    with st.expander("➕ AGREGAR CAPITAL DE INVERSIÓN", expanded=False):
        st.info("Ingresa el dinero que tienes disponible para invertir en productos.")
        
        with st.form("agregar_capital"):
            col1, col2 = st.columns(2)
            
            with col1:
                efectivo_nuevo = st.number_input(
                    "Capital en Efectivo",
                    min_value=0.0,
                    value=float(resumen['capital_efectivo']),
                    step=100.0,
                    format="%.2f"
                )
            
            with col2:
                transferencia_nueva = st.number_input(
                    "Capital en Transferencia",
                    min_value=0.0,
                    value=float(resumen['capital_transferencia']),
                    step=100.0,
                    format="%.2f"
                )
            
            total_capital = efectivo_nuevo + transferencia_nueva
            st.info(f"💡 Capital total: **${total_capital:,.2f}**")
            
            if st.form_submit_button("💾 Actualizar Capital", use_container_width=True):
                exito, mensaje = actualizar_capital(efectivo_nuevo, transferencia_nueva)
                if exito:
                    st.success(mensaje)
                    st.rerun()
                else:
                    st.error(mensaje)
    
    st.markdown("---")
    
    # Sección para registrar compras
    with st.expander("🛒 REGISTRAR COMPRA DE INVENTARIO", expanded=False):
        st.info("Registra aquí las compras de productos que realices.")
        
        productos_todos = obtener_todos_productos()
        
        if not productos_todos.empty:
            with st.form("registrar_compra"):
                col1, col2 = st.columns(2)
                
                with col1:
                    producto_compra = st.selectbox(
                        "Producto",
                        productos_todos['nombre'].tolist(),
                        help="Selecciona el producto que compraste"
                    )
                    cantidad_compra = st.number_input(
                        "Cantidad Comprada",
                        min_value=1,
                        step=1,
                        help="Unidades compradas"
                    )
                
                with col2:
                    costo_unit_compra = st.number_input(
                        "Costo Unitario",
                        min_value=0.0,
                        step=0.01,
                        format="%.2f",
                        help="Precio al que compraste cada unidad"
                    )
                    metodo_pago_compra = st.radio(
                        "Método de Pago",
                        ["Efectivo", "Transferencia"],
                        horizontal=True
                    )
                
                # Calcular total
                total_compra = cantidad_compra * costo_unit_compra
                
                # Mostrar información
                capital_disponible = resumen['capital_efectivo'] if metodo_pago_compra == "Efectivo" else resumen['capital_transferencia']
                
                col_info1, col_info2 = st.columns(2)
                col_info1.info(f"💵 Total a pagar: **${total_compra:,.2f}**")
                col_info2.info(f"💰 Disponible ({metodo_pago_compra}): **${capital_disponible:,.2f}**")
                
                if total_compra > capital_disponible:
                    st.warning(f"⚠️ No tienes suficiente capital en {metodo_pago_compra}")
                
                submitted_compra = st.form_submit_button("✅ REGISTRAR COMPRA", use_container_width=True)
                
                if submitted_compra:
                    # Obtener ID del producto
                    prod_data = productos_todos[productos_todos['nombre'] == producto_compra].iloc[0]
                    
                    exito, mensaje = registrar_compra(
                        prod_data['id'],
                        cantidad_compra,
                        costo_unit_compra,
                        metodo_pago_compra
                    )
                    
                    if exito:
                        st.success(mensaje)
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(mensaje)
        else:
            st.warning("⚠️ No hay productos registrados. Agrega productos en la pestaña CONFIG.")
    
    st.markdown("---")
    
    # Inversión actual por producto
    st.subheader("📦 Inversión Actual por Producto")
    df_inversion = obtener_inversion_por_producto()
    
    if not df_inversion.empty:
        st.dataframe(
            df_inversion,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Costo Unitario": st.column_config.NumberColumn("Costo Unitario", format="$%.2f"),
                "Inversión Actual": st.column_config.NumberColumn("Inversión Actual", format="$%.2f")
            }
        )
        
        # Total invertido
        total_inv = df_inversion['Inversión Actual'].sum()
        st.success(f"### 💰 Total Invertido en Stock: ${total_inv:,.2f}")
    else:
        st.info("📭 No hay inversión actual en productos (sin stock).")
    
    st.markdown("---")
    
    # Historial de compras
    st.subheader("📋 Historial de Compras")
    df_compras = obtener_historial_compras()
    
    if not df_compras.empty:
        st.dataframe(
            df_compras,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Fecha": st.column_config.DateColumn("Fecha"),
                "Costo Unit.": st.column_config.NumberColumn("Costo Unit.", format="$%.2f"),
                "Total Invertido": st.column_config.NumberColumn("Total Invertido", format="$%.2f")
            }
        )
        
        # Opción de descarga
        csv_compras = df_compras.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar historial de compras (CSV)",
            data=csv_compras,
            file_name=f"historial_compras_{date.today()}.csv",
            mime="text/csv",
        )
    else:
        st.info("📭 No hay compras registradas aún.")

# --- PESTAÑA 1: REGISTRAR VENTA ---
with tab_reg:
    st.header("📝 Registrar Venta")
    st.markdown("---")
    
    productos = obtener_productos_con_stock()
    
    if not productos.empty:
        with st.form("venta_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                producto_seleccionado = st.selectbox(
                    "Producto",
                    productos['nombre'].tolist(),
                    help="Selecciona el producto a vender"
                )
                cantidad_vendida = st.number_input(
                    "Cantidad vendida",
                    min_value=1,
                    step=1,
                    help="Unidades vendidas"
                )
            
            with col2:
                mermas = st.number_input(
                    "Mermas (pérdidas)",
                    min_value=0,
                    step=1,
                    help="Unidades perdidas o dañadas"
                )
                metodo_pago = st.radio(
                    "Método de Pago",
                    ["Efectivo", "Transferencia"],
                    horizontal=True
                )
            
            # Mostrar información del producto seleccionado
            producto_data = productos[productos['nombre'] == producto_seleccionado].iloc[0]
            st.info(f"📦 Stock disponible: **{producto_data['stock']}** unidades | "
                   f"💵 Precio: **${producto_data['venta']:.2f}**")
            
            submitted = st.form_submit_button("✅ REGISTRAR VENTA", use_container_width=True)
            
            if submitted:
                exito, mensaje = registrar_venta(
                    producto_data['id'],
                    cantidad_vendida,
                    mermas,
                    metodo_pago
                )
                
                if exito:
                    st.success(mensaje)
                    st.balloons()
                    st.rerun()
                else:
                    st.error(mensaje)
    else:
        st.warning("⚠️ No hay productos con stock disponible.")
        st.info("💡 Agrega productos con stock en la pestaña **CONFIG**.")

# --- PESTAÑA 2: ALMACÉN ---
with tab_alm:
    st.header("📦 Inventario de Productos")
    st.markdown("---")
    
    try:
        df_inventario = obtener_inventario()
        
        if not df_inventario.empty:
            # Estadísticas rápidas
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Productos", len(df_inventario))
            
            # Sumar unidades con manejo de errores
            try:
                total_unidades = int(df_inventario['Cantidad Disponible'].sum())
                col2.metric("Total Unidades", total_unidades)
            except Exception as e:
                col2.metric("Total Unidades", "Error")
                st.error(f"Error calculando total: {e}")
            
            productos_sin_stock = len(df_inventario[df_inventario['Cantidad Disponible'] == 0])
            col3.metric("Sin Stock", productos_sin_stock)
            
            st.markdown("---")
            
            # Tabla de inventario
            st.dataframe(
                df_inventario,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Producto": st.column_config.TextColumn("Producto", width="large"),
                    "Cantidad Disponible": st.column_config.NumberColumn(
                        "Cantidad Disponible",
                        format="%d unidades"
                    )
                }
            )
            
            # Alertas de stock bajo
            stock_bajo = df_inventario[df_inventario['Cantidad Disponible'] <= 5]
            if not stock_bajo.empty:
                st.warning("⚠️ **Productos con stock bajo (≤5 unidades):**")
                for _, row in stock_bajo.iterrows():
                    st.write(f"- {row['Producto']}: {row['Cantidad Disponible']} unidades")
        else:
            st.info("📭 El almacén está vacío. Agrega productos en la pestaña CONFIG.")
    
    except Exception as e:
        st.error(f"❌ Error al cargar el inventario: {e}")
        st.info("💡 Intenta limpiar la base de datos en la pestaña CONFIG o verifica que los datos sean correctos.")

# --- PESTAÑA 3: BALANCE ---
with tab_bal:
    st.header("💰 Resumen de Ganancias")
    st.markdown("---")
    
    # Selector de período
    col1, col2 = st.columns([3, 1])
    with col1:
        ver_30_dias = st.checkbox("Ver últimos 30 días", value=False)
    
    # Calcular fecha de inicio
    if ver_30_dias:
        fecha_inicio = (date.today() - timedelta(days=30)).isoformat()
        periodo_texto = "últimos 30 días"
    else:
        fecha_inicio = date.today().isoformat()
        periodo_texto = "hoy"
    
    df_ventas = obtener_ventas_periodo(fecha_inicio)
    
    if not df_ventas.empty:
        # Cálculos
        inversion_total = (df_ventas['vendidos'] * df_ventas['costo']).sum()
        venta_total = (df_ventas['vendidos'] * df_ventas['venta']).sum()
        ganancia_total = venta_total - inversion_total
        ganancia_neta = ganancia_total / 2  # 50% de la ganancia
        total_recoger = inversion_total + ganancia_neta
        
        # Métricas principales
        st.subheader(f"Período: {periodo_texto}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("🛒 Total Vendido", f"${venta_total:,.2f}")
        col2.metric("📦 Tu Inversión", f"${inversion_total:,.2f}")
        col3.metric("📈 Ganancia Total", f"${ganancia_total:,.2f}")
        
        st.markdown("---")
        
        # Total a recoger (destacado)
        col1, col2 = st.columns(2)
        with col1:
            st.success(f"### 💵 TU GANANCIA (50%): ${ganancia_neta:,.2f}")
        with col2:
            st.info(f"### 💰 TOTAL A RECOGER: ${total_recoger:,.2f}")
        
        # Desglose por método de pago
        st.markdown("---")
        st.subheader("Desglose por Método de Pago")
        
        col1, col2 = st.columns(2)
        
        ventas_efectivo = df_ventas[df_ventas['metodo'] == 'Efectivo']
        ventas_transferencia = df_ventas[df_ventas['metodo'] == 'Transferencia']
        
        total_efectivo = (ventas_efectivo['vendidos'] * ventas_efectivo['venta']).sum() if not ventas_efectivo.empty else 0
        total_transferencia = (ventas_transferencia['vendidos'] * ventas_transferencia['venta']).sum() if not ventas_transferencia.empty else 0
        
        col1.metric("💵 Efectivo", f"${total_efectivo:,.2f}")
        col2.metric("💳 Transferencia", f"${total_transferencia:,.2f}")
        
    else:
        st.info(f"📭 No hay ventas registradas en el período seleccionado ({periodo_texto}).")

# --- PESTAÑA 4: HISTORIAL ---
with tab_list:
    st.header("📋 Historial de Ventas")
    st.markdown("---")
    
    df_historial = obtener_historial_ventas()
    
    if not df_historial.empty:
        # Resumen
        st.metric("Total de Ventas Registradas", len(df_historial))
        
        # Tabla de historial
        st.dataframe(
            df_historial,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Fecha": st.column_config.DateColumn("Fecha"),
                "Inversión": st.column_config.NumberColumn("Inversión", format="$%.2f"),
                "Venta Total": st.column_config.NumberColumn("Venta Total", format="$%.2f"),
                "Ganancia Total": st.column_config.NumberColumn("Ganancia Total", format="$%.2f"),
                "Costo Unit.": st.column_config.NumberColumn("Costo Unit.", format="$%.2f"),
                "Precio Unit.": st.column_config.NumberColumn("Precio Unit.", format="$%.2f"),
            }
        )
        
        # Opción de descarga
        csv = df_historial.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar historial (CSV)",
            data=csv,
            file_name=f"historial_ventas_{date.today()}.csv",
            mime="text/csv",
        )
    else:
        st.info("📭 No hay ventas registradas aún.")

# --- PESTAÑA 5: CONFIGURACIÓN ---
with tab_conf:
    st.header("⚙️ Gestión de Catálogo")
    st.markdown("---")
    
    # Agregar nuevo producto
    with st.expander("➕ AÑADIR NUEVO PRODUCTO", expanded=False):
        with st.form("nuevo_producto", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                nombre = st.text_input("Nombre del Producto*", placeholder="Ej: Café Americano")
                costo = st.number_input("Costo Unitario*", min_value=0.0, format="%.2f", step=0.01)
            
            with col2:
                precio_venta = st.number_input("Precio de Venta*", min_value=0.0, format="%.2f", step=0.01)
                stock_inicial = st.number_input("Stock Inicial*", min_value=0, step=1)
            
            if costo > 0 and precio_venta > 0:
                margen = ((precio_venta - costo) / costo) * 100
                st.info(f"💡 Margen de ganancia: **{margen:.1f}%**")
            
            submitted = st.form_submit_button("✅ Guardar Producto", use_container_width=True)
            
            if submitted:
                exito, mensaje = agregar_producto(nombre, costo, precio_venta, stock_inicial)
                if exito:
                    st.success(mensaje)
                    st.rerun()
                else:
                    st.error(mensaje)
    
    # Lista de productos actuales
    st.markdown("---")
    st.subheader("📦 Productos Actuales")
    
    productos = obtener_todos_productos()
    
    if not productos.empty:
        for _, producto in productos.iterrows():
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            
            with col1:
                st.write(f"**{producto['nombre']}**")
            with col2:
                st.write(f"Stock: {producto['stock']}")
            with col3:
                st.write(f"${producto['venta']:.2f}")
            with col4:
                if st.button("🗑️", key=f"del_{producto['id']}", help="Eliminar producto"):
                    exito, mensaje = eliminar_producto(producto['id'])
                    if exito:
                        st.success(mensaje)
                        st.rerun()
                    else:
                        st.error(mensaje)
            
            st.markdown("---")
    else:
        st.info("No hay productos registrados.")
    
    # Reset del sistema
    st.markdown("---")
    st.subheader("⚠️ Zona Peligrosa")
    
    # Limpiar datos corruptos
    with st.expander("🔧 REPARAR BASE DE DATOS", expanded=False):
        st.info("Si experimentas errores al cargar productos o inventario, usa esta opción para limpiar datos corruptos.")
        
        if st.button("🔧 Limpiar Datos Corruptos"):
            exito, mensaje = limpiar_datos_corruptos()
            if exito:
                st.success(f"✅ {mensaje}")
                st.rerun()
            else:
                st.error(mensaje)
    
    with st.expander("🚨 RESET TOTAL DEL SISTEMA", expanded=False):
        st.warning("⚠️ **ADVERTENCIA:** Esta acción eliminará TODOS los productos y ventas. No se puede deshacer.")
        
        confirmacion = st.text_input(
            "Escribe 'ELIMINAR TODO' para confirmar:",
            placeholder="ELIMINAR TODO"
        )
        
        if st.button("🗑️ CONFIRMAR RESET TOTAL", type="primary"):
            if confirmacion == "ELIMINAR TODO":
                reset_sistema()
                st.success("Sistema reiniciado correctamente.")
                st.rerun()
            else:
                st.error("Confirmación incorrecta. No se realizó ningún cambio.")

# --- FOOTER ---
st.markdown("---")
st.caption("Control de Caja PRO v2.0 | Desarrollado con Streamlit")


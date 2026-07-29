import pandas as pd
import sqlite3
import os
import glob
from datetime import datetime
from database import get_connection, init_db

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Conectar con tu archivo de credenciales (asegúrate de que el nombre sea correcto)
cred = credentials.Certificate('backend/credenciales.json') # O solo 'credenciales.json' dependiendo de dónde corras el script
firebase_admin.initialize_app(cred)

# Crear la variable que nos dejará interactuar con la base de datos
db = firestore.client()

# Nombres exactos de los archivos
RPM_FILE_PATTERN = "Prueba - RPM - 2026.xlsx"
COST_FILE_PATTERN = "Prueba - Cost Tracker 2026.xlsx"

DATA_INBOX = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data-inbox'
)

def find_file(pattern):
    path = os.path.join(DATA_INBOX, pattern)
    if os.path.exists(path):
        return path
    return None

# ─────────────────────────────────────────────
# ETL RPM
# ─────────────────────────────────────────────
def load_rpm(file_path):
    print(f"📥 Leyendo RPM: {file_path}")
    
    df = pd.read_excel(file_path, sheet_name=0, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    
    # Mapeo de columnas del Excel → columnas de la BD
    col_map = {
        'Date': 'date',
        'Country': 'country',
        'Legal Entity': 'legal_entity',
        'Legal Entity Short': 'legal_entity_short',
        'Currency': 'currency',
        'Merchant ID': 'merchant_id',
        'Tax ID': 'tax_id',
        'Merchant Name': 'merchant_name',
        'Line of Business': 'line_of_business',
        'Line of Business 2': 'line_of_business_2',
        'Line of Business 1': 'line_of_business_1',
        'Product': 'product',
        'Product 1': 'product_1',
        'Payment Method 0': 'payment_method_0',
        'Payment Method 1': 'payment_method_1',
        'TRM': 'trm',
        'TRX': 'trx',
        'TPV USD': 'tpv_usd',
        'Revenue USD': 'revenue_usd',
        'Direct Cost LE USD': 'direct_cost_le_usd',
        'Direct Cost USD': 'direct_cost_usd',
        'Interchange USD': 'interchange_usd',
        'Other Direct Cost USD': 'other_direct_cost_usd',
        'Net Revenue USD': 'net_revenue_usd',
        'Distributor Cost USD': 'distributor_cost_usd',
        'IT Cost USD': 'it_cost_usd',
        'IT Cost US LE': 'it_cost_us_le',
        'Other Indirect Cost USD': 'other_indirect_cost_usd',
        'Total Cost LE USD': 'total_cost_le_usd',
        'Total Cost USD': 'total_cost_usd',
        'Gross Profit LE': 'gross_profit_le',
        'Gross Profit USD': 'gross_profit_usd',
        'Financial Cohort': 'financial_cohort',
        'Holding': 'holding',
        'Partner': 'partner',
        'Fuente': 'fuente',
    }
    
    # Renombrar solo columnas que existen en el archivo
    existing = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=existing)
    
    # Agregar metadatos
    df['source_file'] = os.path.basename(file_path)
    df['loaded_at'] = datetime.now().isoformat()
    
    # Convertir columnas numéricas
    numeric_cols = ['trm','trx','tpv_usd','revenue_usd','direct_cost_le_usd',
                    'direct_cost_usd','interchange_usd','other_direct_cost_usd',
                    'net_revenue_usd','distributor_cost_usd','it_cost_usd',
                    'it_cost_us_le','other_indirect_cost_usd','total_cost_le_usd',
                    'total_cost_usd','gross_profit_le','gross_profit_usd']
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Obtener meses presentes en este archivo
    if 'date' not in df.columns:
        print("❌ Columna 'Date' no encontrada en RPM")
        return 0
    
    df['date'] = df['date'].astype(str).str[:10]  # YYYY-MM-DD o YYYY-MM
    months = df['date'].str[:7].unique().tolist()  # YYYY-MM
    print(f"   Meses detectados: {months}")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # UPSERT: borrar meses presentes, reinsertar
    for month in months:
        cursor.execute(
            "DELETE FROM rpm_data WHERE substr(date, 1, 7) = ?",
            (month,)
        )
    
    # Insertar nuevos datos
    cols_in_db = [c for c in [
        'date','country','legal_entity','legal_entity_short','currency',
        'merchant_id','tax_id','merchant_name','line_of_business',
        'line_of_business_2','line_of_business_1','product','product_1',
        'payment_method_0','payment_method_1','trm','trx','tpv_usd',
        'revenue_usd','direct_cost_le_usd','direct_cost_usd','interchange_usd',
        'other_direct_cost_usd','net_revenue_usd','distributor_cost_usd',
        'it_cost_usd','it_cost_us_le','other_indirect_cost_usd',
        'total_cost_le_usd','total_cost_usd','gross_profit_le','gross_profit_usd',
        'financial_cohort','holding','partner','fuente','source_file','loaded_at'
    ] if c in df.columns]
    
    df_to_insert = df[cols_in_db]
    df_to_insert.to_sql('rpm_data', conn, if_exists='append', index=False)
    
    rows = len(df_to_insert)
    conn.commit()
    conn.close()
    print(f"   ✅ RPM cargado: {rows} filas para meses {months}")
    return rows

# ─────────────────────────────────────────────
# ETL COST TRACKER
# ─────────────────────────────────────────────
def load_cost_tracker(file_path):
    print(f"📥 Leyendo Cost Tracker: {file_path}")
    
    df = pd.read_excel(file_path, sheet_name=0, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    
    col_map = {
        'Fecha': 'fecha',
        'Country': 'country',
        'Legal Entity': 'legal_entity',
        'Legal Entity Short': 'legal_entity_short',
        'No. Documento': 'no_documento',
        'No. Cuenta': 'no_cuenta',
        'Nombre Cuenta': 'nombre_cuenta',
        'Descripcion': 'descripcion',
        'Importe Moneda': 'importe_moneda',
        'Cod. Linea Negocio': 'cod_linea_negocio',
        'Cod. Forma Pago': 'cod_forma_pago',
        'Tipo Producto': 'tipo_producto',
        'Proveedor': 'proveedor',
        'Importe USD': 'importe_usd',
        'COGS Type': 'cogs_type',
        'Account COA': 'account_coa',
        'LOB': 'lob',
        'Type': 'type',
        'Clasification': 'clasification',
        'Subtype': 'subtype',
    }
    
    existing = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=existing)
    
    df['source_file'] = os.path.basename(file_path)
    df['loaded_at'] = datetime.now().isoformat()
    
    # Numéricos
    for col in ['importe_moneda', 'importe_usd']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 🟢 HOMOLOGAR PROVEEDORES: Mayúsculas y sin espacios extra
    if 'proveedor' in df.columns:
        print("🚀 ¡ÉXITO! Encontré la columna y la estoy convirtiendo a MAYÚSCULAS...")
        df['proveedor'] = df['proveedor'].astype(str).str.strip().str.upper()
    else:
        print("⚠️ ALERTA: ¡No encuentro la columna 'proveedor'!")       
    
    # UPSERT por mes
    if 'fecha' not in df.columns:
        print("❌ Columna 'Fecha' no encontrada en Cost Tracker")
        return 0
    
    df['fecha'] = df['fecha'].astype(str).str[:10]
    months = df['fecha'].str[:7].unique().tolist()
    print(f"   Meses detectados: {months}")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    for month in months:
        cursor.execute(
            "DELETE FROM cost_tracker WHERE substr(fecha, 1, 7) = ?",
            (month,)
        )
    
    cols_in_db = [c for c in [
        'fecha','country','legal_entity','legal_entity_short',
        'no_documento','no_cuenta','nombre_cuenta','descripcion',
        'importe_moneda','cod_linea_negocio','cod_forma_pago',
        'tipo_producto','proveedor','importe_usd','cogs_type',
        'account_coa','lob','type','clasification','subtype',
        'source_file','loaded_at'
    ] if c in df.columns]
    
    df_to_insert = df[cols_in_db]
    df_to_insert.to_sql('cost_tracker', conn, if_exists='append', index=False)
    
    rows = len(df_to_insert)
    conn.commit()
    conn.close()
    print(f"   ✅ Cost Tracker cargado: {rows} filas para meses {months}")
    return rows

# ─────────────────────────────────────────────
# ETL PRINCIPAL
# ─────────────────────────────────────────────
def run_etl():
    print(f"\n{'='*50}")
    print(f"🔄 ETL iniciado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📂 Carpeta monitoreada: {DATA_INBOX}")
    
    results = {'rpm': 0, 'cost': 0, 'errors': []}
    
    # RPM
    rpm_path = find_file(RPM_FILE_PATTERN)
    if rpm_path:
        try:
            results['rpm'] = load_rpm(rpm_path)
        except Exception as e:
            msg = f"❌ Error en RPM: {e}"
            print(msg)
            results['errors'].append(msg)
    else:
        print(f"⚠️  RPM no encontrado: {RPM_FILE_PATTERN}")
    
    # Cost Tracker
    cost_path = find_file(COST_FILE_PATTERN)
    if cost_path:
        try:
            results['cost'] = load_cost_tracker(cost_path)
        except Exception as e:
            msg = f"❌ Error en Cost Tracker: {e}"
            print(msg)
            results['errors'].append(msg)
    else:
        print(f"⚠️  Cost Tracker no encontrado: {COST_FILE_PATTERN}")
    
    print(f"\n✅ ETL completado: RPM={results['rpm']} filas, Cost={results['cost']} filas")
    if results['errors']:
        print(f"⚠️  Errores: {results['errors']}")
    print(f"{'='*50}\n")

    
    # === NUEVO CÓDIGO PARA FIREBASE ===
    print("Enviando datos a la nube...")
                    # Opcional: Agregamos la fecha exacta en la que se subió
    results['ultima_actualizacion'] = firestore.SERVER_TIMESTAMP
                    
    doc_ref = db.collection('dashboard_data').document('kpis_principales')
                    # Aquí le pasamos tu variable 'results' real
    doc_ref.set(results) 
    print("✅ Datos enviados exitosamente a Firestore en la nube")

    return results
    

if __name__ == '__main__':
    init_db()
    run_etl()
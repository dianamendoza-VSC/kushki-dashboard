import sqlite3
import os

# Ruta a la base de datos (relativa a la ubicación de este archivo)
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'database',
    'dashboard.db'
)

def get_connection():
    """Retorna conexión con row_factory para acceso tipo diccionario."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Crea todas las tablas si no existen."""
    conn = get_connection()
    cursor = conn.cursor()

    # Tabla 1: Datos RPM (Prueba - RPM - 2026)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rpm_data (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            date                    TEXT,
            country                 TEXT,
            legal_entity            TEXT,
            legal_entity_short      TEXT,
            currency                TEXT,
            merchant_id             TEXT,
            tax_id                  TEXT,
            merchant_name           TEXT,
            line_of_business        TEXT,
            line_of_business_2      TEXT,
            line_of_business_1      TEXT,
            product                 TEXT,
            product_1               TEXT,
            payment_method_0        TEXT,
            payment_method_1        TEXT,
            trm                     REAL,
            trx                     REAL,
            tpv_usd                 REAL,
            revenue_usd             REAL,
            direct_cost_le_usd      REAL,
            direct_cost_usd         REAL,
            interchange_usd         REAL,
            other_direct_cost_usd   REAL,
            net_revenue_usd         REAL,
            distributor_cost_usd    REAL,
            it_cost_usd             REAL,
            it_cost_us_le           REAL,
            other_indirect_cost_usd REAL,
            total_cost_le_usd       REAL,
            total_cost_usd          REAL,
            gross_profit_le         REAL,
            gross_profit_usd        REAL,
            financial_cohort        TEXT,
            holding                 TEXT,
            partner                 TEXT,
            fuente                  TEXT,
            source_file             TEXT,
            loaded_at               TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Tabla 2: Cost Tracker (Prueba - Cost Tracker 2026)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cost_tracker (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha               TEXT,
            country             TEXT,
            legal_entity        TEXT,
            legal_entity_short  TEXT,
            no_documento        TEXT,
            no_cuenta           TEXT,
            nombre_cuenta       TEXT,
            descripcion         TEXT,
            importe_moneda      REAL,
            cod_linea_negocio   TEXT,
            cod_forma_pago      TEXT,
            tipo_producto       TEXT,
            proveedor           TEXT,
            importe_usd         REAL,
            cogs_type           TEXT,
            account_coa         TEXT,
            lob                 TEXT,
            type                TEXT,
            clasification       TEXT,
            subtype             TEXT,
            source_file         TEXT,
            loaded_at           TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Tabla 3: Comentarios persistentes por período
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            period       TEXT NOT NULL,
            section      TEXT NOT NULL DEFAULT 'overview',
            comment_text TEXT NOT NULL,
            author       TEXT DEFAULT 'Diana',
            created_at   TEXT DEFAULT (datetime('now')),
            updated_at   TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Índices para mejor rendimiento
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rpm_date     ON rpm_data(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rpm_country  ON rpm_data(country)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rpm_merchant ON rpm_data(merchant_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cost_fecha   ON cost_tracker(fecha)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cost_country ON cost_tracker(country)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_period ON comments(period)')

    conn.commit()
    conn.close()
    print(f"[OK] Base de datos inicializada en: {DB_PATH}")

if __name__ == '__main__':
    init_db()
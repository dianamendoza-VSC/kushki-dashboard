from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3

app = Flask(__name__)

import os
import zipfile
import urllib.request



# --- INICIO DEL AUTO-DESCARGADOR ---
db_path = '/tmp/dashboard.db'
zip_path = '/tmp/dashboard.zip'

# PEGA AQUÍ TU ENLACE DE GITHUB RELEASES
DOWNLOAD_URL = "https://github.com/dianamendoza-VSC/kushki-dashboard/releases/download/v1.0/database.zip"

if not os.path.exists(db_path):
    print("Descargando base de datos desde GitHub...")
    try:
        urllib.request.urlretrieve(DOWNLOAD_URL, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall('/tmp/')
            
        # Si el zip guardó la carpeta, sacamos el archivo para dejarlo en la ruta principal
        if os.path.exists('/tmp/database/dashboard.db') and not os.path.exists(db_path):
            os.rename('/tmp/database/dashboard.db', db_path)
            
        print("¡Base de datos lista!")
    except Exception as e:
        print(f"Error al descargar/descomprimir: {e}")
# --- FIN DEL AUTO-DESCARGADOR ---


# 🟢 CONFIGURACIÓN ÚNICA CORREGIDA: Flask-CORS ya maneja el '*' de forma interna sin duplicar
CORS(app)

# Función auxiliar para la conexión a la base de datos
def get_connection():
    conn = sqlite3.connect('/tmp/dashboard.db')
    conn.row_factory = sqlite3.Row
    return conn


# ─── CORS para desarrollo local ──────────────────────────────────────────────


# ─── STATUS ──────────────────────────────────────────────────────────────────
@app.route('/api/status')
def get_status():
    """Estado del sistema y resumen de datos."""
    conn = get_connection()
    cursor = conn.cursor()
    rpm_count  = cursor.execute("SELECT COUNT(*) FROM rpm_data").fetchone()[0]
    cost_count = cursor.execute("SELECT COUNT(*) FROM cost_tracker").fetchone()[0]
    last_rpm   = cursor.execute("SELECT MAX(loaded_at) FROM rpm_data").fetchone()[0]
    last_cost  = cursor.execute("SELECT MAX(loaded_at) FROM cost_tracker").fetchone()[0]
    periods    = [r[0] for r in cursor.execute(
        "SELECT DISTINCT substr(date,1,7) FROM rpm_data WHERE date IS NOT NULL ORDER BY 1 DESC"
    ).fetchall()]
    conn.close()
    return jsonify({
        'status': 'running',
        'rpm_rows': rpm_count,
        'cost_rows': cost_count,
        'last_rpm_load': last_rpm,
        'last_cost_load': last_cost,
        'available_periods': periods
    })


# ─── PERÍODOS Y FILTROS ───────────────────────────────────────────────────────
@app.route('/api/periods')
def get_periods():
    """Períodos disponibles (YYYY-MM) para los dropdowns."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT substr(date,1,7) as p FROM rpm_data WHERE date IS NOT NULL ORDER BY p DESC"
    ).fetchall()
    conn.close()
    return jsonify({'periods': [r['p'] for r in rows]})


@app.route('/api/filters')
def get_filters():
    """Valores únicos para todos los filtros del dashboard."""
    conn = get_connection()
    def uniq(sql):
        return [r[0] for r in conn.execute(sql).fetchall() if r[0]]
    result = {
        'countries':      uniq("SELECT DISTINCT country          FROM rpm_data ORDER BY country"),
        'lobs':           uniq("SELECT DISTINCT line_of_business FROM rpm_data ORDER BY line_of_business"),
        'legal_entities': uniq("SELECT DISTINCT legal_entity     FROM rpm_data ORDER BY legal_entity"),
        'products':       uniq("SELECT DISTINCT product          FROM rpm_data ORDER BY product"),
        'payment_methods':uniq("SELECT DISTINCT payment_method_1 FROM rpm_data ORDER BY payment_method_1"),
        'cost_lobs':      uniq("SELECT DISTINCT lob              FROM cost_tracker ORDER BY lob"),
        'cogs_types':     uniq("SELECT DISTINCT cogs_type        FROM cost_tracker ORDER BY cogs_type"),
        'proveedores':    uniq("SELECT DISTINCT proveedor        FROM cost_tracker ORDER BY proveedor"),
    }
    conn.close()
    return jsonify(result)


# ─── KPIs ─────────────────────────────────────────────────────────────────────
@app.route('/api/kpis')
def get_kpis():
    period = request.args.get('period')
    period2 = request.args.get('period2') # Necesitamos recibir el periodo de comparación
    country = request.args.get('country')

    conn = get_connection()

    def get_period_data(p):
        if not p: return None
        where_parts = ["substr(date,1,7) = ?"]
        params = [p]
        if country:
            where_parts.append("country = ?"); params.append(country)
        
        where = "WHERE " + " AND ".join(where_parts)
        row = conn.execute(f"""
            SELECT
                SUM(tpv_usd)         AS tpv,
                SUM(revenue_usd)     AS revenue,
                SUM(net_revenue_usd) AS net_revenue,
                SUM(gross_profit_usd)AS gross_profit,
                SUM(trx)             AS trx,
                SUM(total_cost_usd)  AS total_cost
            FROM rpm_data {where}
        """, params).fetchone()
        return row

    curr = get_period_data(period)
    prior = get_period_data(period2)
    conn.close()

    # Valores actuales
    c_tpv = curr['tpv'] or 0
    c_rev = curr['revenue'] or 0
    c_nr  = curr['net_revenue'] or 0
    c_gp  = curr['gross_profit'] or 0
    c_trx = curr['trx'] or 0
    
    # Cálculos actuales correctos
    c_gm = (c_gp / c_rev) if c_rev != 0 else 0
    c_nr_margin = (c_nr / c_rev) if c_rev != 0 else 0  # <-- NUEVO CÁLCULO
    c_tr = (c_rev / c_tpv) if c_tpv != 0 else 0


    # Si no hay prior, enviamos nulos para los deltas
    if not prior or prior['tpv'] is None:
        return jsonify({
            'tpv_usd': c_tpv, 'revenue_usd': c_rev, 'net_revenue_usd': c_nr,
            'gross_profit_usd': c_gp, 'trx': c_trx, 
            'gross_margin': c_gm, 'nr_margin': c_nr_margin, # <-- AGREGADO AQUÍ
            'take_rate': c_tr
        })

    # Valores previos
    p_tpv = prior['tpv'] or 0
    p_rev = prior['revenue'] or 0
    p_nr  = prior['net_revenue'] or 0
    p_gp  = prior['gross_profit'] or 0
    p_trx = prior['trx'] or 0

    # Cálculos previos correctos
    p_gm = (p_gp / p_rev) if p_rev != 0 else 0
    p_nr_margin = (p_nr / p_rev) if p_rev != 0 else 0  # <-- NUEVO CÁLCULO
    p_tr = (p_rev / p_tpv) if p_tpv != 0 else 0

    # Función auxiliar para el delta porcentual
    def pct_delta(curr_val, prev_val):
        if prev_val == 0: return 0
        return ((curr_val - prev_val) / abs(prev_val)) * 100

    return jsonify({
        'tpv_usd': c_tpv,
        'tpv_delta': pct_delta(c_tpv, p_tpv),
        'revenue_usd': c_rev,
        'revenue_delta': pct_delta(c_rev, p_rev),
        'net_revenue_usd': c_nr,
        'nr_delta': pct_delta(c_nr, p_nr),
        'gross_profit_usd': c_gp,
        'gp_delta': pct_delta(c_gp, p_gp),
        'trx': c_trx,
        'trx_delta': pct_delta(c_trx, p_trx),
        'gross_margin': c_gm,
        'gm_delta': (c_gm - p_gm) * 100,
        'nr_margin': c_nr_margin,                             # <-- NUEVO
        'nr_margin_delta': (c_nr_margin - p_nr_margin) * 100, # <-- NUEVO
        'take_rate': c_tr,
        'tr_delta': (c_tr - p_tr) * 100
    })

# ─── TABLA PAÍS MoM (CON SUBFILAS PARA MÉXICO) ───────────────────────────────────
@app.route('/api/country-summary')
def get_country_summary():
    period = request.args.get('period')
    period2 = request.args.get('period2')

    conn = get_connection()

    # 1. Función base que trae el topline normal agrupado por país
    def get_by_country(p):
        if not p: return {}
        rows = conn.execute("""
            SELECT country,
                   SUM(trx)               AS trx,
                   SUM(tpv_usd)           AS tpv_usd,
                   SUM(revenue_usd)       AS revenue_usd,
                   SUM(net_revenue_usd)   AS net_revenue_usd,
                   SUM(gross_profit_usd)  AS gross_profit_usd
            FROM rpm_data
            WHERE substr(date,1,7) = ?
            GROUP BY country
        """, [p]).fetchall()
        return {r['country']: dict(r) for r in rows}

  # ─── OPTIMIZACIÓN FILA "OTHER" POR RESIDUO EN BACKEND ───
    def get_mexico_segments(p):
        if not p: return {}
        
        # 1. Total absoluto de México en el mes para usarlo como base
        tot_mex = conn.execute("""
            SELECT SUM(trx) AS trx, SUM(tpv_usd) AS tpv_usd, SUM(revenue_usd) AS revenue_usd, 
                   SUM(net_revenue_usd) AS net_revenue_usd, SUM(gross_profit_usd) AS gross_profit_usd
            FROM rpm_data WHERE substr(date,1,7) = ? AND country = 'Mexico'
        """, [p]).fetchone()
        tm = dict(tot_mex) if tot_mex and tot_mex['tpv_usd'] else {'trx':0,'tpv_usd':0,'revenue_usd':0,'net_revenue_usd':0,'gross_profit_usd':0}

        # 2. Card Present (Billpocket)
        cp = conn.execute("""
            SELECT SUM(trx) AS trx, SUM(tpv_usd) AS tpv_usd, SUM(revenue_usd) AS revenue_usd, 
                   SUM(net_revenue_usd) AS net_revenue_usd, SUM(gross_profit_usd) AS gross_profit_usd
            FROM rpm_data WHERE substr(date,1,7) = ? AND country = 'Mexico' AND line_of_business = 'Billpocket'
        """, [p]).fetchone()
        rcp = dict(cp) if cp and cp['tpv_usd'] else {'trx':0,'tpv_usd':0,'revenue_usd':0,'net_revenue_usd':0,'gross_profit_usd':0}

        # 3. Card Not Present (Todo lo que no es Billpocket, excepto el remanente)
        # NOTA: Cambiamos el SQL para que traiga la data digital pura sin riesgo de pisar a Other
        cnp = conn.execute("""
            SELECT SUM(trx) AS trx, SUM(tpv_usd) AS tpv_usd, SUM(revenue_usd) AS revenue_usd, 
                   SUM(net_revenue_usd) AS net_revenue_usd, SUM(gross_profit_usd) AS gross_profit_usd
            FROM rpm_data WHERE substr(date,1,7) = ? AND country = 'Mexico' 
              AND line_of_business != 'Billpocket'
              AND line_of_business NOT IN ('Other', 'Otros', 'OTHER') -- Exclusiones estándar digitales
        """, [p]).fetchone()
        rcnp = dict(cnp) if cnp and cnp['tpv_usd'] else {'trx':0,'tpv_usd':0,'revenue_usd':0,'net_revenue_usd':0,'gross_profit_usd':0}

        # 4. CÁLCULO DE "OTHER" POR RESIDUO (Garantiza que NADA se quede fuera)
        rother = {
            'trx': tm['trx'] - rcp['trx'] - rcnp['trx'],
            'tpv_usd': tm['tpv_usd'] - rcp['tpv_usd'] - rcnp['tpv_usd'],
            'revenue_usd': tm['revenue_usd'] - rcp['revenue_usd'] - rcnp['revenue_usd'],
            'net_revenue_usd': tm['net_revenue_usd'] - rcp['net_revenue_usd'] - rcnp['net_revenue_usd'],
            'gross_profit_usd': tm['gross_profit_usd'] - rcp['gross_profit_usd'] - rcnp['gross_profit_usd']
        }

        return {
            'Card Present': rcp,
            'Card Not Present': rcnp,
            'Other': rother
        }

    curr = get_by_country(period)
    prior = get_by_country(period2)
    
    # Obtenemos los segmentos de México para ambos meses
    mex_curr = get_mexico_segments(period)
    mex_prior = get_mexico_segments(period2)
    
    conn.close()

    countries = sorted(set(list(curr.keys()) + list(prior.keys())))
    result = []
    def safe(d, k): return d.get(k) or 0

    # Generar fila de totales agregados globales
    result.append({
        'country': 'TOTAL',
        'is_parent': False,
        'current': {k: sum(safe(v, k) for v in curr.values()) for k in ['trx','tpv_usd','revenue_usd','net_revenue_usd','gross_profit_usd']},
        'prior':   {k: sum(safe(v, k) for v in prior.values()) for k in ['trx','tpv_usd','revenue_usd','net_revenue_usd','gross_profit_usd']}
    })

    # Construcción de filas por país
    for c in countries:
        row_data = {
            'country': c,
            'is_parent': (c == 'Mexico'), # Marcamos si es México para meter subfilas
            'current': {k: safe(curr.get(c, {}), k) for k in ['trx','tpv_usd','revenue_usd','net_revenue_usd','gross_profit_usd']},
            'prior':   {k: safe(prior.get(c, {}), k) for k in ['trx','tpv_usd','revenue_usd','net_revenue_usd','gross_profit_usd']}
        }
        
        # Si procesamos México, le inyectamos sus subfilas estructuradas
        if c == 'Mexico':
            row_data['subrows'] = []
            for segment in ['Card Present', 'Card Not Present', 'Other']:
                row_data['subrows'].append({
                    'segment_name': segment,
                    'current': mex_curr.get(segment, {}),
                    'prior': mex_prior.get(segment, {})
                })
                
        result.append(row_data)

    # Helper interno para calcular márgenes y deltas de forma limpia
    def compute_metrics(name, c_data, p_data, is_subrow=False):
        c_rev, p_rev = c_data['revenue_usd'], p_data['revenue_usd']
        c_gp, p_gp   = c_data['gross_profit_usd'], p_data['gross_profit_usd']
        c_nr, p_nr   = c_data['net_revenue_usd'], p_data['net_revenue_usd']
        
        c_gm = (c_gp / c_rev) if c_rev != 0 else 0
        p_gm = (p_gp / p_rev) if p_rev != 0 else 0
        c_nr_margin = (c_nr / c_rev) if c_rev != 0 else 0
        p_nr_margin = (p_nr / p_rev) if p_rev != 0 else 0
        
        return {
            'country': name,
            'is_subrow': is_subrow,
            'trx': c_data['trx'],                   'trx_delta': c_data['trx'] - p_data['trx'],
            'tpv': c_data['tpv_usd'],               'tpv_delta': c_data['tpv_usd'] - p_data['tpv_usd'],
            'revenue': c_rev,                       'revenue_delta': c_rev - p_rev,
            'gp_prior': p_gp,                       'gp_current': c_gp,             'gp_delta': c_gp - p_gp,
            'nr_prior': p_nr,                       'nr_current': c_nr,             'nr_delta': c_nr - p_nr,
            'gm_pct': c_gm,                         'gm_delta': (c_gm - p_gm) * 100,
            'nr_margin': c_nr_margin,               'nr_margin_delta': (c_nr_margin - p_nr_margin) * 100
        }

    # Aplanar y estructurar el JSON final
    flattened_results = []
    for r in result:
        flat_row = compute_metrics(r['country'], r['current'], r['prior'])
        flat_row['is_parent'] = r.get('is_parent', False)
        
        # Si la fila tiene subfilas calculadas, se procesan y se adjuntan al objeto padre
        if r.get('subrows'):
            flat_row['subrows'] = [compute_metrics(sub['segment_name'], sub['current'], sub['prior'], is_subrow=True) for sub in r['subrows']]
            
        flattened_results.append(flat_row)

    return jsonify(flattened_results)

# ─── BRIDGE ───────────────────────────────────────────────────────────────────
# ─── 1. ENDPOINT PARA LAS TARJETAS DEL OVERVIEW (NOMBRE ÚNICO) ───────────────────
@app.route('/api/bridge-cards', methods=['GET'])
def get_bridge_cards_unique_name():
    period = request.args.get('period')
    period2 = request.args.get('period2')
    metric = request.args.get('metric', 'gross_profit_usd')
    
    # Estandarizamos la métrica seleccionada
    if 'gross_profit' in metric:
        metric = 'gross_profit_usd'
    elif 'net_revenue' in metric:
        metric = 'net_revenue_usd'

    conn = get_connection()
    
    countries_rows = conn.execute("""
        SELECT DISTINCT UPPER(TRIM(country)) AS c_name 
        FROM rpm_data 
        WHERE country IS NOT NULL AND country != ''
    """).fetchall()
    
    results = []

    # Calculamos de forma macro agrupada país por país
    for row in countries_rows:
        c_name = row['c_name']
        if c_name in ['TOTAL', 'TODOS', 'NULL', 'UNDEFINED']: 
            continue

        tot_curr_raw = conn.execute("""
            SELECT SUM(tpv_usd) AS tpv, SUM(revenue_usd) AS revenue,
                   SUM(net_revenue_usd) AS nr, SUM(gross_profit_usd) AS gp,
                   SUM(total_cost_usd) AS cost 
            FROM rpm_data 
            WHERE substr(date,1,7) = ? AND UPPER(TRIM(country)) = ?
        """, [period, c_name]).fetchone()

        tot_prior_raw = conn.execute("""
            SELECT SUM(tpv_usd) AS tpv, SUM(revenue_usd) AS revenue,
                   SUM(net_revenue_usd) AS nr, SUM(gross_profit_usd) AS gp,
                   SUM(total_cost_usd) AS cost 
            FROM rpm_data 
            WHERE substr(date,1,7) = ? AND UPPER(TRIM(country)) = ?
        """, [period2, c_name]).fetchone()

        tc = dict(tot_curr_raw) if tot_curr_raw else {}
        tp = dict(tot_prior_raw) if tot_prior_raw else {}

        tot_tpv_curr = tc.get('tpv') or 0.0
        tot_tpv_prior = tp.get('tpv') or 0.0
        tot_rev_curr = tc.get('revenue') or 0.0
        tot_rev_prior = tp.get('revenue') or 0.0
        
        # Asignación del valor de la métrica según el botón (Gross Profit o Net Revenue)
        c_val = tc.get('gp' if metric == 'gross_profit_usd' else 'nr') or 0.0
        p_val = tp.get('gp' if metric == 'gross_profit_usd' else 'nr') or 0.0
        delta = c_val - p_val

        if tot_tpv_curr == 0 and tot_tpv_prior == 0:
            continue

        # Fórmulas Macro de Tarifa (Pricing)
        take_rate_curr = (tot_rev_curr / tot_tpv_curr) if tot_tpv_curr > 0 else 0.0
        take_rate_prior = (tot_rev_prior / tot_tpv_prior) if tot_tpv_prior > 0 else 0.0
        pricing = (take_rate_curr - take_rate_prior) * tot_tpv_curr

        # 🟢 LÓGICA DE COSTO DINÁMICO SEGÚN LA MÉTRICA (Diferencia vs Revenue)
        if metric == 'gross_profit_usd':
            tot_cost_curr = (tc.get('revenue') or 0.0) - (tc.get('gp') or 0.0)
            tot_cost_prior = (tp.get('revenue') or 0.0) - (tp.get('gp') or 0.0)
        else:
            tot_cost_curr = (tc.get('revenue') or 0.0) - (tc.get('nr') or 0.0)
            tot_cost_prior = (tp.get('revenue') or 0.0) - (tp.get('nr') or 0.0)

        cost_rate_curr = (tot_cost_curr / tot_tpv_curr) if tot_tpv_curr > 0 else 0.0
        cost_rate_prior = (tot_cost_prior / tot_tpv_prior) if tot_tpv_prior > 0 else 0.0
        cost_fx = (cost_rate_prior - cost_rate_curr) * tot_tpv_curr

        # El volumen se calcula de forma exacta como el residuo del delta menos los efectos calculados
        vol_mix = delta - pricing - cost_fx

        results.append({
            'country': c_name.capitalize(),
            'delta': delta,
            'pricing': pricing,
            'vol_mix': vol_mix,
            'volume_mix': vol_mix,
            'cost': cost_fx,
            'cost_fx': cost_fx,
            'prior': p_val,
            'prior_val': p_val,
            'current': c_val,
            'current_val': c_val
        })

    conn.close()
    
    results.sort(key=lambda x: x['country'])

    # Construimos la Card de Total sumando los países de forma dinámica con todos sus componentes
    if len(results) > 0:
        total_card = {
            'country': 'Total',
            'delta': sum(c['delta'] for c in results),
            'pricing': sum(c['pricing'] for c in results),
            'vol_mix': sum(c['vol_mix'] for c in results),
            'volume_mix': sum(c['volume_mix'] for c in results),
            'cost': sum(c['cost'] for c in results),
            'cost_fx': sum(c['cost_fx'] for c in results),
            'prior': sum(c['prior'] for c in results),
            'prior_val': sum(c['prior_val'] for c in results),
            'current': sum(c['current'] for c in results),
            'current_val': sum(c['current_val'] for c in results)
        }
        results.append(total_card)

    return jsonify(results)


# ─── 2. ENDPOINT PARA EL GRÁFICO BRIDGE GENERAL (NOMBRE ÚNICO) ───────────────────────
@app.route('/api/bridge', methods=['GET'])
def get_bridge_data_macro_unique():
    country = request.args.get('country')

    # Obtenemos la lista completa (Países + la Card de Total)
    cards_response = get_bridge_cards_unique_name()
    cards_list = cards_response.get_json()

    # CASO A: Si el usuario seleccionó un país específico (Filtro activo en Merchants)
    if country and str(country).strip() != '' and str(country).lower() not in ['todos', 'null', 'undefined', '']:
        target = str(country).strip().lower()
        for c in cards_list:
            if c['country'].lower() == target:
                return jsonify(c)
        return jsonify({'prior_val':0, 'current_val':0, 'pricing':0, 'cost_fx':0, 'vol_mix':0})

    # CASO B: Overview Global (Filtración estricta para el gráfico)
    # 🟢 CORRECCIÓN: Filtramos para excluir la tarjeta 'Total' y sumar ÚNICAMENTE los países reales
    only_countries = [c for c in cards_list if c['country'].lower() != 'total']

    return jsonify({
        'prior_val': sum(c['prior_val'] for c in only_countries),
        'current_val': sum(c['current_val'] for c in only_countries),
        'pricing': sum(c['pricing'] for c in only_countries),
        'cost_fx': sum(c['cost_fx'] for c in only_countries),
        'vol_mix': sum(c['vol_mix'] for c in only_countries)
    })
    

# ─── ENDPOINT MATRICIAL FINTECH CON FILTROS DINÁMICOS DE HORIZONTE ───────────
@app.route('/api/deep-dive-matrix')
def get_deep_dive_matrix():
    country = request.args.get('country', 'Chile')
    lob = request.args.get('lob', 'Todos')
    metric_type = request.args.get('metric', 'gross_profit_usd')
    period_filter = request.args.get('period', 'ALL')
    segment = request.args.get('segment', 'Todos') # 🟢 NUEVO: Recibimos el segmento desde el HTML

    if 'gross_profit' in metric_type:
        metric_type = 'gross_profit_usd'
    elif 'net_revenue' in metric_type:
        metric_type = 'net_revenue_usd'

    # Definir Horizonte Temporal (Meses Dinámicos)
    if period_filter == 'Q1':
        months_to_query = ['2026-01', '2026-02', '2026-03']
        month_labels = ['JAN', 'FEB', 'MAR']
    elif period_filter == 'Q2':
        months_to_query = ['2026-04', '2026-05', '2026-06']
        month_labels = ['APR', 'MAY', 'JUN']
    elif period_filter.startswith('YTD-'):
        try:
            max_month = int(period_filter.split('-')[1])
        except:
            max_month = 5
        months_to_query = [f'2026-{str(i).zfill(2)}' for i in range(1, max_month + 1)]
        all_labels = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
        month_labels = all_labels[:max_month]
    elif len(period_filter) == 7:
        months_to_query = [period_filter]
        m_num = period_filter.split('-')[1]
        all_labels = {'01':"JAN", '02':"FEB", '03':"MAR", '04':"APR", '05':"MAY"}
        month_labels = [all_labels.get(m_num, f"Month {m_num}")]
    else:
        months_to_query = ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05']
        month_labels = ['JAN', 'FEB', 'MAR', 'APR', 'MAY']

    conn = get_connection()
    where_clauses = []
    params = []
    
    if country and country.lower() not in ['todos', 'all', '']:
        where_clauses.append("country = ?")
        params.append(country)
        
    # 🟢 NUEVO: Lógica especial de segmentos para México
    if segment == 'Card Present':
        where_clauses.append("line_of_business = 'Billpocket'")
    elif segment == 'Other':
        where_clauses.append("line_of_business = 'Other'")
    elif segment == 'Card Not Present':
        where_clauses.append("line_of_business NOT IN ('Billpocket', 'Other')")
    else:
        # Si el segmento es 'Todos' (o es otro país), usamos el filtro LOB normal
        if lob and lob.lower() not in ['todos', 'all', '']:
            where_clauses.append("line_of_business = ?")
            params.append(lob)
        
    where_str = f" AND {' AND '.join(where_clauses)}" if where_clauses else ""

    # Métodos en formato exacto para hacer match con el frontend
    target_methods = ['TPV Total', 'Card not Present', 'Cash', 'Cash Out', 'Transfer', 'Transfer Out']
    matrix_report = {
        'months': month_labels,
        'tpv_by_method': {m: [] for m in target_methods},
        'financials': {},
        'rates': {}
    }

    if metric_type == 'gross_profit_usd':
        fin_keys = ['Revenue USD', 'Total Cost USD', 'Direct LOB USD', 'Interchange USD', 'Other Direct Cost USD', 'IT Cost USD', 'Other Indirect USD', 'Distributor_cost_usd', 'GP LOB / Net revenue USD', 'GM%']
        rate_keys = ['Total Cost Rate%', 'Direct Rate%', 'Interchange Rate%', 'Other Direct Cost %', 'IT Cost %', 'Other Indirect %', 'Distributor Cost %']
    else:
        fin_keys = ['Revenue USD', 'Total Cost USD', 'Direct LOB USD', 'Interchange USD', 'Other Direct Cost USD', 'GP LOB / Net revenue USD', 'GM%']
        rate_keys = ['Total Cost Rate%', 'Direct Rate%', 'Interchange Rate%', 'Other Direct Cost %']

    for k in fin_keys: matrix_report['financials'][k] = []
    for k in rate_keys: matrix_report['rates'][k] = []

    for m in months_to_query:
        m_params = [m] + params
        
        # Traemos los datos globales usando el tpv_usd macro que sí tiene valores
        fin = conn.execute(f"""
            SELECT SUM(tpv_usd), SUM(revenue_usd), SUM(direct_cost_usd), 
                   SUM(interchange_usd), SUM(other_direct_cost_usd), SUM(it_cost_usd), 
                   SUM(other_indirect_cost_usd), SUM(distributor_cost_usd), 
                   SUM(net_revenue_usd), SUM(gross_profit_usd)
            FROM rpm_data WHERE substr(date,1,7) = ? {where_str}
        """, m_params).fetchone()
        
        if fin and fin[0] is not None:
            f = {
                'total_tpv': float(fin[0] or 0), 'rev': float(fin[1] or 0), 'direct_cost': float(fin[2] or 0),
                'interchange': float(fin[3] or 0), 'other_direct': float(fin[4] or 0), 'it_cost': float(fin[5] or 0),
                'other_indirect': float(fin[6] or 0), 'dist_cost': float(fin[7] or 0), 'nr': float(fin[8] or 0), 'gp': float(fin[9] or 0)
            }
        else:
            f = {k: 0.0 for k in ['total_tpv', 'rev', 'direct_cost', 'interchange', 'other_direct', 'it_cost', 'other_indirect', 'dist_cost', 'nr', 'gp']}
            
        tot_tpv = f['total_tpv']
        rev = f['rev']
        
        # ASIGNACIÓN DIRECTA: Metemos el 100% del dinero macro en 'TPV Total' y dejamos los demás en 0.0
        matrix_report['tpv_by_method']['TPV Total'].append(tot_tpv)
        matrix_report['tpv_by_method']['Card not Present'].append(0.0)
        matrix_report['tpv_by_method']['Cash'].append(0.0)
        matrix_report['tpv_by_method']['Cash Out'].append(0.0)
        matrix_report['tpv_by_method']['Transfer'].append(0.0)
        matrix_report['tpv_by_method']['Transfer Out'].append(0.0)

        # Lógica Financiera de Margen Dinámico
        direct_sum = f['direct_cost'] + f['interchange'] + f['other_direct']
        indirect_sum = f['it_cost'] + f['other_indirect'] + f['dist_cost']
        
        if metric_type == 'gross_profit_usd':
            calculated_total_cost = direct_sum + indirect_sum
            final_profit = f['gp']
        else:
            calculated_total_cost = direct_sum
            final_profit = f['nr']
            
        final_margin = (final_profit / rev * 100) if rev > 0 else 0.0

        # Llenado Estructura USD
        matrix_report['financials']['Revenue USD'].append(rev)
        matrix_report['financials']['Total Cost USD'].append(calculated_total_cost)
        matrix_report['financials']['Direct LOB USD'].append(f['direct_cost'])
        matrix_report['financials']['Interchange USD'].append(f['interchange'])
        matrix_report['financials']['Other Direct Cost USD'].append(f['other_direct'])
        
        if metric_type == 'gross_profit_usd':
            matrix_report['financials']['IT Cost USD'].append(f['it_cost'])
            matrix_report['financials']['Other Indirect USD'].append(f['other_indirect'])
            matrix_report['financials']['Distributor_cost_usd'].append(f['dist_cost'])
            
        matrix_report['financials']['GP LOB / Net revenue USD'].append(final_profit)
        matrix_report['financials']['GM%'].append(final_margin)
        
        # Llenado Tasas Analíticas
        tpv_div = tot_tpv if tot_tpv > 0 else 1.0
        matrix_report['rates']['Total Cost Rate%'].append((calculated_total_cost / tpv_div * 100) if tot_tpv > 0 else 0.0)
        matrix_report['rates']['Direct Rate%'].append((f['direct_cost'] / tpv_div * 100) if tot_tpv > 0 else 0.0)
        matrix_report['rates']['Interchange Rate%'].append((f['interchange'] / tpv_div * 100) if tot_tpv > 0 else 0.0)
        matrix_report['rates']['Other Direct Cost %'].append((f['other_direct'] / tpv_div * 100) if tot_tpv > 0 else 0.0)
        
        if metric_type == 'gross_profit_usd':
            matrix_report['rates']['IT Cost %'].append((f['it_cost'] / tpv_div * 100) if tot_tpv > 0 else 0.0)
            matrix_report['rates']['Other Indirect %'].append((f['other_indirect'] / tpv_div * 100) if tot_tpv > 0 else 0.0)
            matrix_report['rates']['Distributor Cost %'].append((f['dist_cost'] / tpv_div * 100) if tot_tpv > 0 else 0.0)

    conn.close()
    return jsonify(matrix_report)

# ─── TOP 20 MERCHANTS ─────────────────────────────────────────────────────────
@app.route('/api/merchants/top20')
def get_top_merchants():
    period = request.args.get('period')
    period2 = request.args.get('period2')
    metric = request.args.get('metric', 'gross_profit_usd')
    country = request.args.get('country', '')
    segment = request.args.get('segment', 'Todos')
        
    if 'gross_profit' in metric:
        metric = 'gross_profit_usd'
    elif 'net_revenue' in metric:
        metric = 'net_revenue_usd'

    # 🟢 DETECTAR CONDICIÓN ESPECIAL PARA CARD PRESENT EN MÉXICO
    is_mexico_cp = str(country).lower() in ['mexico', 'méxico'] and segment == 'Card Present'

    # 🟢 CONSTRUCCIÓN CENTRALIZADA DE FILTROS
    extra_where = []
    extra_params = []
    
    if country and str(country).strip() != '' and str(country).lower() not in ['todos', 'all', 'null', 'undefined', '']:
        extra_where.append("country = ?")
        extra_params.append(country)
        
        # Lógica de segmentos de México
        if str(country).lower() in ['mexico', 'méxico']:
            if segment == 'Card Present':
                extra_where.append("line_of_business = 'Billpocket'")
            elif segment == 'CNP':
                extra_where.append("line_of_business != 'Billpocket'")

    extra_where_str = f" AND {' AND '.join(extra_where)}" if extra_where else ""

    conn = get_connection()

    # 1. QUERY DE CUADRATURA ABSOLUTA (TOTALES MACRO)
    params_c = [period] + extra_params
    params_p = [period2] + extra_params

    tot_curr_raw = conn.execute(f"""
        SELECT SUM(tpv_usd) AS tpv, SUM(revenue_usd) AS revenue,
               SUM(net_revenue_usd) AS nr, SUM(gross_profit_usd) AS gp,
               SUM(total_cost_usd) AS cost
        FROM rpm_data 
        WHERE substr(date,1,7) = ? {extra_where_str}
    """, params_c).fetchone()

    tot_prior_raw = conn.execute(f"""
        SELECT SUM(tpv_usd) AS tpv, SUM(revenue_usd) AS revenue,
               SUM(net_revenue_usd) AS nr, SUM(gross_profit_usd) AS gp,
               SUM(total_cost_usd) AS cost
        FROM rpm_data 
        WHERE substr(date,1,7) = ? {extra_where_str}
    """, params_p).fetchone()

    tc = dict(tot_curr_raw) if tot_curr_raw else {}
    tp = dict(tot_prior_raw) if tot_prior_raw else {}

    tot_tpv_prior = tp.get('tpv') or 0.0
    tot_tpv_curr = tc.get('tpv') or 0.0
    tot_rev_prior = tp.get('revenue') or 0.0
    tot_rev_curr = tc.get('revenue') or 0.0
    
    # 🟢 CÁLCULO DE COSTO BASADO EN LA DIFERENCIA VS REVENUE
    if metric == 'gross_profit_usd':
        tot_cost_prior = (tp.get('revenue') or 0.0) - (tp.get('gp') or 0.0)
        tot_cost_curr = (tc.get('revenue') or 0.0) - (tc.get('gp') or 0.0)
    else:
        tot_cost_prior = (tp.get('revenue') or 0.0) - (tp.get('nr') or 0.0)
        tot_cost_curr = (tc.get('revenue') or 0.0) - (tc.get('nr') or 0.0)
    
    tot_prior_val = tp.get('gp' if metric == 'gross_profit_usd' else 'nr') or 0.0
    tot_current_val = tc.get('gp' if metric == 'gross_profit_usd' else 'nr') or 0.0
    tot_delta = tot_current_val - tot_prior_val

    # 🧮 FÓRMULAS MACRO A NIVEL PAÍS
    take_rate_prior = (tot_rev_prior / tot_tpv_prior) if tot_tpv_prior > 0 else 0.0
    take_rate_curr = (tot_rev_curr / tot_tpv_curr) if tot_tpv_curr > 0 else 0.0
    total_pricing = (take_rate_curr - take_rate_prior) * tot_tpv_curr
    
    cost_rate_prior = (tot_cost_prior / tot_tpv_prior) if tot_tpv_prior > 0 else 0.0
    cost_rate_curr = (tot_cost_curr / tot_tpv_curr) if tot_tpv_curr > 0 else 0.0
    
    total_cost_fx = (cost_rate_prior - cost_rate_curr) * tot_tpv_curr
        
    total_vol_mix = tot_delta - total_pricing - total_cost_fx

    total_row = {
        'tax_id': '—', 'merchant_name': 'TOTAL',
        'tpv': tot_tpv_curr, 'revenue': tot_rev_curr, 
        'tpv_prior': tot_tpv_prior, 'tpv_current': tot_tpv_curr,
        'revenue_prior': tot_rev_prior, 'revenue_current': tot_rev_curr,
        'tr_prior': take_rate_prior, 'tr_current': take_rate_curr,
        'cr_prior': cost_rate_prior, 'cr_current': cost_rate_curr,
        'cost_prior': tot_cost_prior, 'cost_current': tot_cost_curr,
        'prior_val': tot_prior_val, 'current_val': tot_current_val, 'delta': tot_delta,
        'pricing': total_pricing, 'cost_fx': total_cost_fx, 'vol_mix': total_vol_mix
    }

    # 2. EXTRAER Y CALCULAR DATOS DE COMERCIOS INDIVIDUALES (DINÁMICO POR PARTNER)
    def get_raw_merchants(p):
        if not p: return {}
        m_params = [p] + extra_params
        
        # 🟢 MAGIA AQUÍ: Si es México - Card Present, agrupamos por la columna 'partner' en la BD
        if is_mexico_cp:
            sql_query = f"""
                SELECT '—' AS tax_id, COALESCE(partner, 'Sin Clasificar') AS merchant_name,
                       SUM(tpv_usd) AS tpv, SUM(revenue_usd) AS revenue,
                       SUM(net_revenue_usd) AS nr, SUM(gross_profit_usd) AS gp,
                       SUM(total_cost_usd) AS cost
                FROM rpm_data 
                WHERE substr(date,1,7) = ? {extra_where_str}
                GROUP BY partner
            """
        else:
            sql_query = f"""
                SELECT tax_id, merchant_name,
                       SUM(tpv_usd) AS tpv, SUM(revenue_usd) AS revenue,
                       SUM(net_revenue_usd) AS nr, SUM(gross_profit_usd) AS gp,
                       SUM(total_cost_usd) AS cost
                FROM rpm_data 
                WHERE substr(date,1,7) = ? {extra_where_str}
                GROUP BY tax_id, merchant_name
            """
            
        rows = conn.execute(sql_query, m_params).fetchall()

        if is_mexico_cp:
            return {r['merchant_name']: dict(r) for r in rows}
        else:
            return {(r['tax_id'] or 'HUERFANO', r['merchant_name'] or 'Registros sin clasificar'): dict(r) for r in rows}

    curr_m = get_raw_merchants(period)
    prior_m = get_raw_merchants(period2)
    conn.close()

    all_keys = set(list(curr_m.keys()) + list(prior_m.keys()))
    all_merchants_calculated = []

    for key in all_keys:
        c = curr_m.get(key, {'tax_id':'—', 'merchant_name': key if is_mexico_cp else '', 'tpv':0.0, 'revenue':0.0, 'nr':0.0, 'gp':0.0, 'cost':0.0})
        p = prior_m.get(key, {'tax_id':'—', 'merchant_name': key if is_mexico_cp else '', 'tpv':0.0, 'revenue':0.0, 'nr':0.0, 'gp':0.0, 'cost':0.0})

        if is_mexico_cp:
            tax_id = '—'
            merchant_name = key
        else:
            tax_id, merchant_name = key

        c_tpv, p_tpv = c.get('tpv') or 0.0, p.get('tpv') or 0.0
        c_rev, p_rev = c.get('revenue') or 0.0, p.get('revenue') or 0.0
        
        # 🟢 CÁLCULO DE COSTO INDIVIDUAL BASADO EN DIFERENCIA VS REVENUE
        if metric == 'gross_profit_usd':
            c_cost = c_rev - (c.get('gp') or 0.0)
            p_cost = p_rev - (p.get('gp') or 0.0)
        else:
            c_cost = c_rev - (c.get('nr') or 0.0)
            p_cost = p_rev - (p.get('nr') or 0.0)
        
        c_val = c.get('gp' if metric == 'gross_profit_usd' else 'nr') or 0.0
        p_val = p.get('gp' if metric == 'gross_profit_usd' else 'nr') or 0.0
        delta = c_val - p_val

        tr_curr = c_rev / c_tpv if c_tpv > 0 else 0.0
        tr_prior = p_rev / p_tpv if p_tpv > 0 else 0.0
        pricing = (tr_curr - tr_prior) * c_tpv

        cr_curr = c_cost / c_tpv if c_tpv > 0 else 0.0
        cr_prior = p_cost / p_tpv if p_tpv > 0 else 0.0
        
        # El efecto costo siempre es (Tasa Anterior - Tasa Actual) * TPV Actual
        cost_fx = (cr_prior - cr_curr) * c_tpv

        vol_mix = delta - pricing - cost_fx

        if c_tpv > 0 or p_tpv > 0:
            all_merchants_calculated.append({
                'tax_id': '—' if tax_id == 'HUERFANO' else tax_id,
                'merchant_name': merchant_name,
                'tpv': c_tpv, 'revenue': c_rev,
                'tpv_prior': p_tpv, 'tpv_current': c_tpv,
                'revenue_prior': p_rev, 'revenue_current': c_rev,
                'tr_prior': tr_prior, 'tr_current': tr_curr,
                'cr_prior': cr_prior, 'cr_current': cr_curr,
                'cost_prior': p_cost, 'cost_current': c_cost,
                'prior_val': p_val, 'current_val': c_val, 'delta': delta,
                'pricing': pricing, 'cost_fx': cost_fx, 'vol_mix': vol_mix
            })

    # ─── NUEVA LÓGICA: TOP 15 POSITIVOS + TOP 5 NEGATIVOS ───
    
    # 1. Separar los comercios en positivos y negativos basados en el delta
    positives = [m for m in all_merchants_calculated if m['delta'] > 0]
    negatives = [m for m in all_merchants_calculated if m['delta'] < 0]
    
    # 2. Ordenar: 
    # Positivos de mayor a menor (los que más ganaron)
    positives.sort(key=lambda x: x['delta'], reverse=True)
    # Negativos de menor a mayor (los que más perdieron, es decir, el valor más pequeño/negativo primero)
    negatives.sort(key=lambda x: x['delta'])
    
    # 3. Extraer las cuotas solicitadas
    top_15_pos = positives[:15]
    top_5_neg = negatives[:5]
    
    # 4. Unir ambas listas para formar el nuevo grupo "Top 20"
    top_20 = top_15_pos + top_5_neg
    
    # 5. Opcional: Volver a ordenar la lista combinada final de mayor a menor 
    # para que visualmente en la tabla se vean desde el mayor ganador hasta el mayor perdedor
    top_20.sort(key=lambda x: x['delta'], reverse=True)

    # 3. ⚖️ FILA "OTROS" CALCULADA RESIDUALMENTE
    o_tpv_prior = total_row['tpv_prior'] - sum(m['tpv_prior'] for m in top_20)
    o_tpv_curr = total_row['tpv_current'] - sum(m['tpv_current'] for m in top_20)
    o_rev_prior = total_row['revenue_prior'] - sum(m['revenue_prior'] for m in top_20)
    o_rev_curr = total_row['revenue_current'] - sum(m['revenue_current'] for m in top_20)
    o_cost_prior = total_row['cost_prior'] - sum(m['cost_prior'] for m in top_20)
    o_cost_curr = total_row['cost_current'] - sum(m['cost_current'] for m in top_20)
    
    o_tr_prior = (o_rev_prior / o_tpv_prior) if o_tpv_prior > 0 else 0.0
    o_tr_curr = (o_rev_curr / o_tpv_curr) if o_tpv_curr > 0 else 0.0
    o_cr_prior = (o_cost_prior / o_tpv_prior) if o_tpv_prior > 0 else 0.0
    o_cr_curr = (o_cost_curr / o_tpv_curr) if o_tpv_curr > 0 else 0.0

    others_row = {
        'tax_id': '—', 'merchant_name': 'Otros (excl. top 20)',
        'tpv': o_tpv_curr, 'revenue': o_rev_curr,
        'tpv_prior': o_tpv_prior, 'tpv_current': o_tpv_curr,
        'revenue_prior': o_rev_prior, 'revenue_current': o_rev_curr,
        'tr_prior': o_tr_prior, 'tr_current': o_tr_curr,
        'cr_prior': o_cr_prior, 'cr_current': o_cr_curr,
        'prior_val': total_row['prior_val'] - sum(m['prior_val'] for m in top_20),
        'current_val': total_row['current_val'] - sum(m['current_val'] for m in top_20),
        'delta': total_row['delta'] - sum(m['delta'] for m in top_20),
        'pricing': total_row['pricing'] - sum(m['pricing'] for m in top_20),
        'cost_fx': total_row['cost_fx'] - sum(m['cost_fx'] for m in top_20),
        'vol_mix': total_row['vol_mix'] - sum(m['vol_mix'] for m in top_20)
    }

    return jsonify({
        'top20': top_20,
        'others': others_row,
        'total': total_row
    })

# ─── VENDOR VIEW ──────────────────────────────────────────────────────────────
@app.route('/api/vendors')
def get_vendors():
    # 1. Capturamos los parámetros del Frontend
    country = request.args.get('country', 'Todos')
    period = request.args.get('period', 'ALL')
    lob = request.args.get('lob', 'Todos')
    entity = request.args.get('entity', 'Todos')
    
    NOMBRE_TABLA = "cost_tracker"  
    conn = get_connection() 
    
    # 2. Determinación dinámica de los meses involucrados
    months = []
    if period == 'Q1':
        months = ['2026-01', '2026-02', '2026-03']
    elif period == 'Q2':
        months = ['2026-04', '2026-05', '2026-06']
    elif 'YTD' in period:
        try:
            max_month = int(period.split('-')[1])
        except:
            max_month = 5
        months = [f"2026-{str(i).zfill(2)}" for i in range(1, max_month + 1)]
    elif len(period) == 7:
        months = [period]
    else:
        months = ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05']

    # 🟢 NUEVO: EXTRACCIÓN DINÁMICA DEL TPV MENSUAL DEL PAÍS (Desde rpm_data)
    tpv_by_month = {}
    try:
        tpv_query = "SELECT substr(Fecha,1,7) as mes, SUM(tpv) as total_tpv FROM rpm_data WHERE country LIKE ? GROUP BY mes"
        cursor_tpv = conn.execute(tpv_query, [country])
        for r_tpv in cursor_tpv.fetchall():
            tpv_by_month[r_tpv[0]] = float(r_tpv[1] or 0)
    except Exception as e_tpv:
        # Salvaguarda por si el campo en tu tabla rpm_data se llama 'tpv_usd'
        try:
            tpv_query = "SELECT substr(Fecha,1,7) as mes, SUM(tpv_usd) as total_tpv FROM rpm_data WHERE country LIKE ? GROUP BY mes"
            cursor_tpv = conn.execute(tpv_query, [country])
            for r_tpv in cursor_tpv.fetchall():
                tpv_by_month[r_tpv[0]] = float(r_tpv[1] or 0)
        except:
            print("⚠️ Nota de diagnóstico: No se pudo mapear el TPV mensual para las tasas:", str(e_tpv))

    where_clauses = []
    params = []
    
    # Filtro País inmunizado (Conservado intacto)
    if country and country.lower() not in ['todos', 'all', '']:
        if country.lower() in ['mexico', 'méxico']:
            where_clauses.append("(country LIKE 'Mexico' OR country LIKE 'México' OR country LIKE 'MÉXICO')")
        elif country.lower() in ['peru', 'perú']:
            where_clauses.append("(country LIKE 'Peru' OR country LIKE 'Perú' OR country LIKE 'PERÚ')")
        else:
            where_clauses.append("country LIKE ?")
            params.append(f"{country}")
            
    # Filtro LOB Multi-select (Conservado intacto)
    if lob and 'todos' not in lob.lower() and lob != '':
        lob_list = lob.split(',')  
        placeholders = ",".join(["?"] * len(lob_list))  
        where_clauses.append(f"lob IN ({placeholders})")  
        params.extend(lob_list)  
        
    # Filtro Legal Entity Optimizado (Conservado intacto)
    if entity and entity.lower() not in ['todos', 'all', '']:
        where_clauses.append("legal_entity LIKE ?")
        params.append(f"{entity}")
        
    # Restricción de meses (Conservado intacto)
    if months:
        placeholders = ",".join(["?"] * len(months))
        where_clauses.append(f"substr(Fecha,1,7) IN ({placeholders})")
        params.extend(months)

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    # Construimos las columnas mensuales dinámicas
    select_parts = []
    for m in months:
        select_parts.append(f'SUM(CASE WHEN substr(Fecha,1,7) = "{m}" THEN importe_usd ELSE 0 END) as "{m}"')
    
    select_months_str = ", " + ", ".join(select_parts) if select_parts else ""
    
    # Tu consulta SQL unificada por proveedor (Conservada intacta)
    query = f"""
        SELECT proveedor, country, 
               MAX(type) as type, 
               MAX(subtype) as subtype, 
               MAX(lob) as lob, 
               SUM(importe_usd) as total_importe_usd 
               {select_months_str}
        FROM {NOMBRE_TABLA}
        {where_str}
        GROUP BY proveedor, country
        ORDER BY SUM(importe_usd) DESC
    """
    
    # Líneas espías de diagnóstico en consola
    print("🔍 SQL EJECUTADO:", query)
    print("📦 PARÁMETROS PASADOS:", params)
    
    try:
        cursor = conn.execute(query, params)
        columns = [column[0] for column in cursor.description]
        raw_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        
        # 🟢 NUEVO PROCESADOR MULTI-MÉTRICA POST-QUERY
        rich_rows = []
        for row in raw_rows:
            rich_row = {
                "proveedor": row["proveedor"],
                "country": row["country"],
                "type": row["type"],
                "subtype": row["subtype"],
                "lob": row["lob"],
                "total_importe_usd": row["total_importe_usd"],
                "months_data": {}
            }
            
            for i, m in enumerate(months):
                current_val = float(row.get(m) or 0)
                
                # 1. Delta MoM (Como arranca en Enero y no hay Diciembre anterior, fuerza a 0)
                delta = 0.0
                if i > 0:
                    prev_month = months[i-1]
                    prev_val = float(row.get(prev_month) or 0)
                    delta = current_val - prev_val
                
                # 2. Tasa Cost Rate = (Gasto Proveedor / TPV País en este mes) * 100
                month_tpv = tpv_by_month.get(m, 0)
                cost_rate = (current_val / month_tpv * 100) if month_tpv > 0 else 0.0
                
                # Empaquetamos el sub-objeto mensual para el Frontend
                rich_row["months_data"][m] = {
                    "value": current_val,
                    "delta": delta,
                    "rate": cost_rate
                }
            rich_rows.append(rich_row)
        
        # Retornamos el payload estructurado
        return jsonify({
            "months": months,
            "rows": rich_rows
        })
        
    except Exception as e:
        if conn: conn.close()
        print("❌ ERROR EN MATRIZ DE VENDORS:", str(e))
        return jsonify({"error": str(e), "months": [], "rows": []}), 500

# ─── COMMENTS ─────────────────────────────────────────────────────────────────
@app.route('/api/comments', methods=['GET'])
def get_comments():
    period  = request.args.get('period')
    section = request.args.get('section')
    parts, params = ["1=1"], []
    if period:
        parts.append("period = ?"); params.append(period)
    if section:
        parts.append("section = ?"); params.append(section)
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM comments WHERE {' AND '.join(parts)} ORDER BY created_at DESC",
        params
    ).fetchall()
    conn.close()
    return jsonify({'comments': [dict(r) for r in rows]})


@app.route('/api/comments', methods=['POST'])
def create_comment():
    data    = request.get_json()
    period  = data.get('period')
    section = data.get('section', 'overview')
    text    = data.get('comment_text')
    author  = data.get('author', 'Diana')
    if not period or not text:
        return jsonify({'error': 'period y comment_text son requeridos'}), 400
    conn = get_connection()
    cur  = conn.execute(
        "INSERT INTO comments (period, section, comment_text, author) VALUES (?,?,?,?)",
        [period, section, text, author]
    )
    conn.commit()
    new = dict(conn.execute("SELECT * FROM comments WHERE id = ?", [cur.lastrowid]).fetchone())
    conn.close()
    return jsonify({'comment': new}), 201


@app.route('/api/comments/<int:cid>', methods=['PUT'])
def update_comment(cid):
    text = request.get_json().get('comment_text')
    if not text:
        return jsonify({'error': 'comment_text es requerido'}), 400
    conn = get_connection()
    conn.execute(
        "UPDATE comments SET comment_text=?, updated_at=datetime('now') WHERE id=?",
        [text, cid]
    )
    conn.commit()
    row = conn.execute("SELECT * FROM comments WHERE id=?", [cid]).fetchone()
    conn.close()
    return jsonify({'comment': dict(row)}) if row else (jsonify({'error': 'No encontrado'}), 404)


@app.route('/api/comments/<int:cid>', methods=['DELETE'])
def delete_comment(cid):
    conn = get_connection()
    conn.execute("DELETE FROM comments WHERE id=?", [cid])
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
import os

if __name__ == '__main__':
    # Tomar el puerto que asignará Render dinámicamente en la nube
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
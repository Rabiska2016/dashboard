from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import os, json, calendar
from datetime import date
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'rabiska_secret_2024')

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL:
    import psycopg2, psycopg2.extras
    USE_PG = True
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
else:
    import sqlite3
    USE_PG = False
    DATABASE_SQLITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rabiska.db')

PASSWORD = os.environ.get('RABISKA_PASSWORD', 'rabiska2016')
UNITS = {
    'niteroi': {'name': 'Niteroi', 'currency': 'R$'},
    'barra':   {'name': 'Barra',   'currency': 'R$'},
    'cascais': {'name': 'Cascais', 'currency': 'EUR'},
    'london':  {'name': 'London',  'currency': 'GBP'},
}
CAT_RECEITA = ['Tatuagem','Piercing','Produto','Consulta','Flash Day','Outros']
CAT_DESPESA = ['Aluguel','Material','Salarios','Marketing','Equipamentos','Utilities','Software','Viagem','Outros']

def get_db():
    if USE_PG:
        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    conn = sqlite3.connect(DATABASE_SQLITE)
    conn.row_factory = sqlite3.Row
    return conn

def db_all(conn, sql, p=()):
    if USE_PG:
        sql = sql.replace('?','%s')
        cur = conn.cursor(); cur.execute(sql,p); r = cur.fetchall(); cur.close(); return r
    return conn.execute(sql,p).fetchall()

def db_one(conn, sql, p=()):
    if USE_PG:
        sql = sql.replace('?','%s')
        cur = conn.cursor(); cur.execute(sql,p); r = cur.fetchone(); cur.close(); return r
    return conn.execute(sql,p).fetchone()

def db_run(conn, sql, p=()):
    if USE_PG:
        sql = sql.replace('?','%s')
        cur = conn.cursor(); cur.execute(sql,p); cur.close()
    else:
        conn.execute(sql,p)

def init_db():
    conn = get_db()
    if USE_PG:
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, unit TEXT, type TEXT, category TEXT, description TEXT, amount REAL, date TEXT, artist_id INTEGER, created_at TIMESTAMP DEFAULT NOW())')
        cur.execute('CREATE TABLE IF NOT EXISTS artists (id SERIAL PRIMARY KEY, unit TEXT, name TEXT, commission_rate REAL DEFAULT 40, active INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW())')
        conn.commit(); cur.close()
    else:
        conn.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, unit TEXT, type TEXT, category TEXT, description TEXT, amount REAL, date TEXT, artist_id INTEGER, created_at TEXT DEFAULT (datetime('now')))")
        conn.execute("CREATE TABLE IF NOT EXISTS artists (id INTEGER PRIMARY KEY AUTOINCREMENT, unit TEXT, name TEXT, commission_rate REAL DEFAULT 40, active INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now')))")
        conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def dec(*a,**k):
        if 'unit' not in session: return redirect(url_for('login'))
        return f(*a,**k)
    return dec

def month_range(y,m):
    import calendar as cal
    _,last = cal.monthrange(y,m)
    return f"{y}-{m:02d}-01", f"{y}-{m:02d}-{last:02d}"

def last_n_months(n=12):
    today = date.today(); result = []
    for i in range(n-1,-1,-1):
        tm = today.month-1-i; yr = today.year+tm//12; mo = tm%12+1
        result.append((yr,mo))
    return result

def sum_p(conn,unit,typ,s,e):
    sql = "SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE unit=? AND type=? AND date BETWEEN ? AND ?"
    if USE_PG:
        sql=sql.replace('?','%s'); cur=conn.cursor(); cur.execute(sql,(unit,typ,s,e)); v=cur.fetchone(); cur.close()
        return float(list(v.values())[0]) if v else 0.0
    row=conn.execute(sql,(unit,typ,s,e)).fetchone(); return float(row[0]) if row and row[0] else 0.0

@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=request.form.get('unit','').strip(); pw=request.form.get('password','').strip()
        if u in UNITS and pw==PASSWORD:
            session['unit']=u; return redirect(url_for('dashboard'))
        flash('Senha incorreta.','error')
    return render_template('login.html',units=UNITS)

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    unit=session['unit']; ui=UNITS[unit]; conn=get_db()
    today=date.today(); ms,me=month_range(today.year,today.month)
    mr=sum_p(conn,unit,'receita',ms,me); md=sum_p(conn,unit,'despesa',ms,me)
    tr=sum_p(conn,unit,'receita','2000-01-01','2099-12-31'); td=sum_p(conn,unit,'despesa','2000-01-01','2099-12-31')
    recent=db_all(conn,'SELECT t.*,a.name as artist_name FROM transactions t LEFT JOIN artists a ON t.artist_id=a.id WHERE t.unit=? ORDER BY t.date DESC LIMIT 8',(unit,))
    top=db_one(conn,"SELECT a.name,COALESCE(SUM(t.amount),0) as total FROM artists a LEFT JOIN transactions t ON a.id=t.artist_id AND t.unit=? AND t.type='receita' AND t.date BETWEEN ? AND ? WHERE a.unit=? AND a.active=1 GROUP BY a.id,a.name ORDER BY total DESC LIMIT 1",(unit,ms,me,unit))
    monthly=[]
    for yr,mo in last_n_months(6):
        s,e=month_range(yr,mo); r=sum_p(conn,unit,'receita',s,e); d=sum_p(conn,unit,'despesa',s,e)
        monthly.append({'month':f"{mo:02d}/{yr}",'receitas':round(r,2),'despesas':round(d,2),'lucro':round(r-d,2)})
    conn.close()
    return render_template('dashboard.html',active='dashboard',unit=unit,unit_info=ui,
        mes_rec=mr,mes_desp=md,mes_lucro=mr-md,tot_rec=tr,tot_desp=td,
        recent=recent,top_artist=top,monthly_data=json.dumps(monthly))

@app.route('/transactions',methods=['GET','POST'])
@login_required
def transactions():
    unit=session['unit']; ui=UNITS[unit]; conn=get_db()
    if request.method=='POST':
        act=request.form.get('action')
        if act=='add':
            db_run(conn,"INSERT INTO transactions (unit,type,category,description,amount,date,artist_id) VALUES (?,?,?,?,?,?,?)",
                (unit,request.form.get('type'),request.form.get('category'),request.form.get('description',''),
                float(request.form.get('amount',0)),request.form.get('date'),request.form.get('artist_id') or None))
            conn.commit(); flash('Transacao registrada!','success')
        elif act=='delete':
            db_run(conn,"DELETE FROM transactions WHERE id=? AND unit=?",(request.form.get('id'),unit))
            conn.commit()
        conn.close(); return redirect(url_for('transactions'))
    ft=request.args.get('type','all'); fm=request.args.get('month','')
    sql="SELECT t.*,a.name as artist_name FROM transactions t LEFT JOIN artists a ON t.artist_id=a.id WHERE t.unit=?"; p=[unit]
    if ft!='all': sql+=" AND t.type=?"; p.append(ft)
    if fm:
        sql+=(" AND TO_CHAR(TO_DATE(t.date,'YYYY-MM-DD'),'YYYY-MM')=?" if USE_PG else " AND strftime('%Y-%m',t.date)=?"); p.append(fm)
    sql+=" ORDER BY t.date DESC"
    trans=db_all(conn,sql,p); arts=db_all(conn,"SELECT * FROM artists WHERE unit=? AND active=1 ORDER BY name",(unit,))
    conn.close()
    return render_template('transactions.html',active='transactions',unit=unit,unit_info=ui,
        transactions=trans,artists=arts,cat_receita=CAT_RECEITA,cat_despesa=CAT_DESPESA,
        f_type=ft,f_month=fm,today=date.today().isoformat())

@app.route('/cashflow')
@login_required
def cashflow():
    unit=session['unit']; ui=UNITS[unit]; conn=get_db()
    monthly=[]
    for yr,mo in last_n_months(12):
        s,e=month_range(yr,mo); r=sum_p(conn,unit,'receita',s,e); d=sum_p(conn,unit,'despesa',s,e)
        monthly.append({'month':f"{mo:02d}/{yr}",'receitas':round(r,2),'despesas':round(d,2),'lucro':round(r-d,2)})
    rc=db_all(conn,"SELECT category,SUM(amount) as total FROM transactions WHERE unit=? AND type='receita' GROUP BY category ORDER BY total DESC",(unit,))
    dc=db_all(conn,"SELECT category,SUM(amount) as total FROM transactions WHERE unit=? AND type='despesa' GROUP BY category ORDER BY total DESC",(unit,))
    conn.close()
    return render_template('cashflow.html',active='cashflow',unit=unit,unit_info=ui,
        monthly_data=json.dumps(monthly),
        rec_cat=json.dumps([{'label':dict(r)['category'],'value':round(float(dict(r)['total']),2)} for r in rc]),
        desp_cat=json.dumps([{'label':dict(d)['category'],'value':round(float(dict(d)['total']),2)} for d in dc]))

@app.route('/artists',methods=['GET','POST'])
@login_required
def artists():
    unit=session['unit']; ui=UNITS[unit]; conn=get_db()
    if request.method=='POST':
        act=request.form.get('action')
        if act=='add':
            n=request.form.get('name','').strip()
            if n:
                db_run(conn,"INSERT INTO artists (unit,name,commission_rate) VALUES (?,?,?)",(unit,n,float(request.form.get('commission_rate',40))))
                conn.commit(); flash(f'{n} adicionado!','success')
        elif act=='delete':
            db_run(conn,"UPDATE artists SET active=0 WHERE id=? AND unit=?",(request.form.get('id'),unit))
            conn.commit()
        conn.close(); return redirect(url_for('artists'))
    today=date.today(); ms,me=month_range(today.year,today.month)
    ad=db_all(conn,"SELECT a.id,a.name,a.commission_rate,COALESCE(SUM(CASE WHEN t.type='receita' THEN t.amount ELSE 0 END),0) as total_rec,COALESCE(SUM(CASE WHEN t.type='receita' THEN t.amount*a.commission_rate/100 ELSE 0 END),0) as comissao,COALESCE(SUM(CASE WHEN t.type='receita' AND t.date BETWEEN ? AND ? THEN t.amount ELSE 0 END),0) as mes_rec,COUNT(CASE WHEN t.type='receita' THEN 1 END) as sessoes FROM artists a LEFT JOIN transactions t ON a.id=t.artist_id AND t.unit=a.unit WHERE a.unit=? AND a.active=1 GROUP BY a.id,a.name,a.commission_rate ORDER BY total_rec DESC",(ms,me,unit))
    conn.close()
    return render_template('artists.html',active='artists',unit=unit,unit_info=ui,artists=[dict(a) for a in ad])

@app.route('/api/categories')
@login_required
def api_categories():
    return jsonify(CAT_RECEITA if request.args.get('type')=='receita' else CAT_DESPESA)

if __name__=='__main__':
    init_db()
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=False)

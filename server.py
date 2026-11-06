from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path
import sqlite3, json, hashlib, hmac, secrets, os, mimetypes

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / 'data' / 'mesa_ayuda.db'
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '5100'))
SESSIONS = {}


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 180000)
    return salt.hex() + ':' + digest.hex()


def password_ok(password, stored):
    salt_hex, digest_hex = stored.split(':', 1)
    candidate = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), 180000).hex()
    return hmac.compare_digest(candidate, digest_hex)


def init_db():
    with connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','tech')),
          job TEXT DEFAULT '', area TEXT DEFAULT '', location TEXT DEFAULT '', phone TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS tickets (
          id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
          user_id INTEGER NOT NULL REFERENCES users(id), subject TEXT NOT NULL,
          asset_type TEXT NOT NULL, asset_tag TEXT DEFAULT '', asset_model TEXT DEFAULT '',
          serial TEXT DEFAULT '', asset_name TEXT DEFAULT '', priority TEXT NOT NULL DEFAULT 'Media',
          status TEXT NOT NULL DEFAULT 'Abierto', started TEXT DEFAULT '', description TEXT NOT NULL,
          steps TEXT NOT NULL, attempts TEXT DEFAULT '', attachment TEXT DEFAULT '',
          assignee_id INTEGER REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS updates (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id), message TEXT NOT NULL, created_at TEXT NOT NULL
        );
        ''')
        if con.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
            examples = [
              ('Ana María Rojas','usuario@demo.com','usuario123','user','Analista contable','Contabilidad','Sede principal · Piso 3','Ext. 204'),
              ('Carlos Méndez','tecnico@demo.com','tecnico123','tech','Técnico de soporte','Tecnología','Mesa de ayuda','Ext. 100'),
            ]
            for name,email,pw,role,job,area,location,phone in examples:
                con.execute('INSERT INTO users(name,email,password_hash,role,job,area,location,phone) VALUES(?,?,?,?,?,?,?,?)',
                            (name,email,password_hash(pw),role,job,area,location,phone))


def user_json(row):
    return {k: row[k] for k in ('id','name','email','role','job','area','location','phone')}


def ticket_json(row):
    return {
      'id': row['code'], 'subject': row['subject'], 'assetType': row['asset_type'],
      'assetTag': row['asset_tag'], 'assetModel': row['asset_model'], 'serial': row['serial'],
      'assetName': row['asset_name'], 'priority': row['priority'], 'status': row['status'],
      'started': row['started'], 'description': row['description'], 'steps': row['steps'],
      'attempts': row['attempts'], 'attachment': row['attachment'], 'createdAt': row['created_at'],
      'updatedAt': row['updated_at'], 'name': row['name'], 'email': row['email'],
      'job': row['job'], 'area': row['area'], 'location': row['location'], 'phone': row['phone'],
      'assignee': row['assignee_email'], 'assigneeName': row['assignee_name'],
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print('[%s] %s' % (self.log_date_time_string(), fmt % args))

    def send_json(self, obj, status=200, extra_headers=None):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        if extra_headers:
            for key, value in extra_headers.items(): self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        length = min(int(self.headers.get('Content-Length', '0')), 1000000)
        raw = self.rfile.read(length)
        return json.loads(raw or b'{}')

    def current_user(self):
        cookie = self.headers.get('Cookie', '')
        sid = next((p.strip().split('=',1)[1] for p in cookie.split(';') if p.strip().startswith('sid=')), None)
        return SESSIONS.get(sid)

    def require_user(self):
        u = self.current_user()
        if not u: self.send_json({'error':'Inicia sesión para continuar.'}, 401)
        return u

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith('/api/'):
            u = self.require_user()
            if not u: return
            if path == '/api/me': return self.send_json({'user':u})
            if path == '/api/tickets':
                with connect() as con:
                    q = '''SELECT t.*,u.name,u.email,u.job,u.area,u.location,u.phone,
                           tech.email assignee_email,tech.name assignee_name
                           FROM tickets t JOIN users u ON u.id=t.user_id
                           LEFT JOIN users tech ON tech.id=t.assignee_id'''
                    args = []
                    if u['role'] == 'user': q += ' WHERE t.user_id=?'; args.append(u['id'])
                    q += ' ORDER BY t.updated_at DESC'
                    return self.send_json({'tickets':[ticket_json(r) for r in con.execute(q,args)]})
            if path.startswith('/api/tickets/'):
                code = path.rsplit('/',1)[-1]
                with connect() as con:
                    r = con.execute('''SELECT t.*,u.name,u.email,u.job,u.area,u.location,u.phone,tech.email assignee_email,tech.name assignee_name
                        FROM tickets t JOIN users u ON u.id=t.user_id LEFT JOIN users tech ON tech.id=t.assignee_id WHERE t.code=?''',(code,)).fetchone()
                    if not r: return self.send_json({'error':'Ticket no encontrado.'},404)
                    if u['role']=='user' and r['user_id'] != u['id']: return self.send_json({'error':'Sin permiso.'},403)
                    events = con.execute('SELECT x.message,x.created_at,x.user_id,u.name FROM updates x JOIN users u ON u.id=x.user_id WHERE x.ticket_id=? ORDER BY x.id',(r['id'],)).fetchall()
                    return self.send_json({'ticket':ticket_json(r),'events':[{'text':x['message'],'at':x['created_at'],'by':x['name']} for x in events]})
            if path == '/api/technicians' and u['role']=='tech':
                with connect() as con:
                    return self.send_json({'technicians':[user_json(r) for r in con.execute("SELECT * FROM users WHERE role='tech'")]})
            return self.send_json({'error':'Ruta no encontrada.'},404)
        if path == '/': self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try: data = self.body()
        except (json.JSONDecodeError, ValueError): return self.send_json({'error':'Solicitud inválida.'},400)
        if path == '/api/login':
            email = str(data.get('email','')).strip().lower(); password = str(data.get('password',''))
            with connect() as con: row = con.execute('SELECT * FROM users WHERE lower(email)=?',(email,)).fetchone()
            if not row or not password_ok(password,row['password_hash']): return self.send_json({'error':'Correo o contraseña incorrectos.'},401)
            sid = secrets.token_urlsafe(32); user = user_json(row); SESSIONS[sid] = user
            return self.send_json({'user':user},extra_headers={'Set-Cookie':f'sid={sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800'})
        if path == '/api/logout':
            cookie=self.headers.get('Cookie',''); sid=next((p.strip().split('=',1)[1] for p in cookie.split(';') if p.strip().startswith('sid=')),None)
            if sid: SESSIONS.pop(sid,None)
            return self.send_json({'ok':True},extra_headers={'Set-Cookie':'sid=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'})
        u = self.require_user()
        if not u: return
        if path == '/api/tickets':
            required=['subject','assetType','priority','description','steps','job','area','location']
            if any(not str(data.get(k,'')).strip() for k in required): return self.send_json({'error':'Completa todos los campos obligatorios.'},400)
            import datetime
            now=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            with connect() as con:
                con.execute('UPDATE users SET job=?,area=?,location=?,phone=? WHERE id=?',(data.get('job',''),data.get('area',''),data.get('location',''),data.get('phone',''),u['id']))
                cur=con.execute('''INSERT INTO tickets(user_id,subject,asset_type,asset_tag,asset_model,serial,asset_name,priority,status,started,description,steps,attempts,attachment,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,?,?,'Abierto',?,?,?,?,?,?,?)''',(u['id'],data['subject'],data['assetType'],data.get('assetTag',''),data.get('assetModel',''),data.get('serial',''),data.get('assetName',''),data['priority'],data.get('started',''),data['description'],data['steps'],data.get('attempts',''),data.get('attachment',''),now,now))
                code=f"HD-{datetime.datetime.now().year}-{cur.lastrowid:05d}"
                con.execute('UPDATE tickets SET code=? WHERE id=?',(code,cur.lastrowid))
                con.execute('INSERT INTO updates(ticket_id,user_id,message,created_at) VALUES(?,?,?,?)',(cur.lastrowid,u['id'],'Ticket creado',now))
            return self.send_json({'id':code},201)
        if path.startswith('/api/tickets/') and path.endswith('/updates'):
            if u['role']!='tech': return self.send_json({'error':'Solo el técnico puede agregar actualizaciones.'},403)
            code=path.split('/')[-2]; message=str(data.get('message','')).strip()
            if not message:return self.send_json({'error':'Escribe una actualización.'},400)
            return self.add_update(code,u,message)
        return self.send_json({'error':'Ruta no encontrada.'},404)

    def add_update(self,code,u,message):
        import datetime
        now=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
        with connect() as con:
            row=con.execute('SELECT id FROM tickets WHERE code=?',(code,)).fetchone()
            if not row:return self.send_json({'error':'Ticket no encontrado.'},404)
            con.execute('INSERT INTO updates(ticket_id,user_id,message,created_at) VALUES(?,?,?,?)',(row['id'],u['id'],message,now))
            con.execute('UPDATE tickets SET updated_at=? WHERE id=?',(now,row['id']))
        return self.send_json({'ok':True},201)

    def do_PATCH(self):
        u=self.require_user()
        if not u:return
        if u['role']!='tech':return self.send_json({'error':'Solo el técnico puede gestionar tickets.'},403)
        path=urlparse(self.path).path
        if not path.startswith('/api/tickets/'):return self.send_json({'error':'Ruta no encontrada.'},404)
        code=path.rsplit('/',1)[-1]
        try:data=self.body()
        except (json.JSONDecodeError,ValueError):return self.send_json({'error':'Solicitud inválida.'},400)
        valid_status={'Abierto','En progreso','Esperando usuario','Resuelto','Cerrado'}; valid_priority={'Baja','Media','Alta','Crítica'}
        if data.get('status') not in valid_status or data.get('priority') not in valid_priority:return self.send_json({'error':'Estado o prioridad no válida.'},400)
        import datetime
        now=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
        with connect() as con:
            row=con.execute('SELECT id,status,priority,assignee_id FROM tickets WHERE code=?',(code,)).fetchone()
            if not row:return self.send_json({'error':'Ticket no encontrado.'},404)
            tech_id=None
            if data.get('assignee'):
                tech=con.execute("SELECT id FROM users WHERE email=? AND role='tech'",(data['assignee'],)).fetchone()
                if not tech:return self.send_json({'error':'Técnico no válido.'},400)
                tech_id=tech['id']
            con.execute('UPDATE tickets SET status=?,priority=?,assignee_id=?,updated_at=? WHERE id=?',(data['status'],data['priority'],tech_id,now,row['id']))
            for key,label in [('status','Estado'),('priority','Prioridad')]:
                if row[key]!=data[key]:con.execute('INSERT INTO updates(ticket_id,user_id,message,created_at) VALUES(?,?,?,?)',(row['id'],u['id'],f"{label} actualizado a {data[key]}",now))
            if row['assignee_id']!=tech_id:con.execute('INSERT INTO updates(ticket_id,user_id,message,created_at) VALUES(?,?,?,?)',(row['id'],u['id'],'Técnico asignado actualizado',now))
        return self.send_json({'ok':True})

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','same-origin')
        super().end_headers()


if __name__ == '__main__':
    init_db()
    print(f'Mesa de ayuda disponible en http://localhost:{PORT}')
    print(f'Escuchando en {HOST}:{PORT}. Para acceso en LAN usa la IP de este equipo.')
    try: ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
    except KeyboardInterrupt: print('\nServidor detenido.')

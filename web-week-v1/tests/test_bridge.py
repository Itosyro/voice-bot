import importlib.util, json, sqlite3, threading, tempfile
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

p=Path(__file__).parents[1] / 'weekly_web_bridge.py'
spec=importlib.util.spec_from_file_location('wwb',p); m=importlib.util.module_from_spec(spec); import sys; sys.modules[spec.name]=m; spec.loader.exec_module(m)


def mkdb(path):
    now=datetime.now(timezone.utc).isoformat(); day=datetime.now(timezone.utc).date().isoformat()
    with sqlite3.connect(path) as db:
        db.executescript('''
        CREATE TABLE users(chat_id INTEGER PRIMARY KEY, telegram_user_id INTEGER, username TEXT, first_name TEXT, timezone TEXT, quiet_start TEXT, quiet_end TEXT, authorized INTEGER, pending_occurrence_id INTEGER, created_at_utc TEXT, updated_at_utc TEXT);
        CREATE TABLE event_log(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,event_type TEXT,payload_json TEXT,created_at_utc TEXT);
        CREATE TABLE schedule_items(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,title TEXT,kind TEXT,recurrence TEXT,date_local TEXT,weekdays_mask INTEGER,start_local TEXT,duration_minutes INTEGER,reminder_minutes INTEGER,enabled INTEGER,created_at_utc TEXT,updated_at_utc TEXT);
        CREATE TABLE schedule_occurrences(id INTEGER PRIMARY KEY AUTOINCREMENT,schedule_item_id INTEGER,chat_id INTEGER,due_date_local TEXT,title TEXT,kind TEXT,start_at_utc TEXT,end_at_utc TEXT,reminder_minutes INTEGER,status TEXT,reminder_sent_at_utc TEXT,snoozed_until_utc TEXT,completed_at_utc TEXT,created_at_utc TEXT);
        ''')
        db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?,?,?)',(7,7,'u','U','UTC','23:00','09:00',1,None,now,now))
        db.execute('INSERT INTO schedule_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(1,7,'Работа в кафе','work','weekly',None,127,'18:00',120,30,1,now,now))
        db.execute('INSERT INTO schedule_occurrences VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(1,1,7,day,'Работа в кафе','work',now,now,30,'pending',None,None,None,now))

class Server:
    def __init__(self):
        self.rev=1; self.state={'version':1,'tasks':[],'sessions':[],'proofs':[],'checkins':{},'plans':{},'ladder':{}}
        owner=self
        class H(BaseHTTPRequestHandler):
            def log_message(self,*a): pass
            def out(self,p,c=200):
                b=json.dumps(p).encode(); self.send_response(c); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
            def do_GET(self):
                assert self.headers.get('X-ExeDev-UserID')=='local-abc'
                if self.path=='/api/health': self.out({'ok':True})
                elif self.path=='/api/state': self.out({'ok':True,'revision':owner.rev,'state':owner.state})
                else: self.out({},404)
            def do_PUT(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if data['baseRevision']!=owner.rev: return self.out({'ok':False},409)
                owner.state=data['state']; owner.rev+=1; self.out({'ok':True,'revision':owner.rev})
        self.http=ThreadingHTTPServer(('127.0.0.1',0),H); self.t=threading.Thread(target=self.http.serve_forever,daemon=True)
    def __enter__(self): self.t.start(); return self
    def __exit__(self,*a): self.http.shutdown(); self.t.join(); self.http.server_close()
    @property
    def url(self): return f'http://127.0.0.1:{self.http.server_address[1]}'


def test_bridge_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); db=td/'tg.db'; mkdb(db); env=td/'bridge.env'; env.write_text('DVIZH_WEB_USER_ID="local-abc"\nDVIZH_WEB_USER_EMAIL="x@y"\n')
        with Server() as s:
            cfg=m.Config(str(db),s.url,str(env),str(td/'none.json'),str(td/'status.json'),5,3)
            r=m.sync_once(cfg); assert r['changed'] and s.state['weeklySchedule']['occurrences'][0]['status']=='pending'
            s.state['weeklySchedule']['occurrences'][0]['status']='done'; s.state['weeklySchedule']['occurrences'][0]['webUpdatedAt']='now'; s.rev+=1
            r=m.sync_once(cfg); assert r['weekDoneImported']==1
            with sqlite3.connect(db) as q: assert q.execute('select status from schedule_occurrences where id=1').fetchone()[0]=='done'
            r=m.sync_once(cfg); assert not r['changed']

import importlib.util
import json
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODULE = Path(__file__).parents[1] / 'web_schedule_editor_bridge.py'
spec = importlib.util.spec_from_file_location('editor_bridge', MODULE)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
assert spec.loader
spec.loader.exec_module(mod)


def mkdb(path: Path):
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as db:
        db.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE users(chat_id INTEGER PRIMARY KEY, telegram_user_id INTEGER, username TEXT, first_name TEXT, timezone TEXT, quiet_start TEXT, quiet_end TEXT, authorized INTEGER, pending_occurrence_id INTEGER, created_at_utc TEXT, updated_at_utc TEXT);
        CREATE TABLE event_log(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,event_type TEXT,payload_json TEXT,created_at_utc TEXT);
        CREATE TABLE schedule_items(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER NOT NULL,title TEXT NOT NULL,kind TEXT NOT NULL,recurrence TEXT NOT NULL,date_local TEXT,weekdays_mask INTEGER,start_local TEXT NOT NULL,duration_minutes INTEGER NOT NULL,reminder_minutes INTEGER NOT NULL,enabled INTEGER NOT NULL,created_at_utc TEXT NOT NULL,updated_at_utc TEXT NOT NULL);
        CREATE TABLE schedule_occurrences(id INTEGER PRIMARY KEY AUTOINCREMENT,schedule_item_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,due_date_local TEXT NOT NULL,title TEXT NOT NULL,kind TEXT NOT NULL,start_at_utc TEXT NOT NULL,end_at_utc TEXT NOT NULL,reminder_minutes INTEGER NOT NULL,status TEXT NOT NULL,reminder_sent_at_utc TEXT,snoozed_until_utc TEXT,completed_at_utc TEXT,created_at_utc TEXT NOT NULL,UNIQUE(schedule_item_id,due_date_local),FOREIGN KEY(schedule_item_id) REFERENCES schedule_items(id) ON DELETE CASCADE);
        ''')
        db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?,?,?)', (7,7,'u','U','UTC','23:00','09:00',1,None,now,now))


class Server:
    def __init__(self):
        self.rev = 1
        self.state = {'version':1,'tasks':[],'sessions':[],'proofs':[],'checkins':{},'weeklySchedule':{'version':1,'items':[],'occurrences':[],'webCommands':[]}}
        owner = self
        class H(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def out(self,payload,status=200):
                raw=json.dumps(payload).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_GET(self):
                assert self.headers.get('X-ExeDev-UserID') == 'auth-user'
                if self.path == '/api/state': self.out({'ok':True,'revision':owner.rev,'state':owner.state})
                else: self.out({'ok':True})
            def do_PUT(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if data['baseRevision'] != owner.rev: return self.out({'ok':False},409)
                owner.state=data['state']; owner.rev += 1; self.out({'ok':True,'revision':owner.rev})
        self.http=ThreadingHTTPServer(('127.0.0.1',0),H)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
    def __enter__(self): self.thread.start(); return self
    def __exit__(self,*args): self.http.shutdown(); self.thread.join(timeout=2); self.http.server_close()
    @property
    def url(self): return f'http://127.0.0.1:{self.http.server_address[1]}'
    def command(self, payload):
        self.state['weeklySchedule']['webCommands']=[payload]
        self.rev += 1


def cfg(td: Path, db: Path, server: Server):
    env=td/'bridge.env'; env.write_text('DVIZH_WEB_USER_ID="old-user"\n',encoding='utf-8')
    identity=td/'identity.json'; identity.write_text(json.dumps({'user_id':'auth-user','email':'owner@local'}),encoding='utf-8')
    return mod.Config(str(db),server.url,str(env),str(identity),str(td/'status.json'),3,3)


def test_create_update_toggle_delete_and_idempotency():
    with tempfile.TemporaryDirectory() as raw:
        td=Path(raw); db=td/'tg.db'; mkdb(db)
        with Server() as server:
            config=cfg(td,db,server)
            today=datetime.now(timezone.utc).date().isoformat()
            create={'id':'c1','action':'create','title':'Зал верх','kind':'gym','recurrence':'once','dateLocal':today,'weekdaysMask':None,'startLocal':'18:30','durationMinutes':60,'reminderMinutes':30}
            server.command(create)
            result=mod.sync_once(config)
            assert result['applied']==1 and result['acknowledged']==1
            assert server.state['weeklySchedule']['webCommands']==[]
            with sqlite3.connect(db) as q:
                item=q.execute('select id,title,start_local,enabled from schedule_items').fetchone(); item_id=item[0]
                assert item[1:] == ('Зал верх','18:30',1)
                assert q.execute('select count(*) from schedule_occurrences').fetchone()[0] == 1

            # Replaying the same command id must never create a duplicate.
            server.command(create)
            result=mod.sync_once(config)
            assert result['duplicates']==1
            with sqlite3.connect(db) as q: assert q.execute('select count(*) from schedule_items').fetchone()[0] == 1

            server.command({'id':'c2','action':'update','itemId':f'tg-schedule-item-7-{item_id}','title':'Зал низ','kind':'gym','recurrence':'weekly','dateLocal':None,'weekdaysMask':127,'startLocal':'19:15','durationMinutes':75,'reminderMinutes':60})
            assert mod.sync_once(config)['applied']==1
            with sqlite3.connect(db) as q:
                row=q.execute('select title,recurrence,weekdays_mask,start_local,duration_minutes from schedule_items where id=?',(item_id,)).fetchone()
                assert row == ('Зал низ','weekly',127,'19:15',75)
                assert q.execute("select count(*) from schedule_occurrences where status='pending'").fetchone()[0] == 8

            server.command({'id':'c3','action':'set_enabled','itemId':f'tg-schedule-item-7-{item_id}','enabled':False})
            assert mod.sync_once(config)['applied']==1
            with sqlite3.connect(db) as q:
                assert q.execute('select enabled from schedule_items where id=?',(item_id,)).fetchone()[0] == 0
                assert q.execute("select count(*) from schedule_occurrences where status='pending'").fetchone()[0] == 0

            server.command({'id':'c4','action':'set_enabled','itemId':f'tg-schedule-item-7-{item_id}','enabled':True})
            assert mod.sync_once(config)['applied']==1
            with sqlite3.connect(db) as q: assert q.execute("select count(*) from schedule_occurrences where status='pending'").fetchone()[0] == 8

            server.command({'id':'c5','action':'delete','itemId':f'tg-schedule-item-7-{item_id}'})
            assert mod.sync_once(config)['applied']==1
            with sqlite3.connect(db) as q:
                assert q.execute('select count(*) from schedule_items').fetchone()[0] == 0
                assert q.execute('select count(*) from schedule_occurrences').fetchone()[0] == 0


def test_auth_identity_has_priority_over_old_bridge_env():
    with tempfile.TemporaryDirectory() as raw:
        td=Path(raw); db=td/'tg.db'; mkdb(db)
        with Server() as server:
            config=cfg(td,db,server)
            identity=mod.load_identity(config)
            assert identity.user_id == 'auth-user'

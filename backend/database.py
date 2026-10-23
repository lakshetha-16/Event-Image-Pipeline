import json, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
SCHEMA = """
CREATE TABLE IF NOT EXISTS images(id TEXT PRIMARY KEY, original_filename TEXT NOT NULL, bucket TEXT NOT NULL, object_key TEXT NOT NULL, mime_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, width INTEGER, height INTEGER, checksum_sha256 TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','completed','failed')), uploaded_at TEXT NOT NULL, processing_started_at TEXT, processed_at TEXT, processing_ms INTEGER, top_label TEXT, top_confidence REAL, predictions_json TEXT, metadata_key TEXT, metadata_size_bytes INTEGER NOT NULL DEFAULT 0, retry_count INTEGER NOT NULL DEFAULT 0, error_message TEXT);
CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL UNIQUE,event_type TEXT NOT NULL,image_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','completed','failed')),attempts INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 3,available_at TEXT NOT NULL,locked_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,last_error TEXT);
CREATE INDEX IF NOT EXISTS idx_events_queue ON events(status,available_at);
CREATE TABLE IF NOT EXISTS event_log(id INTEGER PRIMARY KEY AUTOINCREMENT,image_id TEXT,event_id TEXT,level TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT,updated_at TEXT NOT NULL);
"""
def now(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
class Database:
    def __init__(self,path): self.path=str(path); Path(self.path).parent.mkdir(parents=True,exist_ok=True)
    @contextmanager
    def connection(self):
        c=sqlite3.connect(self.path,timeout=30); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
        try: yield c; c.commit()
        finally: c.close()
    def init(self):
        with self.connection() as c: c.executescript(SCHEMA)
    def ping(self):
        with self.connection() as c: c.execute('SELECT 1').fetchone()
        return True
    def insert_image(self,r):
        with self.connection() as c: c.execute('INSERT INTO images(id,original_filename,bucket,object_key,mime_type,size_bytes,width,height,checksum_sha256,status,uploaded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',tuple(r[k] for k in ('id','original_filename','bucket','object_key','mime_type','size_bytes','width','height','checksum_sha256','status','uploaded_at')))
    def get_image(self,i):
        with self.connection() as c: r=c.execute('SELECT * FROM images WHERE id=?',(i,)).fetchone()
        if not r:return None
        d=dict(r); raw=d.pop('predictions_json'); d['predictions']=json.loads(raw) if raw else []; return d
    def update_image(self,i,**fields):
        allowed={'status','processing_started_at','processed_at','processing_ms','top_label','top_confidence','predictions_json','metadata_key','metadata_size_bytes','retry_count','error_message','width','height'}
        if set(fields)-allowed: raise ValueError('Invalid image field')
        if fields:
            with self.connection() as c: c.execute('UPDATE images SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),i))
    def list_images(self,status=None,search=None,limit=12,offset=0):
        where=[]; args=[]
        if status: where.append('status=?'); args.append(status)
        if search: where.append('(original_filename LIKE ? OR top_label LIKE ?)'); args += [f'%{search}%',f'%{search}%']
        clause=(' WHERE '+' AND '.join(where)) if where else ''
        with self.connection() as c:
            total=c.execute('SELECT COUNT(*) FROM images'+clause,args).fetchone()[0]
            rows=c.execute('SELECT * FROM images'+clause+' ORDER BY uploaded_at DESC LIMIT ? OFFSET ?',(*args,limit,offset)).fetchall()
        result=[]
        for r in rows:
            d=dict(r); raw=d.pop('predictions_json'); d['predictions']=json.loads(raw) if raw else []; result.append(d)
        return result,total
    def enqueue_event(self,event_id,image_id,event_type,max_attempts):
        t=now()
        with self.connection() as c:
            cur=c.execute("INSERT OR IGNORE INTO events(event_id,event_type,image_id,status,attempts,max_attempts,available_at,created_at,updated_at) VALUES(?,?,?,'pending',0,?,?,?,?)",(event_id,event_type,image_id,max_attempts,t,t,t)); return cur.rowcount==1
    def claim_next_event(self,timeout=300):
        from datetime import timedelta
        t=now(); stale=(datetime.now(timezone.utc)-timedelta(seconds=timeout)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        with self.connection() as c:
            c.execute('BEGIN IMMEDIATE'); c.execute("UPDATE events SET status='pending',locked_at=NULL WHERE status='processing' AND locked_at < ?",(stale,))
            r=c.execute("SELECT * FROM events WHERE status='pending' AND available_at<=? ORDER BY id LIMIT 1",(t,)).fetchone()
            if r is None: return None
            c.execute("UPDATE events SET status='processing',locked_at=?,attempts=attempts+1,updated_at=? WHERE id=?",(t,t,r['id']))
            d=dict(r); d['attempts']+=1; d['status']='processing'; return d
    def complete_event(self,e):
        with self.connection() as c: c.execute("UPDATE events SET status='completed',locked_at=NULL,updated_at=? WHERE event_id=?",(now(),e))
    def retry_event(self,e,delay,error):
        from datetime import timedelta
        due=(datetime.now(timezone.utc)+timedelta(seconds=delay)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        with self.connection() as c: c.execute("UPDATE events SET status='pending',locked_at=NULL,last_error=?,available_at=?,updated_at=? WHERE event_id=?",(error,due,now(),e))
    def fail_event(self,e,error):
        with self.connection() as c: c.execute("UPDATE events SET status='failed',locked_at=NULL,last_error=?,updated_at=? WHERE event_id=?",(error,now(),e))
    def add_log(self,level,message,image_id=None,event_id=None):
        with self.connection() as c: c.execute('INSERT INTO event_log(image_id,event_id,level,message,created_at) VALUES(?,?,?,?,?)',(image_id,event_id,level,message,now()))
    def list_events(self,limit=50):
        with self.connection() as c: return [dict(r) for r in c.execute('SELECT e.*,i.original_filename FROM events e LEFT JOIN images i ON i.id=e.image_id ORDER BY e.id DESC LIMIT ?',(limit,))]
    def list_logs(self,limit=50):
        with self.connection() as c: return [dict(r) for r in c.execute('SELECT * FROM event_log ORDER BY id DESC LIMIT ?',(limit,))]
    def event_counts(self):
        out={k:0 for k in ('pending','processing','completed','failed')}
        with self.connection() as c:
            for r in c.execute('SELECT status,COUNT(*) n FROM events GROUP BY status'): out[r['status']]=r['n']
        return out
    def set_kv(self,k,v):
        with self.connection() as c: c.execute('INSERT INTO kv(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',(k,v,now()))
    def get_kv(self,k):
        with self.connection() as c: r=c.execute('SELECT * FROM kv WHERE key=?',(k,)).fetchone()
        return dict(r) if r else None
    def stats(self):
        with self.connection() as c:
            status={k:0 for k in ('pending','processing','completed','failed')}
            for r in c.execute('SELECT status,COUNT(*) n FROM images GROUP BY status'): status[r['status']]=r['n']
            cats=[dict(r) for r in c.execute("SELECT top_label label,COUNT(*) count FROM images WHERE status='completed' AND top_label IS NOT NULL GROUP BY top_label ORDER BY count DESC LIMIT 8")]
            totals=c.execute('SELECT COUNT(*) n,COALESCE(SUM(size_bytes),0) bytes,AVG(processing_ms) avg FROM images').fetchone()
        return {'totals':{'images':totals['n'],'completed':status['completed'],'awaiting':status['pending']+status['processing'],'pending':status['pending'],'processing':status['processing'],'failed':status['failed'],'storage_bytes':totals['bytes']},'success_rate':round(status['completed']/(status['completed']+status['failed'])*100,1) if status['completed']+status['failed'] else None,'avg_processing_ms':round(totals['avg'],1) if totals['avg'] is not None else None,'categories':cats}

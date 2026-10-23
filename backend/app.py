import hashlib,io,json,logging,re,sqlite3,uuid
from datetime import datetime,timezone
from flask import Flask,jsonify,request,send_file
from werkzeug.exceptions import HTTPException
from classifier import MODEL_NAME
from config import Config
from database import Database,now
from event_producer import EventProducer
from storage import ObjectNotFound,ObjectStorage,StorageError
from validation import UploadError,read_limited,safe_filename,validate_image
log=logging.getLogger(__name__); ID_RE=re.compile(r'^[0-9a-f]{32}$')
def ok(data=None,status=200):return jsonify({'success':True,'data':data}),status
def fail(code,message,status,details=None):
    e={'code':code,'message':message}
    if details is not None:e['details']=details
    return jsonify({'success':False,'error':e}),status
def create_app(config=None,db=None,storage=None,producer=None):
    cfg=config or Config.from_env(); app=Flask(__name__); app.config['MAX_CONTENT_LENGTH']=cfg.max_upload_bytes+1024*1024; db=db or Database(cfg.database_path); db.init()
    if storage is None:
        storage=ObjectStorage(cfg.storage_path)
        storage.ensure_bucket()
    producer=producer or EventProducer(db,cfg.max_attempts); app.extensions['pipeline']={'config':cfg,'db':db,'storage':storage,'producer':producer}
    @app.after_request
    def headers(resp):
        origin=request.headers.get('Origin')
        if origin in cfg.allowed_origins:resp.headers['Access-Control-Allow-Origin']=origin;resp.headers['Access-Control-Allow-Headers']='Content-Type';resp.headers['Access-Control-Allow-Methods']='GET,POST,OPTIONS';resp.headers.add('Vary','Origin')
        resp.headers['X-Content-Type-Options']='nosniff';return resp
    @app.errorhandler(HTTPException)
    def http_error(e):return fail('HTTP_ERROR',e.description,e.code or 500)
    @app.errorhandler(sqlite3.Error)
    def db_error(e):log.exception('Database error');return fail('DATABASE_ERROR','A database error occurred.',500)
    @app.errorhandler(StorageError)
    def storage_error(e):return fail('STORAGE_UNAVAILABLE',str(e),503)
    @app.errorhandler(Exception)
    def unexpected(e):log.exception('Unhandled error');return fail('INTERNAL_ERROR','Unexpected server error.',500)
    def get_image(i):return db.get_image(i) if ID_RE.fullmatch(i or '') else None
    def ingest(f):
        data=read_limited(f.stream,cfg.max_upload_bytes); info=validate_image(f.filename,data); i=uuid.uuid4().hex; key=f'originals/{i}/{info["filename"]}'
        storage.put_bytes(key,data,info['mime_type']); rec={'id':i,'original_filename':info['filename'],'bucket':'local-files','object_key':key,'mime_type':info['mime_type'],'size_bytes':info['size_bytes'],'width':info['width'],'height':info['height'],'checksum_sha256':hashlib.sha256(data).hexdigest(),'status':'pending','uploaded_at':now()}
        try:db.insert_image(rec);producer.publish_upload_event(i)
        except Exception:
            storage.delete(key);raise
        return db.get_image(i)
    @app.post('/api/images/upload')
    def upload():
        incoming=request.files.getlist('files') or request.files.getlist('file')
        if not incoming:return fail('NO_FILE','Attach one or more images in the files field.',400)
        uploaded=[]; rejected=[]
        for f in incoming:
            try:uploaded.append(ingest(f))
            except UploadError as e:rejected.append({'filename':safe_filename(f.filename),'code':e.code,'message':e.message,'status':e.status})
        if not uploaded:
            e=rejected[0];return fail(e['code'],e['message'],e['status'],{'rejected':rejected})
        return ok({'uploaded':uploaded,'rejected':rejected},201)
    @app.get('/api/images')
    def images():
        status=request.args.get('status') or None
        if status and status not in ('pending','processing','completed','failed'):return fail('INVALID_PARAMETER','Unknown status filter.',400)
        try:page=max(1,int(request.args.get('page',1))); size=min(100,max(1,int(request.args.get('page_size',12))))
        except ValueError:return fail('INVALID_PARAMETER','page and page_size must be numbers.',400)
        items,total=db.list_images(status,(request.args.get('search') or '').strip()[:100] or None,size,(page-1)*size);return ok({'items':items,'total':total,'page':page,'page_size':size})
    @app.get('/api/images/<image_id>')
    def image_detail(image_id):
        item=get_image(image_id);return ok(item) if item else fail('NOT_FOUND','Image not found.',404)
    @app.get('/api/images/<image_id>/metadata')
    def metadata(image_id):
        item=get_image(image_id)
        if not item:return fail('NOT_FOUND','Image not found.',404)
        if item['status']!='completed' or not item['metadata_key']:return fail('NOT_READY','Metadata is available after processing.',409)
        raw=storage.get_bytes(item['metadata_key'])
        if request.args.get('download')=='1':return send_file(io.BytesIO(raw),mimetype='application/json',as_attachment=True,download_name=f'{image_id}-metadata.json')
        return ok(json.loads(raw))
    @app.get('/api/images/<image_id>/download')
    def download(image_id):
        item=get_image(image_id)
        if not item:return fail('NOT_FOUND','Image not found.',404)
        raw=storage.get_bytes(item['object_key']); inline=request.args.get('inline')=='1';return send_file(io.BytesIO(raw),mimetype=item['mime_type'],as_attachment=not inline,download_name=item['original_filename'])
    @app.get('/api/events')
    def events():return ok({'events':db.list_events(),'log':db.list_logs(),'counts':db.event_counts()})
    @app.get('/api/analytics')
    def analytics():return ok(db.stats())
    @app.get('/api/settings')
    def settings():return ok({'model':MODEL_NAME,'bucket':'local-files','max_upload_mb':cfg.max_upload_mb,'allowed_extensions':['jpg','jpeg','png','webp'],'max_attempts':cfg.max_attempts,'retry_backoff_seconds':cfg.retry_backoff_seconds,'queue':'SQLite-backed event queue'})
    @app.get('/api/health')
    def health():
        try:db_ok=db.ping()
        except sqlite3.Error:db_ok=False
        storage_ok=storage.ping(); beat=db.get_kv('worker_heartbeat') if db_ok else None; age=None; worker_ok=False
        if beat:
            seen=datetime.strptime(beat['value'],'%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc);age=round((datetime.now(timezone.utc)-seen).total_seconds(),1);worker_ok=age<=30
        return ok({'status':'ok' if db_ok and storage_ok and worker_ok else 'degraded','services':{'api':True,'database':db_ok,'local_file_storage':storage_ok,'worker':worker_ok},'worker_last_seen_seconds':age})
    return app
if __name__=='__main__':
    logging.basicConfig(level=logging.INFO);cfg=Config.from_env();create_app(cfg).run(host=cfg.flask_host,port=cfg.flask_port,debug=cfg.flask_debug,threaded=True)

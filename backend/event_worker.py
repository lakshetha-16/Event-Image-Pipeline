import hashlib,json,logging,sqlite3,time
from classifier import ImageClassifier,InvalidImageError
from config import Config
from database import Database,now
from metadata_generator import build_metadata,metadata_key,to_json_bytes
from storage import ObjectNotFound,ObjectStorage
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s'); log=logging.getLogger('worker')
class PermanentError(Exception): pass
class Worker:
    def __init__(self,db,storage,classifier,cfg): self.db,self.storage,self.classifier,self.cfg=db,storage,classifier,cfg; self.stopping=False
    def run_forever(self):
        log.info('Worker ready. Press Ctrl+C to stop.')
        while not self.stopping:
            try: self.db.set_kv('worker_heartbeat',now()); event=self.db.claim_next_event(self.cfg.visibility_timeout_seconds)
            except sqlite3.Error as e: log.error('Database polling failed: %s',e); time.sleep(self.cfg.poll_interval_seconds*2); continue
            if event is None: time.sleep(self.cfg.poll_interval_seconds); continue
            self.process_event(event)
    def run_once(self):
        event=self.db.claim_next_event(self.cfg.visibility_timeout_seconds)
        if event is None:return False
        self.process_event(event); return True
    def process_event(self,event):
        try: self._handle(event)
        except PermanentError as e: self._fail(event,str(e))
        except Exception as e:
            message=str(e) or type(e).__name__
            if event['attempts']<event['max_attempts']:
                delay=self.cfg.retry_backoff_seconds*(2**(event['attempts']-1)); self.db.retry_event(event['event_id'],delay,message); self.db.update_image(event['image_id'],status='pending',retry_count=event['attempts'],error_message=message); self.db.add_log('WARNING',f'Attempt {event["attempts"]} failed; retrying in {delay}s',event['image_id'],event['event_id'])
            else:self._fail(event,f'Gave up after {event["attempts"]} attempts: {message}')
    def _fail(self,event,message):
        self.db.fail_event(event['event_id'],message)
        if self.db.get_image(event['image_id']):self.db.update_image(event['image_id'],status='failed',error_message=message,retry_count=event['attempts'])
        self.db.add_log('ERROR',message,event['image_id'],event['event_id'])
    def _handle(self,event):
        image=self.db.get_image(event['image_id'])
        if not image:raise PermanentError('Image record not found.')
        if image['status']=='completed':self.db.complete_event(event['event_id']);return
        self.db.update_image(image['id'],status='processing',processing_started_at=now(),error_message=None)
        if self.cfg.worker_artificial_delay_seconds:time.sleep(self.cfg.worker_artificial_delay_seconds)
        try:data=self.storage.get_bytes(image['object_key'])
        except ObjectNotFound as e:raise PermanentError(str(e)) from e
        if hashlib.sha256(data).hexdigest()!=image['checksum_sha256']:raise PermanentError('Stored image checksum mismatch.')
        try:result=self.classifier.predict(data)
        except InvalidImageError as e:raise PermanentError(str(e)) from e
        completed=now(); payload=to_json_bytes(build_metadata(image,result['predictions'],completed,self.classifier.model_name,result['processing_ms'])); key=metadata_key(image['id']); self.storage.put_bytes(key,payload,'application/json'); top=result['predictions'][0]
        self.db.update_image(image['id'],status='completed',processed_at=completed,processing_ms=result['processing_ms'],top_label=top['label'],top_confidence=top['confidence'],predictions_json=json.dumps(result['predictions']),metadata_key=key,metadata_size_bytes=len(payload),retry_count=max(0,event['attempts']-1),error_message=None)
        self.db.complete_event(event['event_id']); self.db.add_log('INFO',f'Completed: {top["label"]} ({top["confidence"]}%)',image['id'],event['event_id'])
def main():
    cfg=Config.from_env(); db=Database(cfg.database_path); db.init(); storage=ObjectStorage(cfg.storage_path); storage.ensure_bucket(); model=ImageClassifier(); log.info('Loading MobileNetV2; first run downloads model weights.'); model.load(); Worker(db,storage,model,cfg).run_forever()
if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: log.info('Worker stopped.')

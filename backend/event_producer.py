from database import Database
UPLOAD_EVENT='image.uploaded'
class EventProducer:
    def __init__(self,db:Database,max_attempts=3): self.db=db; self.max_attempts=max_attempts
    def publish_upload_event(self,image_id):
        event_id=f'{UPLOAD_EVENT}:{image_id}'
        if not self.db.enqueue_event(event_id,image_id,UPLOAD_EVENT,self.max_attempts): return None
        self.db.add_log('INFO','Upload event created and queued',image_id,event_id); return event_id

import json
SCHEMA_VERSION='1.0'
def metadata_key(image_id): return f'metadata/{image_id}.json'
def build_metadata(image,predictions,completed_at,model_name,processing_ms):
    return {'schema_version':SCHEMA_VERSION,'image_id':image['id'],'original_filename':image['original_filename'],'file_size_bytes':image['size_bytes'],'mime_type':image['mime_type'],'width':image['width'],'height':image['height'],'uploaded_at':image['uploaded_at'],'processed_at':completed_at,'processing_time_ms':processing_ms,'model':model_name,'predictions':[{'rank':p['rank'],'label':p['label'],'class_id':p.get('class_id'),'confidence_percent':p['confidence']} for p in predictions],'checksum_sha256':image['checksum_sha256'],'storage':{'type':'local_filesystem','object_key':image['object_key']},'processing_status':'completed'}
def to_json_bytes(metadata): return json.dumps(metadata,indent=2,ensure_ascii=False).encode('utf-8')

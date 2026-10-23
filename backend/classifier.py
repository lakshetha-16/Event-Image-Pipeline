import io, os, time
import numpy as np
from PIL import Image, UnidentifiedImageError
MODEL_NAME='MobileNetV2 (ImageNet, 1000 classes)'
class InvalidImageError(Exception): pass
def prepare_image(data):
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load(); w,h=im.size; rgb=im.convert('RGB').resize((224,224),Image.Resampling.BILINEAR)
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError) as e: raise InvalidImageError('Image could not be decoded.') from e
    return np.asarray(rgb,dtype='float32'),w,h
class ImageClassifier:
    model_name=MODEL_NAME
    def __init__(self): self.model=None; self.preprocess=None; self.decode=None
    @property
    def loaded(self): return self.model is not None
    def load(self):
        os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
        import tensorflow as tf
        apps=tf.keras.applications; self.model=apps.MobileNetV2(weights='imagenet'); self.preprocess=apps.mobilenet_v2.preprocess_input; self.decode=apps.mobilenet_v2.decode_predictions
    def predict(self,data,top_k=3):
        if not self.loaded: raise RuntimeError('Model is not loaded. Start the worker after installing TensorFlow.')
        start=time.perf_counter(); arr,w,h=prepare_image(data); pred=self.model.predict(self.preprocess(np.expand_dims(arr,0)),verbose=0); decoded=self.decode(pred,top=top_k)[0]
        return {'predictions':[{'rank':i+1,'class_id':cid,'label':label.replace('_',' '),'confidence':round(float(p)*100,2)} for i,(cid,label,p) in enumerate(decoded)],'processing_ms':int((time.perf_counter()-start)*1000),'width':w,'height':h}

import io, os
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
Image.MAX_IMAGE_PIXELS=50_000_000
FORMATS={'jpg':('JPEG','image/jpeg'),'jpeg':('JPEG','image/jpeg'),'png':('PNG','image/png'),'webp':('WEBP','image/webp')}
class UploadError(Exception):
    def __init__(self,code,message,status=400): self.code,self.message,self.status=code,message,status; super().__init__(message)
def safe_filename(name): return (secure_filename(os.path.basename(name or '')) or 'image')[:100]
def read_limited(stream,limit):
    data=stream.read(limit+1)
    if len(data)>limit: raise UploadError('FILE_TOO_LARGE',f'File exceeds the {limit//(1024*1024)} MB limit.',413)
    return data
def validate_image(filename,data):
    name=safe_filename(filename); ext=name.rsplit('.',1)[-1].lower() if '.' in name else ''
    if ext not in FORMATS: raise UploadError('UNSUPPORTED_TYPE','Only JPG, JPEG, PNG and WEBP images are accepted.',415)
    if not data: raise UploadError('EMPTY_FILE','The file is empty.')
    try:
        with Image.open(io.BytesIO(data)) as im: fmt=im.format; width,height=im.size; im.verify()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError): raise UploadError('CORRUPT_IMAGE','The image is corrupt or too large to process.')
    expected,mime=FORMATS[ext]
    if fmt!=expected: raise UploadError('TYPE_MISMATCH','The file content does not match its extension.',415)
    return {'filename':name,'mime_type':mime,'width':width,'height':height,'size_bytes':len(data)}

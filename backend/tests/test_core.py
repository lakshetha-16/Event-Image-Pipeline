import io, tempfile, unittest
from pathlib import Path
from PIL import Image
from database import Database
from validation import validate_image, UploadError
class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'test.db'));self.db.init()
    def tearDown(self):self.tmp.cleanup()
    def test_database_ping_and_queue(self):
        self.assertTrue(self.db.ping());self.assertTrue(self.db.enqueue_event('e1','img1','image.uploaded',3));self.assertFalse(self.db.enqueue_event('e1','img1','image.uploaded',3));event=self.db.claim_next_event();self.assertEqual(event['event_id'],'e1');self.assertEqual(event['attempts'],1)
    def test_valid_png(self):
        b=io.BytesIO();Image.new('RGB',(12,8),'blue').save(b,format='PNG');result=validate_image('sample.png',b.getvalue());self.assertEqual(result['width'],12);self.assertEqual(result['mime_type'],'image/png')
    def test_rejects_mismatched_content(self):
        b=io.BytesIO();Image.new('RGB',(4,4)).save(b,format='PNG')
        with self.assertRaises(UploadError):validate_image('sample.jpg',b.getvalue())
    def test_rejects_unknown_extension(self):
        with self.assertRaises(UploadError):validate_image('notes.txt',b'abc')
if __name__=='__main__':unittest.main()

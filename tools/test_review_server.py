"""浏览器拖动依赖的字节区间合同回归。"""
import functools,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from review_server import RangeHandler

class RangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();Path(cls.temp.name,'video.mp4').write_bytes(bytes(range(200)))
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(RangeHandler,directory=cls.temp.name))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}/video.mp4'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
    def fetch(self,value=None,method='GET'):
        req=urllib.request.Request(self.url,headers={'Range':value} if value else {},method=method)
        try:return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:return e
    def test_full(self):
        with self.fetch() as r:self.assertEqual(r.status,200);self.assertEqual(len(r.read()),200);self.assertEqual(r.headers['Accept-Ranges'],'bytes')
    def test_partial(self):
        with self.fetch('bytes=10-19') as r:self.assertEqual(r.status,206);self.assertEqual(r.headers['Content-Range'],'bytes 10-19/200');self.assertEqual(r.read(),bytes(range(10,20)))
    def test_suffix_and_open_end(self):
        for value in ['bytes=-10','bytes=190-','bytes=190-999']:
            with self.fetch(value) as r:self.assertEqual(r.status,206);self.assertEqual(r.read(),bytes(range(190,200)))
    def test_head(self):
        with self.fetch('bytes=10-19','HEAD') as r:self.assertEqual(r.status,206);self.assertEqual(r.headers['Content-Length'],'10');self.assertEqual(r.read(),b'')
    def test_unsatisfied(self):
        for value in ['bytes=201-','bytes=50-10','bytes=-0']:
            with self.fetch(value) as r:self.assertEqual(r.status,416);self.assertEqual(r.headers['Content-Range'],'bytes */200')
    def test_bad_request(self):
        with self.fetch('bytes=0-1,5-6') as r:self.assertEqual(r.status,400)

if __name__=='__main__':unittest.main()

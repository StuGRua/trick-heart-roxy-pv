"""本地媒体审阅服务器：支持单区间Range、HEAD与并发读取。"""
import argparse,functools,os,re
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        self.byte_range=None
        path=Path(self.translate_path(self.path))
        header=self.headers.get('Range')
        if not header or not path.is_file():return super().send_head()
        match=re.fullmatch(r'bytes=(\d*)-(\d*)',header.strip())
        if not match or not any(match.groups()):
            self.send_error(HTTPStatus.BAD_REQUEST,'Expected one byte range');return None
        try:f=path.open('rb')
        except OSError:self.send_error(HTTPStatus.NOT_FOUND);return None
        size=os.fstat(f.fileno()).st_size;left,right=match.groups()
        if left:
            start=int(left);end=min(int(right),size-1) if right else size-1
        else:
            length=int(right);start=max(0,size-length);end=size-1
            if length==0:start=size
        if start>=size or end<start:
            f.close();self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return None
        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header('Content-Type',self.guess_type(str(path)))
        self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length',str(end-start+1))
        self.send_header('Last-Modified',self.date_time_string(os.fstat(f.fileno()).st_mtime))
        self.end_headers();f.seek(start);self.byte_range=(start,end)
        return f

    def end_headers(self):
        self.send_header('Accept-Ranges','bytes')
        super().end_headers()

    def copyfile(self,source,outputfile):
        try:
            if self.byte_range is None:return super().copyfile(source,outputfile)
            remaining=self.byte_range[1]-self.byte_range[0]+1
            while remaining:
                data=source.read(min(1024*1024,remaining))
                if not data:break
                outputfile.write(data);remaining-=len(data)
        except (BrokenPipeError,ConnectionResetError):pass

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8847)
    ap.add_argument('--directory',type=Path,default=Path(__file__).resolve().parents[1]);args=ap.parse_args()
    handler=functools.partial(RangeHandler,directory=str(args.directory.resolve()))
    with ThreadingHTTPServer(('127.0.0.1',args.port),handler) as server:
        print(f'Review: http://127.0.0.1:{server.server_port}/review.html',flush=True)
        server.serve_forever()

if __name__=='__main__':main()

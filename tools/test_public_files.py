"""发布白名单不能越界、夹带媒体或重复计数。"""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import check_public

class PublicFileTests(unittest.TestCase):
    def check(self,names,make):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);make(root);(root/'public-files.json').write_text(json.dumps({'files':names}))
            with patch.object(check_public,'ROOT',root):return check_public.public_files()

    def test_only_declared_file(self):
        result=self.check(['README.md'],lambda p:((p/'README.md').write_text('ok'),(p/'local-note.txt').write_text('private')))
        self.assertEqual([x[0] for x in result],['README.md'])

    def test_reject_duplicate(self):
        with self.assertRaises(ValueError):self.check(['a.md','a.md'],lambda p:(p/'a.md').write_text('ok'))

    def test_reject_output_media(self):
        with self.assertRaises(ValueError):self.check(['video.mp4'],lambda p:(p/'video.mp4').write_bytes(b'not a public source'))

    def test_reject_escape(self):
        with self.assertRaises(ValueError):self.check(['../README.md'],lambda p:None)

if __name__=='__main__':unittest.main()

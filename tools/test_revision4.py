"""容易复发的图层契约；合成验收另需真实连续帧。"""
import unittest
from unittest.mock import patch
import numpy as np
import cv2
import revision4_composite as v4
import revision4_juggle as juggle
import chinese_subtitles as zh

class LayerContractTests(unittest.TestCase):
    def test_internal_skin_shadow_is_not_background(self):
        mask=np.zeros((40,60),np.uint8);mask[:,:10]=1;mask[14:24,25:35]=1
        bg=v4.boundary_connected(mask)
        self.assertTrue(bg[0,0]);self.assertFalse(bg[18,29])

    def test_butterfly_contact_does_not_resize_portrait(self):
        src=np.full((1080,1920,3),(137,54,51),np.uint8)
        cv2.rectangle(src,(550,300),(1350,780),(24,22,20),5)
        cv2.rectangle(src,(554,304),(1346,776),(240,233,212),-1)
        _,before,_=v4.panel_geometry(src,(480,200,1450,850))
        decorated=src.copy();cv2.ellipse(decorated,(900,292),(70,27),0,0,360,(255,211,151),-1)
        _,after,fg=v4.panel_geometry(decorated,(480,200,1450,850))
        self.assertEqual(before,after);self.assertGreater(np.count_nonzero(fg),0)

    def test_unaffected_frame_uses_v3(self):
        sentinel=np.full((3,4,3),17,np.uint8)
        with patch.object(v4,'old_frame',return_value=sentinel) as old:
            im,record=v4.render(1800)
        self.assertIs(im,sentinel);old.assert_called_once_with(1800)
        self.assertFalse(record['affected'])

    def test_magic_entry_without_hand_does_not_receive_fingers(self):
        sentinel=np.zeros((1080,1920,3),np.uint8)
        with patch.object(v4,'old_frame',return_value=sentinel), \
             patch.object(v4.c,'reference',return_value=sentinel), \
             patch.object(v4.v3,'glove',return_value=np.zeros((1080,1920),np.uint8)), \
             patch.object(v4.v3,'sprite') as sprite:
            im,record=v4.opening_hand(6)
        self.assertIs(im,sentinel);sprite.assert_not_called()
        self.assertIsNone(record['hand_reference'])

    def test_version_configuration_does_not_change_cues(self):
        cues=zh.CUES;zh.configure('v4')
        try:
            self.assertEqual(zh.BASE.name,'full-composite-v4')
            self.assertEqual(zh.DEST.name,'full-composite-v4-zh')
            self.assertIs(zh.CUES,cues)
        finally:zh.configure('v3')

    def test_closed_curtain_preserves_open_black_seam(self):
        src=np.full((1080,1920,3),(80,15,16),np.uint8)
        src[:350,951:980]=0
        with patch.object(juggle,'choose',return_value=(2600,0)), \
             patch.object(juggle,'sprite') as sprite:
            out,record=juggle.render(src,2778)
        self.assertTrue(np.array_equal(out,src));sprite.assert_not_called()
        self.assertEqual(record['curtain_state'],'closed')

if __name__=='__main__':unittest.main()

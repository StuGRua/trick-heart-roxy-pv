"""v4共享的连通域图层规则。"""
import cv2
import numpy as np

def boundary_connected(mask):
    """只选与画布外缘相连的区域，保留内部同色的肤色/阴影。"""
    _,labels,_,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),8)
    ids=np.unique(np.concatenate((labels[0],labels[-1],labels[:,0],labels[:,-1])))
    return np.isin(labels,ids[ids!=0])

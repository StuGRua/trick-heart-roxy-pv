# Trick Heart — Roxy Visual Fan Edit

《トリックハート》洛琪希视觉二创。AI绘制人物与动作差分，Python/OpenCV负责跟踪、遮罩和合成，FFmpeg输出成片。提供中文字幕版和原PV同步对比。

视觉二创：**StuG_III + GPT6Astra**。

[v2下载](https://github.com/StuGRua/trick-heart-roxy-pv/releases/latest) · [改进与踩坑记录](docs/v2-release.md)

## v2改进

- 修复持牌穿模、画框漏红发、白手套残留、道具重影和帘幕残影。
- 补齐站立动作、13张杂耍姿态、表情变化及醒来转头。
- 重画常服特写，修正鸭子重复与人物出框。

## 复现

已验证环境：Windows + WSL、Python 3.12、FFmpeg 6.0。帧缓存建议预留15GB。

1. 下载Release中的`trick-heart-roxy-pv-resources-v2.zip`，将包内目录的内容合并到仓库根目录。
2. 将有权使用的原视频`source-1080-video.m4s`和音轨`source-audio.m4s`放入`research/`，按`source-baseline.json`核对输入。附件不含原视频与音轨。
3. 安装依赖并构建：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/build.py --check
.venv/bin/python tools/build.py --version v4
.venv/bin/python tools/review_server.py --port 8847
```

打开 http://127.0.0.1:8847/review.html 。输出位于`deliverables/`，可切换正片、中文字幕和同步对比，支持逐帧、慢放与片段循环。

FFmpeg/FFprobe可用`ROXY_FFMPEG`、`ROXY_FFPROBE`指定；对比字体和署名字体可用`ROXY_FONT`、`ROXY_CREDIT_FONT`指定。采用的署名字体为Times New Roman，需自行提供。

复现请使用资源包中的原画；重新生成图片或更换字体、依赖、编码器会改变结果。构建参数与历史版本说明见[制作流程](docs/pipeline.md)。

## 制作资料

- [制作流程](docs/pipeline.md)与[合成规则](docs/v4-revision.md)
- [原画提示词与来源](assets/revision4-manifest.json)
- [验证说明](docs/validation.md)

## 来源与许可

原曲／原PV：[MIMI《トリックハート》feat. 重音テトSV](https://www.bilibili.com/video/BV1ohuu6LEBP)。角色：洛琪希／《无职转生》。

感谢[无糖淀粉的千早爱音版](https://www.bilibili.com/video/BV1giez6QEzc)分享制作方法。

代码采用[MIT](LICENSE)，字体保留OFL许可；音乐、PV、角色和制作素材的范围见[素材说明](ASSET-NOTICE.md)。

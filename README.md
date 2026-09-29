# Trick Heart — Roxy Visual Fan Edit

《トリックハート》洛琪希视觉二创的Python制作工程。保留原PV构图、日文歌词、道具、镜头顺序与原音轨，以常服和魔法师两套洛琪希造型替换人物。另提供使用站酷快乐体的独立中文字幕版。

本版视觉二创：**StuG_III + GPT6Astra**。画面只保留中途和片尾两处英文视觉署名，不新增字幕署名。

感谢[无糖淀粉的千早爱音版](https://www.bilibili.com/video/BV1giez6QEzc)分享制作思路和方法。本项目参考其“人物差分原画＋程序跟随原PV合成”的工作流，制作常服与魔法师两套洛琪希造型。

代码采用MIT许可；复现素材作为独立附件提供，许可范围见[素材说明](ASSET-NOTICE.md)。下载入口：[Releases](https://github.com/StuGRua/trick-heart-roxy-pv/releases/latest)。

## 工程内容

- 图像模型制作可复用人物原画与姿态/表情差分；Python/OpenCV负责整体跟踪、遮罩、前景恢复和按帧合成。
- 78个连续合成区间；原画、手势切换、裸手重绘和字幕事件都有明确帧号。
- 正片1920×1080、24fps、3768帧、157秒；复制原AAC音轨并保留157.013333秒尾包。
- 原v3、中文字幕v3-zh与原片同步对比可在同一审阅页切换，支持拖动、逐帧、慢放和片段循环。
- 字幕外像素保护、帧覆盖、原AAC/PCM一致性、乱序确定性和媒体完整解码验证。

## 文件边界

| 目录 | 用途 | 进入代码仓库 |
| --- | --- | --- |
| tools/ | 构建、渲染、验证和审阅服务 | 是 |
| assets/ 中的JSON | 已脱敏的原画清单、提示词和裁切配置 | 是 |
| assets/fonts/ | 未修改的站酷快乐体及OFL许可 | 是 |
| assets/ 中的PNG | 本项目采用的制作原画 | 否，单独资源包 |
| subtitles/ | 字幕事件、样式和输入哈希 | 配置进入；译文与派生字幕在资源包 |
| research/ | 原始媒体输入及基线 | 只包含哈希基线 |
| frames/、review/、deliverables/、.venv/ | 缓存、检查证据、输出和环境 | 否 |
| tests/ | 当前交付的验证基线 | 是 |

public-files.json列出全部可公开文件。发布工具严格使用白名单，不直接打包工作目录。原作媒体不会随代码或资源包分发。

## 运行

已验证的环境为Windows + WSL、Python 3.12、Windows FFmpeg 6.0。其他环境需自行验证，尤其是字体和编码器版本。依赖固定于requirements.txt。

1. 在仓库根目录创建环境并安装依赖：

       python3 -m venv .venv
       .venv/bin/python -m pip install -r requirements.txt

2. 准备支持AV1解码、libx264和drawtext的FFmpeg/FFprobe。可通过ROXY_FFMPEG、ROXY_FFPROBE指定路径；否则寻找常见工具目录或PATH。用ROXY_FONT指定对比标记字体，用ROXY_CREDIT_FONT指定英文视觉署名字体；已交付v3使用Times New Roman，字体文件不随仓库分发。

3. 从[Releases](https://github.com/StuGRua/trick-heart-roxy-pv/releases/latest)下载trick-heart-roxy-pv-resources.zip，将包内trick-heart-roxy-pv/目录的内容合并到仓库根目录，避免形成同名嵌套目录。将有权使用的原视频source-1080-video.m4s及音轨source-audio.m4s放入research/，按source-baseline.json核对哈希；原视频和音轨不随资源包分发。

4. 执行：

       .venv/bin/python tools/build.py --check
       .venv/bin/python tools/build.py
       .venv/bin/python -m unittest discover -s tools -p 'test_*.py' -v
       .venv/bin/python tools/review_server.py --port 8847

默认构建v3、同步对比和v3-zh。需要仅构建v3时使用--without-subtitles。打开 http://127.0.0.1:8847/review.html 。

完整缓存建议预留15GB；缓存可以重新生成。图像模型重跑不保证相同原画，复现当前版本必须使用本次采用的素材。更换字体、库或编码器版本可能改变文件哈希。

## 检查与发布准备

    python3 tools/check_public.py
    python3 tools/package_release.py

生成的代码包与资源包分别位于deliverables/。资源包包含人物原画、用户提供译文等非MIT内容，不代表已取得原作或角色的公开再许可。这两条命令只在本地检查与打包，不自动上传或执行Git写操作。

详细制作结构见[制作流程](docs/pipeline.md)，复现与验证边界见[验证说明](docs/validation.md)。代码使用[MIT](LICENSE)，原曲、原PV、角色、译文、人物图与字体的范围见[素材说明](ASSET-NOTICE.md)。

## 为什么目前是repo而不是skill

本项目的主要交付是确定的素材、时间轴、合成规则、播放器和可运行代码，repo便于版本管理与复现。skill适合指导下一次如何准备原画、检查遮挡和调用这些脚本；它不能取代这里的代码或素材。等第二个不同PV验证了可复用接口，再提供指向repo的轻量skill，避免把本片专用规则包装成通用能力。

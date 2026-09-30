# PV规划模板

复制本目录到新项目的规划目录，先填project.json，再填四份CSV。CSV是工作表，当前渲染脚本不直接读取它们；实施时需要映射到该项目的镜头配置。

## 字段约定

- 帧号从0开始，所有区间为左闭右开；`end_frame_exclusive`可以等于总帧数。帧率保留分子/分母，时间仅供显示。
- `shot_id`、`pose_id`、`layer_id`和`review_id`各自唯一；同一镜头的记录用`shot_id`关联。
- `status`使用`planned`、`missing_asset`、`rendered`、`reviewed`。`reviewed`须有对应证据；模板初始为空，不代表已完成。
- 多值单元格使用分号；路径使用项目相对路径；空值表示待查，不能被当成不存在或已通过。
- `source_kind`区分`source_video`、`generated_cel`、`reconstructed_background`、`subtitle`。同一物体同一时段只指定一个主来源。
- `contact_mode`可写`none`、`joint_cel`、`separate_prop`；独立道具需在图层表写清前后关系。
- `z_order`从后到前递增；关系随时间变化时拆成不同事件区间。
- `kind`使用`still`、`normal_speed`、`slow_motion`、`boundary_frames`或`machine`，`result`为`pass`、`fail`或`unverified`。

## 四份工作表

| 文件 | 用途 |
| --- | --- |
| shots.csv | 每个镜头的范围、造型、状态、接触、前景和跟踪锚点 |
| pose-events.csv | 镜头内部姿态、头向、眼嘴和手部状态的切换 |
| layers.csv | 物体来源、时间范围、图层顺序及遮挡规则 |
| reviews.csv | 实际检查范围、检查方式、问题及最终文件证据 |

## 填写示例

本片握杯问题可以记录为：镜头范围`[1401,1543)`，接触模式`joint_cel`，杯和裸手来自同一采用原画；禁止再次恢复源杯旧指。验收为该区间连续播放、接触边界逐帧和最终文件抽帧，案例见[返修记录](../../docs/v4-revision.md#案例与证据)。新项目需要重新确定自己的帧范围。

## 开始制作前的人工核对

1. project.json的源文件、SHA256、帧率和帧数已填；每项保留范围已经确认。
2. 镜头无未解释的空洞/重叠，所有参考帧落在源媒体范围内。
3. 姿态记录所指镜头和素材存在；缺图明确标`missing_asset`。
4. 遮挡关系没有循环；每件道具有主来源，接触阶段有对应姿态。
5. 最终验收记录指向实际检查的输出版本和文件哈希。

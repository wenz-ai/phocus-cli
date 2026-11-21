# 命令与 MCP

安装包会创建工作目录。`phocus paths` 显示原片库、热文件夹、Phocus 中转输出及成片目录。可以单独修改，例如 `phocus paths --library "/Volumes/Photos"`。每次调用也可以用 `--out` 临时指定成片目录。

```sh
# 已有 JPEG 或 PNG：批量交付，可离线运行
phocus export /photos/*.jpg --long-edge 2048 --jpeg-quality 88 --srgb --watermark-exif --watermark-width 55

# RAW：保留全尺寸母版与 sidecar，再生成小尺寸签名版
phocus render /photos/*.3FR --set exposure=0.25 tint_native=-0.003 \
  --curve rgb 0:0 64:52 192:205 255:255 --long-edge 1600 --watermark-text 'Studio'

# 官方 HNNR：先关闭自动输出，使用空队列
phocus hnnr /photos/sample.3FR --mode detail

# 查看调整或制作可继续编辑的副本
phocus inspect /photos/sample.3FR
phocus variant /photos/sample.3FR --crop 0.1 0.1 0.9 0.9 --rotate 90
```

`--curve` 可重复指定 rgb、red、green、blue 和 luma（亮度）通道。输入为 0–255 的 X:Y 控制点，X 由小到大，带 0 和 255 两端。其他通道沿用照片已有设置。`tint_native` 使用 Phocus sidecar 原始数值，范围 −0.015 至 +0.015，负值偏洋红、正值偏绿。裁切坐标是 0–1 的左、上、右、下边界。更多数值范围见 `phocus capabilities`。

## 导出选项

`render` 默认返回 Phocus 母版。给它增加交付选项后，返回值中的 `output` 是母版，`delivery.output` 是交付副本。`export` 可直接处理已渲染的多张 SDR JPEG 或 8 位 PNG。批次按输入顺序执行，错误结果保留先前已成功的路径。

| 选项 | 用途 |
|---|---|
| `--long-edge 2048` | 保持比例缩小，原图较小时保留原尺寸 |
| `--export-format jpeg` 或 `png` | 选择交付格式。透明输入请使用 PNG |
| `--jpeg-quality 88` | JPEG 质量 1–100 |
| `--srgb` | 有 ICC 时执行色彩转换；未标记的 RGB 按 sRGB 解释。默认保留原 ICC |
| `--watermark-text`、`--watermark-logo`、`--watermark-exif` | 任选一种；EXIF 只取实际存在的相机、镜头、焦距、光圈、快门、ISO |
| `--watermark-corner bottom-right`、`--watermark-width 35`、`--watermark-opacity 65` | 四角位置、占图宽度百分比、不透明度 |

交付副本使用 Pillow 在最终尺寸上加水印，省略原拍摄元数据；EXIF 水印的拍摄参数写在画面上。带 HDR 增益图的文件及 16 位 TIFF 不在此交付流程内。

## 可选 MCP

终端运行 `command -v phocus`，复制显示的绝对路径。支持 stdio 的 MCP 客户端可以这样配置：

```json
{"mcpServers":{"phocus":{"command":"/替换成上一步显示的绝对路径/phocus","args":["mcp"]}}}
```

Codex 中希望同时使用 MCP，可运行：

```sh
codex mcp add phocus -- "$(command -v phocus)" mcp
```

新开 MCP 会话后，可以按手上的文件和任务选择工具。

| 工作步骤 | 工具 | 什么时候用 |
|---|---|---|
| 检查原片 | `capabilities`、`inspect_photo` | 查调整范围，读 RAW 已保存的版本和参数。 |
| 处理 RAW | `make_variant`、`render_photos`、`denoise_raw` | 留可编辑副本、用同一配方渲染一组、做官方 HNNR。 |
| 检查成片 | `preview_result`、`sample_color`、`analyze_exposure` | 看全图或原尺寸细节，查局部色相、高光和暗部。 |
| 交付 | `export_photos`、`watermark_result`、`list_official_frames`、`export_official_frames` | 批量缩放或加水印，给单张成片加签名，选款并导出官方画框。 |

原片相对路径从 library 起算。`preview_result` 和 `watermark_result` 的相对路径从成片目录起算。渲染结果返回的绝对路径可以直接交给后续工具。

普通渲染使用 Phocus 当前输出预设。HNNR 使用 macOS 辅助功能和窗口定向接口，要求可见主窗口及缩略图面板。发行包为 Apple Silicon 附带原生 helper，使用源码时首次运行 HNNR 需 Xcode 命令行工具。

## 更多原生调整

`sharpen_radius` 以像素为单位，步长 0.1，可搭配 `sharpen_threshold`、`sharpen_dark_limit`。黑白通道混合使用 `mono_red`、`mono_green`、`mono_blue`，写入时启用 Phocus 黑白处理。颗粒支持 `grain_type`（0–2）和 `grain_color`。镜头与透视参数见 `phocus capabilities` 中的 `lens_corrections`、`vignette_amount`、`defringe_*` 和 `keystone_*`。在 `variant` 或 `render` 中传入 `--straighten 3.5` 可拉直 3.5 度，也可配合直角旋转。

## 调整一段颜色

例如黄色杯盖偏艳，希望减一点饱和度、把黄色略微推向绿色：

```sh
phocus render "/photos/sample.3FR" --color-band yellow 25 12 0.75 0
```

五个值依次是**中心色相、选色角度、色相偏移、饱和度倍率、明度调整**。中心可以用 0 到小于 360 的度数，或 red、orange、yellow、green、cyan、blue、purple、magenta。角度 1–90°，偏移 −45 到 +45°，饱和度 0.3–1.7（1 为原值），明度 −50 到 +50（0 为原值）。同一命令可以重复传 `--color-band`。已存在的同中心选色点会更新，其他选色点保留。`--clear-color-bands` 清除工作副本已有的选色点，也可与新选色组合使用。画面中其他相近颜色也会受到影响。

不知道目标色相时，对渲染的 SDR 预览运行 `phocus sample preview.jpg --at 0.7 0.6`。坐标以左上角为原点、范围 0–1，结果包含一小块区域的平均 sRGB 值及估算色相。色彩接近中性时 `estimated_hue` 返回 null。这个数值可用作选色起点，具体效果以 RAW 导出为准。

## 控制黑场、白场和中间调

```sh
phocus render "/photos/sample.3FR" --levels rgb 12 1.2 242 --levels blue 3 1.0 245
```

顺序是**通道、黑场、中间调、白场**。黑白场范围 0–255，黑场必须小于白场；中间调 1 为原值，支持 0.1–4。RGB 设置一组共同的色阶，red、green、blue 可以分别覆盖；只给单通道时其他通道沿用原有设置。

MCP 的 `render_photos` 和 `make_variant` 支持同样的设置。例如：
```json
{"photos":["sample.3FR"],"color_bands":[{"hue":"yellow","width":25,"shift":12,"saturation":0.75}],"levels":{"rgb":{"black":12,"mid":1.2,"white":242}}}
```
用 `sample_color` 取样，或用 `inspect_photo` 查看已保存的 `levels` 与 `color_bands`。

### 线性渐变曝光

`--linear-mask 名称 满强度X 满强度Y 零强度X 零强度Y EV` 为原始图像坐标（左上角为原点，0–1）。满强度端向外保持指定 EV；两点间渐变，到零强度端另一侧恢复原图。例如 `--linear-mask sky 0.5 0.1 0.5 0.55 -1` 压暗画面上部。可重复添加不同名称；再次指定同名简单渐变会更新该层。使用包含裁切或旋转的照片时，仍按未裁切的原始图像定位。

`render_photos` 或 `make_variant` 的对应参数是 `linear_masks: [{"name":"sky","full":[0.5,0.1],"zero":[0.5,0.55],"ev":-1}]`。输出为 Phocus 可继续编辑的调节层。`inspect_photo` 可读回层名、曝光和位置。

## 检查高光与暗部

`phocus exposure-stats 成片.jpg` 返回 8 位 sRGB 成片红、绿、蓝三个通道各自落在 0 和 255 的像素数及百分比。用 `--region 0 0 1 0.3` 只检查画面顶部 30%。坐标以按 EXIF 方向显示的画面为准，从左上角起算。带 ICC 的图片先转换到 sRGB。

MCP 调用 `analyze_exposure` 时传入 `{"file":"成片.jpg","region":[0,0,1,0.3]}`。例如拍演出时，可以单独检查红色舞台灯附近的红通道。这个数值反映当前导出效果；判断 RAW 还有多少可恢复细节，需要调整曝光再渲染比较。

## 原生除尘点

`phocus render 照片.3FR --dust-spot 2436 2360 80 1` 在未裁切、未旋转原图的像素坐标 X=2436、Y=2360 创建圆形除尘点。半径使用原生面板范围 5–200 像素，强度为 1–10。重复参数可处理多个点，同中心圆点会更新。适合在同一机身、相同原图尺寸的一组照片中清理固定位置的传感器灰尘。机身标识直接从当前 RAW 读取。

MCP 参数为 `dust_spots: [{"x":2436,"y":2360,"radius":80,"amount":1}]`，可用 `inspect_photo` 回读圆点。已有其他形状保留。

## 画笔与橡皮擦

`--brush-stroke 衣服 paint 0.02 0.5 0.40:0.55 0.48:0.60` 用圆头笔沿路径在名为“衣服”的图层涂抹，曝光为 +0.5 EV。坐标是未裁切原片左上角起算的 0–1，半径是原图短边的比例。单点画圆，多个点连成笔画。重复参数按顺序叠加；用 `erase` 擦同名图层，再配合 `--layer-adjust` 调整颜色。首版支持硬边圆笔、Phocus TileFactor=2 的 16 位蒙版，适用性已在 X2D 100C 验证。

MCP 的对应参数为 `brush_strokes: [{"name":"衣服","mode":"paint","radius":0.02,"ev":0.5,"points":[[0.4,0.55],[0.48,0.60]]}]`。图层保存后可在 Phocus 内继续涂改。

## 给调节层校色

`--layer-adjust 人脸 temperature 13 --layer-adjust 人脸 highlights 27` 只改变名为“人脸”的原生调节层。可在同一次调用中先创建线性或径向蒙版。MCP 的对应字段为 `layer_adjustments: {"人脸":{"temperature":13,"highlights":27}}`。temperature、tint、highlights、shadows、saturation、clarity 为 −100 至 100；sharpness 为 −500 至 500；moire 为 −5 至 5。色温使用 Phocus 局部面板的相对刻度。已有图层的启用状态、蒙版和未指定参数保留。

## 径向局部曝光

`phocus render 照片.3FR --radial-mask 人脸 0.48 0.36 0.12 0.18 0 0.35 inside 0.5` 会在椭圆内提亮半档。名称之后依次为中心 X/Y、水平和垂直半径、角度（度）、羽化（0–1）、inside 或 outside、曝光 EV。中心和半径相对未裁切原图的宽高。同名简单椭圆会更新，复杂图层请换一个名称。

MCP 的 `make_variant` 与 `render_photos` 接受 `radial_masks: [{"name":"人脸","center":[0.48,0.36],"radii":[0.12,0.18],"feather":0.35,"ev":0.5}]`。

## 接续一个批次

给 `render` 或 `export` 加上 `--batch-id portraits-01`，MCP 中对应参数为 `batch_id`。首次运行将配方和每张成片保存到输出目录的 `batch-portraits-01` 下。遇到坏文件时，结果会逐张列出 `completed`、`failed` 和 `pending`。修好失败文件后，重跑同一条命令即可。文件顺序、配方和输出目录须相同；已完成的原片或配方需要重新处理时，请换批次名。CLI 遇到失败返回非零退出码，MCP 返回逐张状态。每张交付文件与回执一起发布，中断后只重做尚未交付的项目。

## 并排对比成片

`phocus compare 调整前.jpg 调整后.jpg --crop 3500 2100 600 600` 生成左前右后的无损 PNG，两侧显示同一区域的原始像素。省略 `--crop` 则显示整图。支持同一构图、相同显示尺寸的 SDR JPEG/PNG；软件按 EXIF 方向定位并转换到 sRGB。单次 MCP 调用 `preview_result(file=调整前, compare_with=调整后, crop=[3500,2100,600,600])` 即可返回对照图。

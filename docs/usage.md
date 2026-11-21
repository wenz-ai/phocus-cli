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

`--curve` 可重复指定 rgb、red、green、blue 四个通道。输入为 0–255 的 X:Y 控制点，X 由小到大，带 0 和 255 两端。其他通道沿用照片已有设置。`tint_native` 使用 Phocus sidecar 原始数值，范围 −0.015 至 +0.015，负值偏洋红、正值偏绿。裁切坐标是 0–1 的左、上、右、下边界。更多数值范围见 `phocus capabilities`。

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

新开对话后，客户端可以发现 `capabilities`、`inspect_photo`、`make_variant`、`denoise_raw`、`render_photos`、`export_photos`、`watermark_result` 和 `preview_result`。预览支持原尺寸局部。MCP 的相对原片路径基于 library，已输出成片可传绝对路径。

普通渲染使用 Phocus 当前输出预设。HNNR 使用 macOS 辅助功能和窗口定向接口，要求可见主窗口及缩略图面板。发行包为 Apple Silicon 附带原生 helper，使用源码时首次运行 HNNR 需 Xcode 命令行工具。

# Phocus CLI & MCP Bridge

[功能覆盖与待开发项目](CAPABILITIES.md)


[![macOS tests](https://github.com/wenz-ai/phocus-cli/actions/workflows/tests.yml/badge.svg)](https://github.com/wenz-ai/phocus-cli/actions/workflows/tests.yml)

用一条命令批量调整哈苏 RAW，由 **Hasselblad Phocus** 在 Mac 上导出全尺寸成片。摄影师可以保留多个可编辑版本；AI 客户端可以先看整张构图，再取一块原尺寸细节判断降噪与锐化。工具在本地读写工作副本，原片和已有调整保存在原处。

*A local CLI and stdio MCP server for Hasselblad Phocus. Batch-edit RAW copies, render through the desktop app’s hot folder, and request previews only when needed. Tested on macOS with Phocus 4.2.3 and X2D 100C files. Independently developed.*

## 先试一个离线版本

安装 Python 3.9 或以上版本。下载仓库后，CLI 使用 Python 标准库和 macOS 自带工具。

```sh
git clone https://github.com/wenz-ai/phocus-cli.git
cd phocus-cli
./phocus capabilities
./phocus inspect "/photos/sample.3FR"
./phocus variant "/photos/sample.3FR" --out "/photos/variants" \
  --set exposure=0.33 highlights=15
```

`inspect` 和 `variant` 使用这张 RAW 自己的 `.3FR.phos` 文件，Phocus 可以关闭。成功后 `variant` 返回新目录中的 RAW 与调整记录，打开该副本即可继续编辑。只有裸 RAW 时，直接用下方的 `render`。

## 让 Phocus 在后台出片

1. 建立三个目录。例如 `/photos/inbox` 接收临时 RAW，`/photos/spool` 接收 Phocus 导出，`/photos/results` 存放最终结果。后两个目录均在 inbox 以外。
2. 在 Phocus 中选一张照片，手动导出一次到 spool。选**全尺寸 JPEG**，命名预设包含源文件名，关闭附加输出，导出后操作选“无”。这会记住输出格式与目的地。
3. 在 Phocus 文件浏览器选中 inbox，勾选 **文件 → 自动输出新的图像**（File → Export New Images Automatically）。现在可以切到其他应用。Phocus 需要保持打开，并停留在 inbox。
4. 完成后取消这个勾选，再回到日常照片目录。Phocus 的监看对象随浏览目录改变。

```sh
./phocus render /photos/session/*.3FR \
  --watch /photos/inbox --spool /photos/spool --out /photos/results \
  --set noise_filter_bias=4 color_noise_radius=12
```

上例是比较降噪效果的起点。每张照片得到一个新结果目录，含成片及配套的 `.phos`。已有 sidecar 的照片只需一次渲染。对没有 sidecar 的原片设置参数时，工具先让 Phocus 为它生成调整记录，再用第二轮渲染出片。APFS 同卷可利用写时复制。超时默认每轮 90 秒，可通过 `--timeout` 修改；错误信息包含可恢复的工作副本路径。

## 能调哪些参数

| 用途 | 参数与范围 |
|---|---|
| 明暗 | `exposure` −4 至 +4 EV；`contrast`、`brightness` −50 至 50；`highlights`、`shadows` −100 至 100 |
| 色彩 | `temperature` 2500–10000 K，`saturation`、`vibrance` −50 至 50 |
| 清晰度与锐化 | `clarity` −100 至 100，`detail` −10 至 10，`sharpen_amount` 0–200。测试 detail 时请同时给 clarity 一个非零值 |
| 胶片颗粒 | `grain_amount`、`grain_size`、`grain_roughness` 0–100。修改其中一项会开启颗粒 |
| 常规降噪 | `noise_filter_bias` −10 至 10 对应亮度降噪，`color_noise_radius` 0–50 控制彩色降噪 |
| 图案校正 | `moire_removal` 0–5 处理全局摩尔纹，`remove_checkerboard` 0/1 控制棋盘格校正 |

## 官方 HNNR 桌面桥（实验性）

`hnnr` 调用正在运行的 Phocus，生成新的降噪 .3FR。支持 `purity`（纯净优先）和 `detail`（细节优先）。该命令需要 macOS 图形会话、可见的 Phocus 主窗口及缩略图面板、Xcode 命令行工具，以及运行客户端的辅助功能权限。首次使用会在本地编译 Swift helper。

在 Phocus 中选中 **空的专用队列**，关闭「自动输出新的图像」，然后运行：

```sh
./phocus hnnr /photos/sample.3FR --mode detail --watch /photos/inbox --out /photos/results
```

命令把 RAW 副本放入队列，向 Phocus 的缩略图定向右键，检查官方模式窗口只有一张可处理照片，选择模式并提交。原生模式窗及进度窗仍会出现；两次被监测的测试中前台应用都保持可用。macOS 的窗口坐标接口未公开，不同系统版本可能影响兼容性。目前识别简体中文及英文控件，实测使用简体中文。运行期间请让 Phocus 停留在队列目录。若超时，会报告工作副本位置。

返回的 `output` 是新 RAW，能继续交给 `render_photos`。需要导出 JPEG 时，先重新开启 Phocus 的自动输出。HNNR 处理传感器数据，命令从原始 RAW 建立工作副本，后续调色请应用到降噪后的文件。

## 构图与水印

`variant` 和 `render` 都支持 `--crop LEFT TOP RIGHT BOTTOM`。边界是 0 到 1 的归一化坐标，表示原图中的矩形。`--rotate` 接受逆时针 0、90、180、270 度。`monochrome=1` 开启 Phocus 黑白工具，0 关闭。裁切、旋转和黑白都由 Phocus 自己渲染。

```sh
./phocus variant /photos/sample.3FR --out /photos/variants \
  --crop 0.25 0.25 0.75 0.75 --rotate 90 --set monochrome=1
```

水印是独立的导出后步骤，支持文字或透明 PNG logo。安装 Pillow 后，用同一 Python 解释器运行 CLI。可选四角位置、占图宽度百分比、透明度、JPEG 或 PNG 输出。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'Pillow>=11,<14'
.venv/bin/python phocus watermark /photos/finished.jpg --text 'Studio / 2026' --out /photos/results
.venv/bin/python phocus watermark /photos/finished.jpg --logo /photos/logo.png \
  --corner bottom-left --width-pct 12 --opacity 70 --format png --out /photos/results
```

水印处理普通 SDR JPEG 和 8 位 PNG，显示方向按 EXIF 校正，保留源 ICC 色彩配置，另存带标记的副本并省略拍摄元数据。JPEG 会重新压缩，需要保留水印区外的原像素时选择 PNG。哈苏官方相框、HDR 增益图水印、16 位 TIFF 水印仍待验证。

## 接入 MCP

使用 Python 3.10+。CLI 本身可单独使用。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'mcp==1.30.0' 'Pillow>=11,<14'
```

以下为支持 `mcpServers` 配置格式的客户端示例。终端工作目录可能与图形应用不同，请填写绝对路径。library 是可读取的 RAW 根目录，out 是派生图片的根目录。

```json
{
  "mcpServers": {
    "phocus": {
      "command": "/path/to/phocus-cli/.venv/bin/python",
      "args": [
        "/path/to/phocus-cli/mcp_server.py",
        "--library", "/photos/session",
        "--watch", "/photos/inbox",
        "--spool", "/photos/spool",
        "--out", "/photos/results"
      ]
    }
  }
}
```

| 工具 | 用法 |
|---|---|
| `capabilities` | 查询参数、范围与对应的 Phocus 字段 |
| `inspect_photo` | 读取已保存的调整及历史版本名称 |
| `make_variant` | 创建新的可编辑 RAW 副本 |
| `render_photos` | 一次提交多张照片与一组参数，返回文件路径、尺寸及耗时 |
| `denoise_raw` | 在专用队列中提交 Phocus HNNR，返回可再次传入渲染工具的 RAW 路径 |
| `watermark_result` | 给成片添加文字或 library 目录中的 PNG logo，返回新文件路径 |
| `preview_result` | 默认返回长边 1280 像素的总览。传入 `crop: [x, y, width, height]` 取左上角起算的原尺寸局部，每边最多 1280 像素 |

例如，比较同张照片两种降噪设置时，可以让助手“各导出一版，取两张成片相同位置的 512 × 512 暗部，再看整张”。只有调用预览工具时，图片才会进入所连接的 MCP 客户端。

## 验证与兼容性

已验证的组合是 macOS、Phocus 4.2.3、X2D 100C、全尺寸 JPEG、sidecar 版本 31 / ImageCorrection 版本 11。锁屏、休眠、其他机型、其他 Phocus 版本和 TIFF/HDR 导出仍需分别验证。一次 16 张次的旧版基准测试中，约 212 MB 的 RAW 渲染中位数为 3.91 秒；一次仅生成离线副本约 0.04 秒。速度取决于硬件、存储和输出预设。

[验证记录及复跑命令](TESTING.md) · [GitHub Actions](https://github.com/wenz-ai/phocus-cli/actions/workflows/tests.yml) · [Phocus 热文件夹工作方式](https://blog.tonalphoto.com/phocus-hot-folder-batch-processing/)

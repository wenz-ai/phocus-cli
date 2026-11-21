# Phocus CLI

在 Mac 上用 Codex 或终端批量处理哈苏照片。你可以先让 AI 在一张 RAW 上试色，放大看肤色和暗部，再把确认的调整用到同一组照片。RAW 由哈苏 Phocus 渲染，原片保留，成片另存。

**[下载 macOS 安装包](https://github.com/wenz-ai/phocus-cli/releases/latest/download/Phocus-CLI-macOS.zip)** · [命令示例](docs/usage.md) · [完整功能清单](CAPABILITIES.md)

## 可以做什么

| 想做的事 | 能拿到什么 |
|---|---|
| 调色、构图 | 调整曝光、白平衡、曲线和色阶，单独改变某一段颜色，也能裁切或旋转。编辑结果可在 Phocus 中接着修。 |
| 检查高光、暗部 | 统计成片或局部选区各颜色通道到达纯黑、纯白端点的像素比例，辅助判断调色效果。 |
| 批量出片 | 给一组 RAW 应用同一套调整，一次导出全尺寸母版和长边、质量可选的 sRGB 交付版。 |
| 哈苏 AI 降噪 | 调用官方 HNNR，选择「细节优先」或「纯净优先」，得到可继续调色的新 RAW。 |
| 签名、水印和画框 | 给 SDR JPEG/PNG 加文字、透明 logo 或 EXIF 拍摄参数。可选引擎另外提供 7 款 Hasselblad 官方画框，以及适用机身可用的 2 款 Earth Explorer 画框。[画框安装与示例](docs/frames.md) |

## 安装到 Mac

1. 下载上方的 macOS 安装包并解压。
2. 双击 **安装 Phocus.command**，等终端显示「安装完成」。首次安装需要联网。
3. 如果使用 Codex，新开一个对话，输入 `$phocus-photo` 即可调用随附的 Skill。习惯用终端的话，运行 `phocus --help` 查看命令。

<details>
<summary>macOS 拦截了双击安装</summary>

打开「终端」，输入 `/bin/bash `（末尾留一个空格），将解压后的 **安装 Phocus.command** 拖入终端，按回车。

</details>

## 第一次出片

找一张 JPEG 拖进 Codex 对话，直接说：

> 用 $phocus-photo 把这张照片导出成长边 2048 像素的 JPEG，右下角加上我的签名「晴天」，告诉我成片在哪。

如果用终端，把示例里的文件名换成自己的照片：

```sh
phocus export "照片.jpg" --long-edge 2048 --watermark-text "晴天"
```

这一步可以关闭 Phocus。默认成片在 **图片 → Phocus CLI → 成片**。有自定义目录时，运行 `phocus paths` 即可查看。

## 第一次批量处理 RAW

先安装并打开[哈苏 Phocus](https://www.hasselblad.com/phocus/phocus-for-pc-mac/)。以下设置让 Phocus 自动接收 CLI 送来的 RAW 工作副本：

1. 在 Phocus 中手动导出一张**全尺寸 JPEG** 到 **图片 → Phocus CLI → Phocus 输出**。命名预设选含源文件名，关闭附加输出。
2. 在 Phocus 左侧选中 **图片 → Phocus CLI → 待处理**，勾选 **文件 → 自动输出新的图像**。批处理期间保持 Phocus 打开并停在这个目录。
3. 把 RAW 所在的文件夹路径给 Codex，例如：“先拿一张试一下，把黄色杯盖的饱和度降一点，给我看前后对比。等我选好，再按这个效果处理这一组。”

使用 **HNNR** 时，让 Phocus 停在空的「待处理」目录，先取消「自动输出新的图像」。按 macOS 提示授予运行客户端辅助功能权限。降噪完成后，重新勾选自动输出即可继续渲染 JPEG。

## CLI、Skill 和 MCP 怎么选

- **在 Codex 里修图**：默认安装的 `$phocus-photo` Skill 会调用本机 CLI。
- **在终端或脚本里跑批次**：直接使用 `phocus`，执行结果以 JSON 返回。
- **在其他 AI 客户端接入**：支持 MCP 的客户端可以调用 `phocus mcp`，获取结构化工具和原尺寸局部预览。[MCP 配置示例](docs/usage.md#可选-mcp)

本项目独立开发，已在 Hasselblad X2D 100C 与 Mac 版 Phocus 4.2.3 上验证。[查看验证记录](TESTING.md)

## 许可证

项目代码以 [MIT 许可证](LICENSE) 开源，欢迎提交 Issue 和 PR。哈苏 Phocus 软件及品牌素材沿用各自的授权。

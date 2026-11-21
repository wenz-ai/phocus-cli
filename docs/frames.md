# 使用 Windows Phocus 的官方画框

哈苏在 Phocus 4.2 的 **PC** 发布说明中列出了 JPG 哈苏画框。对照同版 Mac 导出预设、Mac 4.2.3 的本机发布说明及应用资源，我们没有找到可以调用的同款 Mac 原生入口。这个可选后端直接运行 Windows 安装包里的 `PhocusApi64.dll`，通过画框选择器自己使用的 `GetPhotoFramePreviewSize` 和 `RenderPhotoFramePreview` 渲染。图形与文字布局由原版 DLL 生成。CLI 负责准备拍摄参数、色彩转换与 JPEG 编码。

## 在 Mac 上准备一次

需要 Apple Silicon Mac、Rosetta，以及约数 GB 的本地环境和额外解包空间。已配置的机器可直接跳到导出。首次设置会下载哈苏官方 4.2 x64 安装包（约 1.22 GB）、Windows Python 及本地运行环境，按 SHA-256 校验，在本机建立专用的 Colima/Docker 镜像。基础 CLI、Skill 和其他 MCP 工具可独立使用。

```sh
brew install docker colima cabextract msitools
phocus frames setup
```

如果已经下载过官方安装包，可用 `phocus frames setup --installer "/path/to/Phocus-4.2-x64.exe"`。画框渲染在断网容器中运行，图像通过本机标准输入输出传递。Windows 软件、品牌图案和用户照片均未打入项目发行包。

## 导出

```sh
phocus frames list
phocus frames export "/photos/master.jpg" --styles explorer-1 --long-edge 2048
phocus frames export "/photos/master.jpg" --styles all
phocus frames export "/photos/original.3FR" --styles hasselblad-2 hasselblad-7
```

- **Hasselblad 1–7** 对应 `hasselblad-1` 到 `hasselblad-7`。
- **Explorer 1–2** 对应 `explorer-1`、`explorer-2`。白色山峰和双圆弧直接叠在画面上的是 **Explorer 1**。
- `all` 按官方选择器顺序输出此照片适用的款式。PC 选择器会按机身版本筛选 Explorer；CLI 读取真实 EXIF、XMP 或哈苏 ImageUniqueID 里的机身信息，识别不到兼容机身时可用普通款。
- 请使用未加框且保留机型/镜头信息的母版；社交平台有时会去掉这些信息。CLI 会识别本工具写出的画框标记，外部软件已清除标记的成片需要自行辨别。
- RAW 走既有 Mac Phocus 热文件夹流程生成母版后再加框；已有 JPEG 加框可关闭 Mac Phocus。`--long-edge` 限制照片内容的长边，外框会增加最终像素尺寸。`--quality` 指定 JPEG 质量。
- MCP 工具为 `list_official_frames` 和 `export_official_frames`。后者传入文件路径和款式列表，例如 `{"file":"master.jpg","styles":["all"],"long_edge":2048}`。
- 渲染采用 Windows 4.2 的 **8 位 RGB 画框接口**，输出为 SDR sRGB JPEG。Windows 全套导出容器、Ultra HDR 增益图、手机自定义手写签名属于其他功能。兼容层使用 DirectWrite 字体回退，文本字形可能与原生 Windows 有细微差别。

使用完可以运行 `colima stop phocus-frames` 释放虚拟机内存。已配置的专用环境可在下次调用时启动。

[官方 PC 4.2 说明](https://cdn.hasselblad.com/software/Phocus_for_PC/4.2/Phocus-4.2-readme.pdf) · [官方 Mac 4.2.3 说明](https://cdn.hasselblad.com/software/Phocus_for_Mac/4.2.3/Phocus-Mac-read-me.pdf) · [官方软件下载目录](https://www.hasselblad.com/downloads/#133)

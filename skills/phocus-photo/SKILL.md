---
name: phocus-photo
description: 使用本机 Phocus CLI 给哈苏 .3FR 调色、裁切、HNNR 降噪、导出哈苏官方画框，或将已有 JPEG/PNG 批量缩放、添加签名、logo 或 EXIF 水印。适用于用户要求处理哈苏照片、比较后期版本及交付成片。
---

先选入口。已有 JPEG/PNG 直接调用 `phocus export`；需要哈苏 RAW 渲染时调用 `phocus render`。CLI 已装但当前 shell 找不到命令时，用 `~/.local/bin/phocus`。通过 `phocus paths` 读取实际工作目录；用户提供的路径优先。

- RAW 调整按 `phocus capabilities` 返回的字段和范围传入。曲线用 `--curve rgb 0:0 128:152 255:255`，可重复指定 red、green、blue。Tint 的 `tint_native` 使用 sidecar 数值。先渲染代表照片检查肤色和高光，再将同一配方应用到光线相近的一组。
- Phocus 渲染需在软件中选中工作队列，开启「自动输出新的图像」，输出到配置的 spool。只需可编辑副本时，已有自己的 .phos 的 RAW 可以直接用 `variant`。
- HNNR 用 `phocus hnnr FILE --mode detail` 或 `purity`。让 Phocus 停在空队列并关闭自动输出。命令会操作官方模式窗口，返回新的 RAW。导出 JPEG 前重新打开自动输出，用相同位置的原尺寸暗部或纹理比较效果。
- 批量交付可在一次 render 中加 `--long-edge 2048 --jpeg-quality 88 --srgb --watermark-exif`。文字、PNG logo、EXIF 水印三选一；按需要用 `--watermark-width` 调节大小。render 返回 output（母版）和 delivery.output（交付版），报告用户所需的文件。
- 只有连接 MCP 的客户端才用 `render_photos`、`export_photos`、`preview_result` 等工具。CLI 足以完成同一工作流。

- 用户说哈苏专属框或 Earth Explorer 时使用 `phocus frames export FILE --styles explorer-1`（或 MCP `export_official_frames`）。用 `frames list` 看 9 个款式，`all` 输出当前照片可用款式。输入需为哈苏 RAW 或保留 EXIF 的未加框 SDR JPEG。文字、EXIF 和普通 logo 水印仍走 `export`。

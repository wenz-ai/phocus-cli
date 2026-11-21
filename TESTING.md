# 验证记录

## 成片对照

测试日期为 2026-11-21。真实样张来自 Hasselblad X2D 100C，EXIF 感光度 ISO 6400，Phocus 4.2.3 导出的 JPEG 尺寸为 11656 × 8742。两张对照图都经过完整渲染，没有用 RAW 内嵌缩略图代替。

对每个参数分别设置基线和测试值，回读导出后的 .phos，再比较两张 JPEG 在相同位置的 16 个 256 × 256 原尺寸区域。18 个参数都改变了采样区域的实际像素。测试颗粒大小、粗糙度时，两边都启用颗粒；测试 detail 时，两边 clarity 都设为 40。

| 参数 | 基线 → 测试值 | RGB 平均绝对差（0–255） |
|---|---|---:|
| 亮度降噪偏置 | 0 → 10 | 1.550 |
| 彩色降噪半径 | 0 → 40 | 0.679 |
| 全局摩尔纹 | 0 → 5 | 0.610 |
| 棋盘格校正 | 关 → 开 | 0.962 |

这些数值用于查出“参数保存成功，成片却完全相同”的问题。数值大小取决于场景、JPEG 编码和采样位置，不能作为降噪质量评分。棋盘格和摩尔纹测试证实处理生效，能否消除具体伪影要看有相应问题的原片。HNNR 不在本测试范围内。[逐项结果](tests/x2d-iso6400.jsonl)

## 命令及 MCP

- CLI 覆盖 capabilities、inspect、variant 和 render。离线测试覆盖全部参数的上下界、非法数值、格式版本、损坏的 sidecar、历史保留和输入输出隔离。
- MCP 使用官方 SDK 的 stdio 客户端，覆盖工具列表、参数查询、原片检查、制作副本、真实后台渲染、预览和路径边界。裸 RAW 带调整走两轮渲染。两张 RAW 还通过同一次 MCP 调用批量导出，按提交顺序返回结果。
- 局部预览使用具有已知色块坐标的测试图验证尺寸、原点和位置，并用真实 ISO 6400 成片取相同位置的局部检查降噪。测试也覆盖越界裁切。
- 自动化 CI 在 macOS 上运行离线测试和 MCP 协议测试。实际渲染需要安装 Phocus、配置热文件夹并提供 RAW，在本地运行。

## 如何复跑

在仓库根目录运行。离线 CLI 测试只依赖 Python 标准库；协议测试及像素对照另需 MCP SDK 与 Pillow。

```sh
python3 -m unittest -v test_phocus
python3 -m venv .venv
.venv/bin/python -m pip install -r tests/requirements.txt
.venv/bin/python tests/test_mcp.py -v
```

按 [README](README.md) 配置热文件夹，选择一张代表性 RAW，运行真实对照。默认在临时目录中生成、对比并清理样片，仅把测量值写到标准输出。测试会多次解码一亿像素 JPEG，需要为临时渲染结果预留磁盘空间。

```sh
.venv/bin/python tests/live_matrix.py /photos/high-iso.3FR \
  --watch /photos/inbox --spool /photos/spool > result.jsonl
```

若某项未改变所选区域的像素，脚本会报告具体参数并返回非零状态。在已有 sidecar 的原片上测试更快。

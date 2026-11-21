# Phocus CLI 与 MCP Bridge

在 macOS 上批量处理哈苏 .3FR。命令写入工作副本的 .phos 调整记录，再把副本交给 Hasselblad Phocus 的「自动输出新的图像」。可直接在其他应用中工作。CLI 和 MCP 均不使用鼠标、键盘、截图、辅助功能、屏幕录制或模型 API。原片与原有调整保存在原处。本项目是独立开发的适配器。

## 第一次使用

CLI 使用 Python 3.9+ 和 macOS 自带的 cp、sips。文件夹最好在同一个 APFS 卷上，这样 200 MB 的 RAW 可以用写时复制创建工作副本。离线 inspect、variant 只需现有 .phos。render 需要打开官方 Phocus，首次配置时会用到一次官方的输出窗口。

1. 准备三个目录。watch 用来接收临时 RAW，spool 接收 Phocus 的导出，out 保存整理后的成片。spool 和 out 都放在 watch 以外。
2. 在 Phocus 中手动导出一张照片到 spool，选全尺寸 JPEG、含源文件名的命名预设，以及「输出后没有后续步骤」。使用单个输出，关闭附加输出。热文件夹沿用这组设置。
3. 在 Phocus 的文件浏览器中选中 watch 文件夹，勾选「文件 → 自动输出新的图像」。Phocus 可留在其他应用后面。渲染期间保持 Phocus 的浏览目录与输出预设不变。结束后再次点击该菜单取消勾选，再切换到日常照片目录。
4. 运行下面的命令。将示例路径换成实际路径。每张成片和与源 RAW 同名的 .phos 都放在新的结果目录中。

```sh
./phocus capabilities
./phocus inspect /photos/sample.3FR
./phocus variant /photos/sample.3FR --out /photos/variants --set exposure=0.5 highlights=20
./phocus render /photos/sample.3FR --watch /photos/inbox --spool /photos/spool --out /photos/results --set exposure=0.5 highlights=20
./phocus render /photos/day/*.3FR --watch /photos/inbox --spool /photos/spool --out /photos/results --set temperature=5000
```

所有命令返回 JSON。render 可以一次传多张，按顺序完成。没有 .phos 的原片若要调参，会先由 Phocus 生成这张照片自己的调整记录，再渲染目标效果。已有 .phos 则直接在它的当前版本上调整。离线制作多个可编辑版本用 variant，输出是 RAW 和配套的 .phos。inspect 返回当前设置和历史版本名称。exposure 以 EV 为单位，temperature 用 K；其他参数的取值范围见 capabilities。

一次输出的默认等待时间是 90 秒，可用 --timeout 调整。超时会报告任务路径，保留工作副本供检查。先检查 Phocus 是否仍在浏览 watch、是否启用了自动输出、输出位置和命名是否正确。批处理遇错时，JSON 会列出此前成功的项目和出错的源文件。

## MCP

MCP 使用官方 Python SDK 的 stdio 传输。用 Python 3.10+ 创建虚拟环境，版本 1.30.0 已实测。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'mcp==1.30.0'
```

客户端的 command 填虚拟环境 Python 的绝对路径，args 按下列顺序填写。library 允许读取源 .3FR，out 存放派生结果。

```json
{
  "command": "/path/to/phocus-cli/.venv/bin/python",
  "args": [
    "/path/to/phocus-cli/mcp_server.py",
    "--library", "/photos",
    "--watch", "/photos/inbox",
    "--spool", "/photos/spool",
    "--out", "/photos/results"
  ]
}
```

| 工具 | 结果 |
|---|---|
| capabilities | 参数、单位对应的存储字段和输入范围 |
| inspect_photo | 一张照片的当前调整和历史名称 |
| make_variant | 独立的可编辑副本路径 |
| render_photos | 一次提交多张照片和一组参数，返回成片路径、分辨率、耗时 |
| preview_result | 按需返回最长边 1280 像素的 JPEG，供模型判断下一步调整 |

## 实测条件

实测环境为 macOS、Phocus 4.2.3、X2D 100C 的 11656 × 8742 RAW、全尺寸 JPEG。写入适配 .phos 版本 31、ImageCorrection 版本 11。支持的参数反映此版本已观察到的字段，零值和开关保留各工具自身的含义，例如修改颗粒大小也会启用颗粒。其他相机、Phocus 版本、HDR 和 TIFF 工作流需要分别验证。

Phocus 需要保持运行，并占用本机的解码算力。没有 MCP 主机时 CLI 也能工作。锁屏、休眠以及在同一个 Phocus 实例里同时手动浏览别的目录不在此次后台验证范围内。

[哈苏官方 Phocus](https://www.hasselblad.com/phocus/phocus-for-pc-mac/) · [Phocus 4.2.3 热文件夹实测](https://blog.tonalphoto.com/phocus-hot-folder-batch-processing/) · [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

### 成本与画面对照

同一张约 212 MB 的 X2D 原片、同一 JPEG 预设、本机 APFS。一次不改参数加 15 次单参数任务共 16 次完整导出。已有 sidecar 时中位数 3.912 秒，范围 3.280–4.642 秒。每个任务包含准备副本、官方渲染、校验导出记录/分辨率和归档。一次全新 RAW 带调整的 MCP 请求执行两轮，用时 7.667 秒。离线生成副本含 CLI 冷启动，15 次中位数 0.041 秒。

解码并对照实际 JPEG。曝光、反差、亮度、高光、暗部、色温、饱和度、自然饱和度、清晰度、锐化、降噪偏置与三项颗粒调节均得到有别于基线的输出。颗粒组测试包含开启颗粒的影响。清晰度为零时改变 detail 未测出差异，清晰度为 40 时将 detail 从 0 改至 8 可测出差异。这里验证了照片会变，具体审美仍需看预览。

前台通过 macOS 应用激活通知和约 50 毫秒一次的采样交叉检查。逐张调用系统导出框的早期原型曾触发 Phocus 激活，现有热文件夹版本在实测中没有触发。一次 render_photos 调用可传多张并等待完成，默认只回传文本。只有 preview_result 返回图像。没有采集模型账单或同任务的 Computer Use token 数。

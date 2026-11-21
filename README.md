# Phocus CLI

在 Mac 上用一句话处理哈苏照片。你可以让 Codex 给 RAW 降噪、调曲线、批量导出，也可以直接给已有的 JPEG 添加签名或拍摄参数水印。RAW 由哈苏官方 Phocus 处理，结果另存为新文件。

## 安装

1. [下载安装包](https://github.com/wenz-ai/phocus-cli/releases/latest/download/Phocus-CLI-macOS.zip)，解压。
2. 双击 **安装 Phocus.command**，看到「安装完成」即可关闭窗口。第一次安装需要联网。
3. 新开一个 Codex 对话，输入 `$phocus-photo`，然后告诉它要处理哪张照片。

如果 macOS 拦截双击，打开「终端」，输入 `/bin/bash `（末尾留一个空格），把安装文件拖进去，按回车。

## 先做一张带水印的照片

把一张有拍摄信息的 JPEG 拖进 Codex 对话，然后说：

> 用 $phocus-photo 把这张照片导出成长边 2048 的 JPEG，在右下角写上相机、镜头、光圈、快门和 ISO，告诉我成片在哪。

这一步可以直接试。也可以让它用你的名字或透明 PNG logo 做水印。默认成片在「图片 → Phocus CLI → 成片」。

## 处理哈苏 RAW

先[安装哈苏 Phocus](https://www.hasselblad.com/phocus/phocus-for-pc-mac/)。首次批量导出需要在 Phocus 中设一次目录：

1. 手动导出一张**全尺寸 JPEG** 到「图片 → Phocus CLI → Phocus 输出」，命名选含源文件名，关闭附加输出。
2. 在 Phocus 左侧选中「图片 → Phocus CLI → 待处理」，勾选 **文件 → 自动输出新的图像**。保持 Phocus 打开。
3. 把 RAW 路径交给 Codex，例如：“把这组照片暗部稍微提亮，导出 1600 像素的 sRGB JPEG，加上我的签名，同时留一份全尺寸母版。”

**哈苏 AI 降噪（HNNR）** 使用同一个空的「待处理」目录，运行前先取消「自动输出新的图像」。它会打开 Phocus 自己的模式窗，可选细节优先或纯净优先，产出新的 RAW。第一次使用时按 macOS 提示给运行客户端辅助功能权限。加工后的 RAW 可以接着调色和导出。

如果已经自定义过目录，运行 `phocus paths` 可查看实际位置。

## 我该用哪种方式？

| 你在哪里用 | 用什么 |
|---|---|
| Codex 里说中文修图 | **CLI + Skill**，安装包默认装好。Skill 教助手选命令和检查成片 |
| 终端或自己的脚本 | **CLI**，运行 `phocus --help` 查看命令 |
| 支持 MCP 的其他 AI 客户端 | **可选 MCP**，提供同一套操作的结构化参数，还能直接返回图片预览 |

[命令示例与 MCP 设置](docs/usage.md) · [功能清单](CAPABILITIES.md) · [验证记录](TESTING.md)

本项目独立开发。已用 Hasselblad X2D 100C 和 macOS 版 Phocus 4.2.3 验证。

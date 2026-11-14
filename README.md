# xhs-vn-post

为 if_line 视觉小说制作小红书、小黑盒图文素材与发布审核包。支持背景、透明立绘和原剧本对白合成，也可混排封面、CG 与角色卡；统一输出 1080×1440 图片、顺序预览、文案和文件校验清单。

本仓库是 skill 的开发源码。完整操作入口见 [SKILL.md](SKILL.md)，配置字段见 [references/config.md](references/config.md)。脚本只生成本地审核包，实际发布须由用户审核后交给对应发布 skill。

## 本地开发

需要 Python 3.10+、Pillow 和可用中文字体。Windows 默认探测微软雅黑或黑体；Linux 可安装 Noto CJK；也可在作品配置的 `font` 字段指定字体路径。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s scripts -p "test_*.py" -v
```

Linux/macOS 将以上解释器路径替换为 `.venv/bin/python`。

## 生成素材

复制 [examples/post.example.json](examples/post.example.json) 到 `work/作品名/post.json`，替换示例素材路径、真实台词、出处和文案。相对路径按配置所在目录解析。

```powershell
.\.venv\Scripts\python.exe scripts/compose_screens.py --config "work/作品名/post.json"
.\.venv\Scripts\python.exe scripts/compose_screens.py --config "work/作品名/post.json" --validate-only
.\.venv\Scripts\python.exe scripts/compose_screens.py --verify "work/作品名/out/pack-实际包编号"
```

每次生成独立目录；`manifest.json` 为完整包标记。个人素材、文案、产物及账号凭据不应提交到仓库，`work/` 和 `out/` 已忽略。

## 作为 skill 安装

开发时将客户端的 skill 安装位置链接到本仓库根目录，安装名称保持 `xhs-vn-post`。这样修改本仓库即可直接更新安装入口，无需重新复制。

Windows 可使用目录联接（Junction），支持安装位置与开发目录位于不同盘符。在仓库根目录执行：

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\xhs-vn-post" -Target (Get-Location).Path
```

安装位置必须尚不存在；如果已有普通目录，先移到 `skills` 目录之外备份，再创建链接，避免备份被当成另一份 skill 加载。其他客户端按其实际 skills 目录选择安装位置；已有入口若链接到这个安装位置，可继续复用。

`xiaohongshu-upload` 和 `xiaoheihe-article-publish` 为可选的实际发布能力，不是离线合成的运行依赖。

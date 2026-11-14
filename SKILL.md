---
name: xhs-vn-post
description: 为 if_line 视觉小说制作小红书或小黑盒图文素材：通过 JSON 配置合成背景、透明立绘与原剧本对白，整理散图，生成统一 3:4 图片、顺序预览和完整发布审核包。整页画面为可选形式，可与立绘、CG 混排；实际发布分别交给 xiaohongshu-upload 或 xiaoheihe-article-publish，并须经过用户审核。
---

# VN 图文素材与发布审核包

把已完成的素材与真实台词整理成可核对的发布包。用户 2026-09-21 指定：整页 VN 画面可以加入帖子，不强制每张都是游戏画面；裸立绘、背景、CG 可以混排。

## 准备素材

- 在 if_line 项目中，先读当前仓库 `CLAUDE.md`，以现行情景流程为创作入口；新作品制作参照当前可用的 `ifline-vn-studio`。本 skill 只读取已完成素材，不重新生成或发布作品。
- 优先使用项目导出/API 提供的真实文件，按剧本关联说话人、表情、背景。立绘使用带透明通道的原始 PNG，不拿角色预览缩略图替代。只有提示词、queued/pending 或缺文件的素材不能当作已完成。
- 台词使用原剧本句子，在配置 `source` 中记录情景/段落/素材标识或本地出处。`GET /api/path-chapters/{pcid}/script` 是仍保留的读取接口，结构以当前 API 返回为准，不假定总有 `spans`，也不恢复退役的章节生成流程。
- if_line 项目的本地开发约定：后端 `127.0.0.1:56666`，前端 `http://127.0.0.1:5175/project/{pid}`，阅读器预览 `/project/{pid}/preview`；这些服务不由本 skill 仓库提供，环境变化时以目标项目配置为准。正常开发环境验收只用测试账号 `999@qq.com`，密码从安全配置取得。
- 可以截取真实阅读器画面；脚本合成的画面须称为“合成画面”，不能仅凭合成图宣称已完成实机验收。不要把凭据或 cookie 写入配置/审核包。

## 填配置并生成

使用 Python 3.10+ 和 Pillow。在本 skill 开发目录执行 `python -m pip install -r requirements.txt` 安装依赖；如果在 if_line 仓库中调用，也可复用其 `backend/venv/Scripts/python.exe`（Linux 对应 `backend/venv/bin/python`）。不再修改 Python 的 CONFIG 段。

1. 复制 [examples/post.example.json](examples/post.example.json) 到作品工作目录，命名 `post.json`。例子中的文件路径需要替换成实际素材；工作路径与作品文案也要一起填写。
2. 按最终发布顺序填写 `images`：`scene` 合成 VN 对白画面，`image` 整理封面/CG/立绘卡。完整字段与迁移说明见 [references/config.md](references/config.md)。
3. 运行合成器；相对素材、字体、正文文件和 `output_dir` 均相对于 **配置文件所在目录**，不依赖当前 shell 工作目录。以下命令中的 `SKILL_DIR` 表示本 SKILL.md 所在目录，替换为真实路径。

```powershell
python "SKILL_DIR/scripts/compose_screens.py" --config "作品目录/post.json"
```

```bash
python3 /path/to/xhs-vn-post/scripts/compose_screens.py --config /path/to/work/post.json
```

可加 `--validate-only` 实际渲染检查而不写文件；`--output DIR` 可覆盖输出根目录，此命令行参数相对当前工作目录解析。

长对白默认 `text_overflow: "error"`：超过三行就报错。需要保留完整长句时设为 `"paginate"`，自动拆成连续多张；原文字符和顺序保存在清单中，不擅自改写或截断。分页会增加最终图片数，必须重新核对清单。

## 画面与交付检查

- **用户既定制作约定**：整帖统一 3:4、1080×1440；人物大而清晰，尤其封面。缩到 300px 宽时人物仍须突出。这是本工作流的出图约定，不表述为所有平台/所有 VN 的硬性规格。
- 背景通常 `cover` 裁切；需要保全内容的 CG/原梗封面选 `blur`（模糊铺底、原图居中 contain）；浅底立绘卡选 `solid`（同色补边），不硬拉伸。裸透明立绘用 `solid` 并指定浅色 `matte`。
- 默认说话人可见立绘高 980px、其他角色 850px，非说话方压暗 55%；缩放前去透明留白。角色位置和尺寸可在配置中调整，确保脸、名牌和对白没有误遮挡。艺术构图仍需目视检查。
- 默认底部深色半透明对话框、主题色名牌、中文正文、继续箭头及作品章节角标。字体与配色可配置；找不到中文字体就明确报错，不退回缺字字体。
- 每次运行创建独立 `out/pack-…/`，不覆盖旧包或混入旧图。交付 `images/`、`preview.jpg`、`post.json`、`manifest.json`、`发布审核单.md`。`manifest.json` 最后写入，缺少它表示产物未完成。
- 先看 `preview.jpg` 中每张 300px 缩略图，再逐张打开原图检查对白完整、图片顺序、角色与场景、裁切和透明边缘。机检不会判断画面美感或素材/剧情是否真实匹配。
- 标题/正文按本地约定检查长度和控制字符，配对引号/书名号异常会提示；话题存在性、平台实际计数及当前限制仍需在发布前核对。历史用过的话题不视为永久有效。

## 发布前用户审核（硬规则，用户 2026-09-21 指定）

**先把完整待发包交给用户：按顺序展示图片/预览、标题、正文全文、话题和目标账号；只有用户明确同意后才能执行发布。** 用户未回复、答复含糊或要求修改，停在产物阶段。修改标题、正文、话题、账号或任意图片后，重新生成审核包并提交审核。

`sau xiaohongshu upload-note` / `upload-video` 执行即发布，没有草稿缓冲。本脚本只生成本地文件，不调用上传命令，也不把机检通过当作用户批准。

- 小红书实际登录/上传：使用当前可用的 `xiaohongshu-upload` skill，先确认实际 `sau` 路径、CLI 契约和目标账号，不硬编码 `main`。上传图片按 manifest 的 `images` 数组取序，不使用目录通配符。
- 小黑盒实际发布/更新：使用 `xiaoheihe-article-publish` skill；正文末尾保留「图文由 if_line 制作」，并遵守其发布审核要求。
- 发布前可用以下命令检查包内文件是否发生变化；通过仅表示文件完整，**不表示用户已批准或已经发布**。

```bash
python compose_screens.py --verify /path/to/out/pack-xxxxxxxxxxxx
```

## 发布结果与历史经验

- 历史上无头反复访问小红书曾触发安全限制；保留“不在发布后反复无头核验”的操作约定，不把访问次数写成平台固定阈值。
- 区分“工具报告成功”“已确认平台可见”“结果不确定”。保留发布返回/日志证据，不仅凭一行成功日志宣称平台可见；结果不确定时先核实，不自动重发。
- 若确需查看页面，截图前先检查 `document.body.innerText`、URL 和页面状态，避免把错误页误判成正常内容；必要时由用户在 APP 确认。
- 不假定当前 CLI 支持编辑；以实际命令能力为准。不能编辑时，把用户 APP 修改或新帖方案交用户决定，不自动重复发布或删除旧帖。
- 若需求扩大到多平台封面/视频/宣发套装，可交给 `promo-pack`；本 skill 负责 VN 图文合成与审核交付，不复制整套多平台产线。

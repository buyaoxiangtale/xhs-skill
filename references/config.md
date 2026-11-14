# post.json 配置与迁移

只读取本地 UTF-8 JSON 和本地素材，不下载文件、不访问账号、不执行发布。Python 3.10+，依赖 Pillow（支持 `Image.Resampling` 的版本）。

## 顶层字段

| 字段 | 用途 |
| --- | --- |
| `version` | 必填，固定 `1` |
| `work_title` | 必填，作品角标，是否带书名号由这里决定 |
| `chapter_tag` | 可选，情景/章节说明；过宽时报错，不裁掉文字 |
| `font` | 可选，本地中文字体路径；省略时探测微软雅黑、黑体、Noto CJK、文泉驿或苹方，均不可用时报错 |
| `output_dir` | 默认 `out`，每次生成新的 `pack-包编号` 子目录；同内容再次运行也保留独立目录 |
| `background` | 可选，scene 的默认背景；仅有 image 项时不读取它 |
| `portraits` | 角色名到透明 PNG 路径的对象，仅加载实际引用的角色 |
| `text_overflow` | `error`（默认）或 `paginate`；后者完整分页，每张最多三行 |
| `style` | 可选，覆盖下面的默认样式 |
| `post` | 必填，发布文案与目标平台 |
| `images` | 必填，非空有序数组；scene / image 可任意混排，按此顺序出图 |

相对路径都相对于 `post.json` 所在目录。`--output DIR` 是唯一例外，它按命令行当前目录解析。不展开 shell 变量；Windows JSON 路径用 `/`，或把反斜杠写成 `\\`。未知配置字段会报错，避免拼错后悄悄用默认值。

## post

```json
{
  "platform": "xiaohongshu",
  "account": "用户实际选择的账号名",
  "title": "标题",
  "note_file": "note.txt",
  "tags": ["在平台确认过的话题"]
}
```

- `platform`：`xiaohongshu`（默认）或 `xiaoheihe`。
- `account`：可选，省略会在审核单提醒核对账号；不自动选择 `main`。
- `title`：非空单行字符串。小红书按 20 字符、小黑盒按 30 字符做本地检查，实际编辑器计数可能不同。
- `note` / `note_file`：必须且只能提供一个。`note` 为正文全文，`note_file` 为 UTF-8 文本文件；生成的包一律存入完整 `note`，不会依赖包外正文文件。小红书按 1000 字符做本地检查。
- `tags`：字符串数组，默认空。这里只校验类型，不声称已确认平台话题存在。
- 不含控制字符；正文允许 `\n` 换行。中文引号、书名号数量不配对会提示人工核对。小黑盒缺少末尾署名「图文由 if_line 制作」会提示，发布前必须补齐并重审。

## scene：背景 + 立绘 + 原台词

```json
{
  "kind": "scene",
  "background": "assets/room.png",
  "background_mode": "cover",
  "speaker": "小夏",
  "text": "从真实剧本逐字复制的台词。",
  "sprites": [
    {"name": "小夏", "x": 120, "y_offset": 0, "height": 1080}
  ],
  "source": {"scene_id": "实际情景ID", "paragraph_id": "实际段落ID"}
}
```

`background` 可省略以使用顶层默认值；每张都有专用背景时也不需要全局背景。`background_mode` 支持 `cover`（默认）、`blur`、`solid`。

`speaker` 默认“旁白”；旁白不绘制名牌，省略 `sprites` 就不挂立绘。有角色留场需求时显式填写。`sprites` 顺序就是前后叠放顺序。

每个 sprite 的 `name` 必须存在于顶层 `portraits`；`x` 是去透明留白并缩放后左边缘位置，省略即水平居中；`y_offset` 为贴底偏移，正值向下。`height` 默认取说话/非说话人的样式高度。`speaking` 可显式设置布尔值，否则由角色名是否等于 `speaker` 推断。

透明边缘不会因压暗而变得更不透明。人物突出、脸是否被裁、表情是否对应台词，仍需看图验收。

长对白用 `paginate` 时，同一 scene 会变成多张，人物与背景保持一致。manifest 每张记录 `page` / `pages`、本页 `text` 和完整 `source_text`；按顺序拼接本页 `text` 可恢复完整原句，包括原有换行。不会加省略号或改写台词。

## image：散图或真实截图

```json
{
  "kind": "image",
  "path": "assets/character-card.png",
  "fit": "solid",
  "matte": "#f6f3ef",
  "source": "导出的原始角色卡"
}
```

| fit | 用途 |
| --- | --- |
| `blur`（默认） | 原图完整居中，模糊放大铺底；适合 CG / 原梗封面 |
| `solid` | 原图完整居中，同色补边；适合浅底立绘卡、透明立绘 |
| `cover` | 铺满并居中裁切；只在允许裁掉边缘时使用 |

`matte` 可指定颜色。未指定时，不透明图片用四角中位色补边；四角带透明的图片用浅色底。透明 PNG 先与底色正确合成，再导出 RGB，避免直接去 alpha 产生黑底。

`source` 在两种图片项中都支持字符串或 JSON 对象。记录真实来源，不放密码、token 或有凭据的 URL。脚本保留来源信息但不会替你验证业务归属或剧情真伪。

## style 默认值

```json
{
  "text_size": 38,
  "name_size": 40,
  "tag_size": 27,
  "speaker_height": 980,
  "other_height": 850,
  "dim_factor": 0.55,
  "box_color": "#0a0e18bc",
  "name_colors": {"小夏": "#7058a8e8"}
}
```

字体大小范围 16–72；人物高度 100–2880。`dim_factor` 是覆盖的黑度，`0.55` 表示亮度保留约 45%，alpha 不变。对话框会随正文大小调整高度；人物高度按去透明边后的实际内容计算，旧坐标可能需要重排。

## 交付与核验

每个新包包含：

- `images/01.png`…：按最终发布顺序编号，包括展开后的分页。
- `preview.jpg`：每张 300×400 缩略图及序号，便于检查整帖节奏。
- `post.json`：完整标题、正文、话题、平台及可选账号。
- `发布审核单.md`：顺序图片链接、预览、全文文案、警告和审核要求。
- `manifest.json`：来源、分页文本、图片顺序、文件 SHA-256 和 `awaiting_user_review` 状态。最后写入，作为完整包标记。

`--verify PACKAGE_DIR` 检查文件缺失、变动、清单外文件及文案/图片清单一致性。它不证明内容质量、平台可见性或用户已批准；发布审批仍按 SKILL.md 执行。失败/中断且没有 manifest 的目录不能交付。修改产物时应改原始配置并重新生成，不手改审核包。

## 从旧脚本迁移

旧 `WORK_TITLE / CHAPTER_TAG / FONT / OUT_DIR` → `work_title / chapter_tag / font / output_dir`。
旧 `BG_PATH / SPRITES / NAME_COLORS` → `background / portraits / style.name_colors`。
旧 `SCENES` → `images` 中 `kind: "scene"` 的项；旧 `PAD_TO_34` → `kind: "image"` 的项，`fit: "blur"`。旧元组立绘改为具名字段。

不再使用 Python CONFIG 段或自填输出文件名；通过单个 `images` 数组确定混排顺序。命令需传 `--config`，不给配置会显示帮助并退出，不沿用示例作品。

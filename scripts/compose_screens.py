#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a local VN review package from JSON. Requires Pillow; never publishes."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import statistics
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1440
RESAMPLE = Image.Resampling.LANCZOS
STYLE = {
    "text_size": 38, "name_size": 40, "tag_size": 27,
    "speaker_height": 980, "other_height": 850, "dim_factor": 0.55,
    "box_color": "#0a0e18bc", "name_colors": {},
}


class ConfigError(ValueError):
    pass


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def object_id(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8"))


def text_value(value, label, *, empty=False, multiline=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ConfigError(f"{label} 必须是{'可为空的' if empty else '非空'}字符串")
    if any(unicodedata.category(c) == "Cc" and not (multiline and c == "\n") for c in value):
        raise ConfigError(f"{label} 含控制字符或不允许的换行")
    return value


def fields(value, allowed, label):
    if not isinstance(value, dict):
        raise ConfigError(f"{label} 必须是对象")
    unknown = set(value) - set(allowed)
    if unknown:
        raise ConfigError(f"{label} 不支持字段：{', '.join(sorted(unknown))}")


def number(value, label, low, high, *, integer=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigError(f"{label} 必须是有限数值")
    if integer and not isinstance(value, int):
        raise ConfigError(f"{label} 必须是整数")
    if not low <= value <= high:
        raise ConfigError(f"{label} 必须在 {low}–{high} 之间")
    return value


def color(value, label):
    try:
        return ImageColor.getcolor(value, "RGBA")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ConfigError(f"{label} 不是有效颜色：{value}") from exc


def local_path(base, value, label):
    text_value(value, label)
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def find_font(base, specified):
    if specified is not None:
        candidates = [local_path(base, specified, "font")]
    else:
        candidates = [Path(p) for p in (
            "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        )]
    for path in candidates:
        if path.is_file():
            try:
                ImageFont.truetype(str(path), 38)
                return str(path)
            except OSError:
                continue
    raise ConfigError("未找到可用中文字体；请在 font 中指定本机中文 TTF/TTC/OTF 文件")


def read_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    fields(config, {"version", "work_title", "chapter_tag", "font", "output_dir",
                    "background", "portraits", "style", "text_overflow", "post", "images"}, "配置")
    if type(config.get("version")) is not int or config["version"] != 1:
        raise ConfigError("version 必须为 1")
    text_value(config.get("work_title"), "work_title")
    text_value(config.get("chapter_tag", ""), "chapter_tag", empty=True)
    if config.get("text_overflow", "error") not in {"error", "paginate"}:
        raise ConfigError("text_overflow 仅支持 error / paginate")
    images = config.get("images")
    if not isinstance(images, list) or not images:
        raise ConfigError("images 必须是按发布顺序排列的非空数组")
    portraits = config.get("portraits", {})
    if not isinstance(portraits, dict):
        raise ConfigError("portraits 必须是角色名到本地 PNG 路径的对象")
    for name, image_path in portraits.items():
        text_value(name, "portraits 角色名")
        local_path(path.parent, image_path, f"portraits.{name}")
    overrides = config.get("style", {})
    fields(overrides, STYLE, "style")
    style = {**STYLE, **overrides}
    for key in ("text_size", "name_size", "tag_size"):
        number(style[key], f"style.{key}", 16, 72)
    for key in ("speaker_height", "other_height"):
        number(style[key], f"style.{key}", 100, H * 2)
    number(style["dim_factor"], "style.dim_factor", 0, 1, integer=False)
    color(style["box_color"], "style.box_color")
    if not isinstance(style["name_colors"], dict):
        raise ConfigError("style.name_colors 必须是对象")
    for name, value in style["name_colors"].items():
        color(value, f"style.name_colors.{name}")
    return path, config, style


def read_post(config, base, warnings):
    post = dict(config.get("post", {})) if isinstance(config.get("post"), dict) else None
    fields(post, {"platform", "account", "title", "note", "note_file", "tags"}, "post")
    platform = post.get("platform", "xiaohongshu")
    if platform not in {"xiaohongshu", "xiaoheihe"}:
        raise ConfigError("post.platform 仅支持 xiaohongshu / xiaoheihe")
    if ("note" in post) == ("note_file" in post):
        raise ConfigError("post.note 与 post.note_file 必须且只能填写一个")
    if "note_file" in post:
        post["note"] = local_path(base, post.pop("note_file"), "post.note_file").read_text(encoding="utf-8-sig")
    title = text_value(post.get("title"), "post.title")
    note = text_value(post.get("note"), "post.note", multiline=True)
    title_limit = 20 if platform == "xiaohongshu" else 30
    if len(title) > title_limit or (platform == "xiaohongshu" and len(note) > 1000):
        raise ConfigError(f"文案超过本地检查上限：标题 {len(title)}/{title_limit}，正文 {len(note)}"
                          + ("/1000" if platform == "xiaohongshu" else ""))
    tags = post.get("tags", [])
    if not isinstance(tags, list):
        raise ConfigError("post.tags 必须是字符串数组")
    for tag in tags:
        text_value(tag, "post.tags 条目")
    if "account" in post:
        text_value(post["account"], "post.account")
    for left, right in (("“", "”"), ("‘", "’"), ("《", "》"), ("「", "」"), ("『", "』")):
        if (title + note).count(left) != (title + note).count(right):
            warnings.append(f"文案中的 {left}{right} 数量不配对，请人工确认。")
    if platform == "xiaoheihe" and not note.rstrip().endswith("图文由 if_line 制作"):
        warnings.append("小黑盒正文末尾缺少「图文由 if_line 制作」署名；提交发布前必须补齐并重审。")
    warnings.append("话题存在性及平台实际计数口径未联网核验；提交发布前人工确认。")
    return {**post, "platform": platform, "tags": tags}


def open_rgba(path):
    with Image.open(path) as original:
        return ImageOps.exif_transpose(original).convert("RGBA")


def flatten(image, matte):
    background = Image.new("RGBA", image.size, matte[:3] + (255,))
    return Image.alpha_composite(background, image).convert("RGB")


def fit_image(path, mode="cover", matte=None):
    rgba = open_rgba(path)
    if matte is None:
        # Use an opaque card's corner colour; transparent cutouts get a light matte.
        corners = [rgba.getpixel(p) for p in ((0, 0), (rgba.width - 1, 0),
                   (0, rgba.height - 1), (rgba.width - 1, rgba.height - 1))]
        matte = (tuple(int(statistics.median(p[c] for p in corners)) for c in range(3)) + (255,)
                 if all(p[3] == 255 for p in corners) else (246, 243, 239, 255))
    rgb = flatten(rgba, matte)
    if mode == "cover":
        return ImageOps.fit(rgb, (W, H), method=RESAMPLE)
    foreground = ImageOps.contain(rgb, (W, H), method=RESAMPLE)
    background = (ImageOps.fit(rgb, (W, H), method=RESAMPLE).filter(ImageFilter.GaussianBlur(28))
                  if mode == "blur" else Image.new("RGB", (W, H), matte[:3]))
    background.paste(foreground, ((W - foreground.width) // 2, (H - foreground.height) // 2))
    return background


def wrap_lines(text, font, max_width):
    """Return (display, start, end) slices; explicit newlines stay in source spans."""
    lines, current, start = [], "", 0
    for index, char in enumerate(text):
        if char == "\n":
            lines.append((current, start, index + 1))
            current, start = "", index + 1
        elif current and font.getlength(current + char) > max_width:
            lines.append((current, start, index))
            current, start = char, index
        else:
            current += char
    if current or not lines:
        lines.append((current, start, len(text)))
    return lines


def scene_frames(item, config, base, style, font_path, input_index, warnings):
    text = text_value(item.get("text"), f"images[{input_index}].text", multiline=True)
    speaker = text_value(item.get("speaker", "旁白"), "speaker")
    font = ImageFont.truetype(font_path, style["text_size"])
    name_font = ImageFont.truetype(font_path, style["name_size"])
    tag_font = ImageFont.truetype(font_path, style["tag_size"])
    lines = wrap_lines(text, font, W - 108)
    if len(lines) > 3 and config.get("text_overflow", "error") == "error":
        raise ConfigError(f"images[{input_index}] 台词需 {len(lines)} 行，超过 3 行；"
                          "请选更短原句或设置 text_overflow=paginate，禁止静默截断")
    background = item.get("background", config.get("background"))
    if not background:
        raise ConfigError(f"images[{input_index}] 缺 background（可在顶层设置默认背景）")
    bg_path = local_path(base, background, "background")
    mode = item.get("background_mode", "cover")
    if mode not in {"cover", "blur", "solid"}:
        raise ConfigError("background_mode 仅支持 cover / blur / solid")
    canvas = fit_image(bg_path, mode).convert("RGBA")
    inputs = [str(bg_path)]
    sprites = item.get("sprites", [])
    if not isinstance(sprites, list):
        raise ConfigError("sprites 必须是数组")
    for sprite in sprites:
        fields(sprite, {"name", "x", "y_offset", "height", "speaking"}, "sprite")
        name = text_value(sprite.get("name"), "sprite.name")
        if name not in config.get("portraits", {}):
            raise ConfigError(f"portraits 中缺少角色：{name}")
        path = local_path(base, config["portraits"][name], f"portraits.{name}")
        portrait = open_rgba(path)
        alpha = portrait.getchannel("A")
        bbox = alpha.getbbox()
        if bbox is None:
            raise ConfigError(f"立绘完全透明：{name}")
        if alpha.getextrema()[0] == 255:
            warnings.append(f"立绘「{name}」没有透明像素，请确认使用了原始透明 PNG。")
        portrait = portrait.crop(bbox)
        speaking = sprite.get("speaking", speaker == name)
        if not isinstance(speaking, bool):
            raise ConfigError("sprite.speaking 必须是布尔值")
        height = number(sprite.get("height", style["speaker_height"] if speaking else style["other_height"]),
                        "sprite.height", 100, H * 2)
        portrait = portrait.resize((max(1, round(portrait.width * height / portrait.height)), height), RESAMPLE)
        if not speaking:
            # Adjust RGB only: translucent edges must retain their original alpha.
            original_alpha = portrait.getchannel("A")
            portrait = ImageEnhance.Brightness(portrait).enhance(1 - style["dim_factor"])
            portrait.putalpha(original_alpha)
        x = number(sprite.get("x", (W - portrait.width) // 2), "sprite.x", -W * 4, W * 4)
        dy = number(sprite.get("y_offset", 0), "sprite.y_offset", -H * 2, H * 2)
        canvas.alpha_composite(portrait, (x, H - height + dy))
        inputs.append(str(path))
    tag = " ".join(filter(None, [config["work_title"], config.get("chapter_tag", "")]))
    if tag_font.getlength(tag) > W - 70:
        raise ConfigError("作品/章节角标过长；请缩短 chapter_tag 或减小 style.tag_size")
    if speaker != "旁白" and name_font.getlength(speaker) > W - 150:
        raise ConfigError("说话人名牌过宽；请减小 style.name_size")
    frames = []
    page_groups = [lines[i:i + 3] for i in range(0, len(lines), 3)]
    line_height = math.ceil(style["text_size"] * 1.42)
    box_height = max(240, line_height * 3 + 78)
    box_y = H - 28 - box_height
    for page, group in enumerate(page_groups, 1):
        image = canvas.copy()
        overlay = Image.new("RGBA", (W, H))
        draw = ImageDraw.Draw(overlay)
        draw.rounded_rectangle((24, box_y, W - 24, H - 28), radius=20,
                               fill=color(style["box_color"], "box_color"), outline=(255, 255, 255, 60), width=2)
        if speaker != "旁白":
            plate_height = style["name_size"] + 20
            plate_width = math.ceil(name_font.getlength(speaker)) + 52
            plate_color = color(style["name_colors"].get(speaker, "#78828fe8"), "name_colors")
            draw.rounded_rectangle((48, box_y - plate_height + 36, 48 + plate_width, box_y + 36),
                                   radius=12, fill=plate_color)
            draw.text((74, box_y - plate_height + 43), speaker, font=name_font, fill="white")
        for offset, (line, _, _) in enumerate(group):
            draw.text((60, box_y + 48 + line_height * offset), line, font=font, fill=(244, 246, 250, 255))
        draw.polygon(((W - 104, H - 60), (W - 70, H - 60), (W - 87, H - 40)), fill=(255, 255, 255, 215))
        draw.rounded_rectangle((18, 16, 52 + math.ceil(tag_font.getlength(tag)), style["tag_size"] + 37),
                               radius=11, fill=(10, 14, 24, 132))
        draw.text((35, 24), tag, font=tag_font, fill=(255, 255, 255, 222))
        frames.append((Image.alpha_composite(image, overlay).convert("RGB"), {
            "kind": "composite", "input_index": input_index, "speaker": speaker,
            "text": text[group[0][1]:group[-1][2]], "source_text": text,
            "page": page, "pages": len(page_groups), "inputs": inputs,
            "source": item.get("source", {}),
        }))
    return frames


def render_all(config, base, style, font_path, warnings):
    frames = []
    for index, item in enumerate(config["images"], 1):
        fields(item, {"kind", "path", "fit", "matte", "background", "background_mode",
                      "speaker", "text", "sprites", "source"}, f"images[{index}]")
        kind = item.get("kind")
        if "source" in item and not isinstance(item["source"], (dict, str)):
            raise ConfigError(f"images[{index}].source 必须是对象或字符串")
        if not item.get("source"):
            warnings.append(f"第 {index} 项未填写 source；请人工核对素材/台词出处。")
        if kind == "scene":
            fields(item, {"kind", "background", "background_mode", "speaker", "text", "sprites", "source"},
                   f"images[{index}] scene")
            frames.extend(scene_frames(item, config, base, style, font_path, index, warnings))
        elif kind == "image":
            fields(item, {"kind", "path", "fit", "matte", "source"}, f"images[{index}] image")
            path = local_path(base, item.get("path"), f"images[{index}].path")
            mode = item.get("fit", "blur")
            if mode not in {"cover", "blur", "solid"}:
                raise ConfigError("image.fit 仅支持 cover / blur / solid")
            matte = color(item["matte"], "image.matte") if "matte" in item else None
            frames.append((fit_image(path, mode, matte), {
                "kind": "image", "input_index": index, "fit": mode,
                "inputs": [str(path)], "source": item.get("source", {}),
            }))
        else:
            raise ConfigError(f"images[{index}].kind 仅支持 scene / image")
    return frames


def encoded_image(image, format):
    buffer = io.BytesIO()
    image.save(buffer, format, **({"quality": 92} if format == "JPEG" else {}))
    return buffer.getvalue()


def preview_image(frames, font_path):
    columns = min(3, len(frames))
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (columns * 324 + 24, rows * 454 + 24), "#f0ede8")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(font_path, 19)
    for index, (image, meta) in enumerate(frames):
        x, y = 24 + (index % columns) * 324, 24 + (index // columns) * 454
        sheet.paste(image.resize((300, 400), RESAMPLE), (x, y))
        label = f"{index + 1:02d} · " + ("合成画面" if meta["kind"] == "composite" else "素材整理")
        if meta.get("pages", 1) > 1:
            label += f" {meta['page']}/{meta['pages']}"
        draw.text((x, y + 411), label, font=font, fill="#323742")
    return sheet


def review_markdown(post, records, warnings, bundle_id):
    fence = "`" * max(3, max((len(part) for part in re.findall(r"`+", post["note"])), default=0) + 1)
    lines = ["# 发布前审核包", "", "人话摘要：请按下列顺序核对图片与完整文案。当前包仅供审核，尚未发布，需用户明确同意后才能交给发布工具。", "",
             f"包编号：`{bundle_id}`", "", f"平台：{post['platform']}", "",
             f"账号：{post.get('account', '未指定；发布前核对实际账号')}", "",
             "![300px 顺序预览](preview.jpg)", "", "## 图片顺序", ""]
    for item in records:
        label = "合成画面（非实机截图）" if item["kind"] == "composite" else "素材整理"
        lines.append(f"{item['order']}. [{item['path']}]({item['path']}) · {label}")
    lines += ["", "## 标题", "", post["title"], "", "## 正文全文", "", fence + "text", post["note"], fence,
              "", "## 话题", "", json.dumps(post["tags"], ensure_ascii=False), "", "## 核对事项", ""]
    lines += [f"- {message}" for message in warnings]
    lines += ["- 以 300px 缩略图检查人物是否突出，再打开原图检查脸、名牌、对白和裁切。",
              "- 按 manifest.json 的 images 顺序上传；分页会增加图片数量，请确认最终清单。",
              "- 标题、正文、话题、账号或图片有变动，须重新生成审核包并重新审核。",
              "- 用户未回复、回复含糊或要求修改时，停在审核阶段。", ""]
    return "\n".join(lines).encode("utf-8")


def compose(config_path, *, output=None, validate_only=False):
    config_path, config, style = read_config(config_path)
    warnings = []
    base = config_path.parent
    font_path = find_font(base, config.get("font"))
    post = read_post(config, base, warnings)
    frames = render_all(config, base, style, font_path, warnings)
    warnings = list(dict.fromkeys(warnings))
    artifacts, records = {}, []
    for index, (image, meta) in enumerate(frames, 1):
        name = f"images/{index:02d}.png"
        data = encoded_image(image, "PNG")
        artifacts[name] = data
        records.append({"order": index, "path": name, "sha256": sha256(data), **meta})
    payload = {"schema_version": 1, "canvas": [W, H], "post": post, "images": records}
    bundle_id = object_id(payload)
    if validate_only:
        return {"image_count": len(records), "warnings": warnings, "bundle_id": bundle_id}
    artifacts["post.json"] = json_bytes(post)
    artifacts["preview.jpg"] = encoded_image(preview_image(frames, font_path), "JPEG")
    artifacts["发布审核单.md"] = review_markdown(post, records, warnings, bundle_id)
    manifest = {**payload, "bundle_id": bundle_id, "status": "awaiting_user_review",
                "warnings": warnings, "files": {name: sha256(data) for name, data in artifacts.items()}}
    # Finish all validation/rendering before creating an output directory.
    root = Path(output).resolve() if output is not None else local_path(base, config.get("output_dir", "out"), "output_dir")
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"pack-{bundle_id[:12]}"
    suffix = 1
    while True:
        try:
            destination.mkdir()
            break
        except FileExistsError:
            suffix += 1
            destination = root / f"pack-{bundle_id[:12]}-{suffix}"
    for name, data in artifacts.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    # Manifest is the completion marker, written last.
    (destination / "manifest.json").write_bytes(json_bytes(manifest))
    return {"package": str(destination), "image_count": len(records),
            "warnings": warnings, "bundle_id": bundle_id}


def verify_package(directory):
    root = Path(directory).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    payload = {key: manifest[key] for key in ("schema_version", "canvas", "post", "images")}
    if object_id(payload) != manifest["bundle_id"]:
        raise ConfigError("manifest 内容与包编号不一致")
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha256(path.read_bytes()) != expected:
            raise ConfigError(f"审核包文件缺失或已修改：{name}")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]) | {"manifest.json"}:
        raise ConfigError("审核包出现清单外文件；请重新生成，避免混入旧图")
    if json.loads((root / "post.json").read_text(encoding="utf-8")) != manifest["post"]:
        raise ConfigError("post.json 与 manifest 中的发布文案不一致")
    for item in manifest["images"]:
        if manifest["files"].get(item["path"]) != item["sha256"]:
            raise ConfigError(f"图片校验信息不一致：{item['path']}")
    return {"package": str(root), "image_count": len(manifest["images"]),
            "status": "files_verified_user_approval_still_required"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", type=Path, help="UTF-8 post.json；素材相对配置文件解析")
    group.add_argument("--verify", type=Path, help="核对已生成包的内容和顺序，不代表用户批准")
    parser.add_argument("--output", type=Path, help="覆盖 output_dir；相对当前工作目录解析")
    parser.add_argument("--validate-only", action="store_true", help="实际渲染校验，但不写产物")
    args = parser.parse_args(argv)
    if args.verify and (args.output or args.validate_only):
        parser.error("--verify 不与 --output / --validate-only 同用")
    try:
        result = (verify_package(args.verify) if args.verify else
                  compose(args.config, output=args.output, validate_only=args.validate_only))
    except (ConfigError, OSError, ValueError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

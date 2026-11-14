"""Offline behavioural regression tests. Run with Python + Pillow; no account/network."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_screens as composer


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="xhs-vn-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "素材"
        self.assets.mkdir()
        Image.new("RGB", (180, 240), "white").save(self.assets / "背景.png")
        Image.new("RGB", (200, 300), "#ecdfcd").save(self.assets / "卡片.png")
        portrait = Image.new("RGBA", (400, 600))
        ImageDraw.Draw(portrait).rectangle((100, 50, 299, 549), fill=(255, 0, 0, 255))
        portrait.save(self.assets / "立绘.png")
        self.config = {
            "version": 1, "work_title": "《本地验收》", "chapter_tag": "对白测试",
            "output_dir": "交付", "portraits": {"小夏": "素材/立绘.png"},
            "post": {"title": "仅用于离线验证", "note": "这是测试包，不用于发布。", "tags": []},
            "images": [self.image_item()],
        }

    def image_item(self, **values):
        return {"kind": "image", "path": "素材/卡片.png", "fit": "solid", "source": "本地测试素材", **values}

    def scene(self, **values):
        return {"kind": "scene", "background": "素材/背景.png", "speaker": "小夏",
                "text": "这句话必须完整保留。", "sprites": [{"name": "小夏"}],
                "source": {"scene_id": "test-scene", "paragraph_id": "test-paragraph"}, **values}

    def write(self):
        path = self.root / "post.json"
        path.write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")
        return path

    def build(self, **kwargs):
        result = composer.compose(self.write(), **kwargs)
        package = Path(result["package"])
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        return package, manifest

    def test_image_only_creates_new_directory_without_background(self):
        self.config["background"] = "不存在的全局背景.png"
        package, manifest = self.build()
        self.assertEqual(manifest["canvas"], [1080, 1440])
        with Image.open(package / "images/01.png") as image:
            self.assertEqual(image.size, (1080, 1440))
        self.assertEqual(manifest["status"], "awaiting_user_review")
        self.assertTrue((package / "preview.jpg").is_file())
        self.assertIn("这是测试包，不用于发布。", (package / "发布审核单.md").read_text(encoding="utf-8"))
        composer.verify_package(package)

    def test_each_scene_can_supply_its_own_background(self):
        self.config["images"] = [self.scene()]
        _, manifest = self.build()
        self.assertEqual(manifest["images"][0]["kind"], "composite")

    def test_long_text_fails_before_any_output_is_written(self):
        self.config["images"] = [self.scene(text="原剧本长对白。" * 45)]
        with self.assertRaisesRegex(composer.ConfigError, "禁止静默截断"):
            composer.compose(self.write())
        self.assertFalse((self.root / "交付").exists())

    def test_pagination_preserves_every_character_including_newlines(self):
        text = "第一句原文。\n\n" + "完整的原剧本对白，不能被截断。" * 14 + "\n"
        self.config["text_overflow"] = "paginate"
        self.config["images"] = [self.scene(text=text)]
        _, manifest = self.build()
        records = manifest["images"]
        self.assertGreater(len(records), 1)
        self.assertEqual("".join(item["text"] for item in records), text)
        self.assertTrue(all(item["source_text"] == text for item in records))
        self.assertEqual([item["page"] for item in records], list(range(1, len(records) + 1)))
        self.assertTrue(all(item["source"]["paragraph_id"] == "test-paragraph" for item in records))

    def test_mixed_images_keep_explicit_publication_order(self):
        self.config["images"] = [self.image_item(source="封面"), self.scene(), self.image_item(source="尾图")]
        _, manifest = self.build()
        self.assertEqual([item["kind"] for item in manifest["images"]], ["image", "composite", "image"])
        self.assertEqual([item["path"] for item in manifest["images"]], ["images/01.png", "images/02.png", "images/03.png"])
        self.assertEqual(manifest["images"][0]["source"], "封面")
        self.assertEqual(manifest["images"][-1]["source"], "尾图")

    def test_paginated_render_draws_all_dialogue_in_order(self):
        text = "原句包含标点和换行。\n" + "接下来的内容同样必须真正绘制出来。" * 15
        self.config["text_overflow"] = "paginate"
        self.config["images"] = [self.scene(text=text)]
        drawn = []
        original_text = ImageDraw.ImageDraw.text

        def record(draw, xy, value, *args, **kwargs):
            if xy[0] == 60:
                drawn.append(value)
            return original_text(draw, xy, value, *args, **kwargs)

        with patch.object(ImageDraw.ImageDraw, "text", record):
            self.build()
        self.assertEqual("".join(drawn), text.replace("\n", ""))

    def test_solid_padding_infers_card_colour_without_stretch(self):
        result = composer.fit_image(self.assets / "卡片.png", "solid")
        self.assertEqual(result.getpixel((0, 720)), (236, 223, 205))
        self.assertEqual(result.size, (1080, 1440))

    def test_transparent_cutout_is_flattened_on_light_matte(self):
        for mode in ("solid", "blur"):
            with self.subTest(mode=mode):
                result = composer.fit_image(self.assets / "立绘.png", mode, (240, 230, 220, 255))
                self.assertEqual(result.getpixel((0, 0)), (240, 230, 220))
                self.assertEqual(result.getpixel((540, 720)), (255, 0, 0))

    def test_portrait_height_uses_visible_pixels_after_alpha_trim(self):
        self.config["images"] = [self.scene()]
        package, _ = self.build()
        with Image.open(package / "images/01.png") as image:
            # Visible portrait starts at 1440 - 980, despite 50px source padding.
            self.assertEqual(image.getpixel((540, 470)), (255, 0, 0))
            self.assertEqual(image.getpixel((540, 450)), (255, 255, 255))

    def test_dimming_retains_semitransparent_alpha(self):
        portrait = Image.new("RGBA", (200, 500), (255, 0, 0, 128))
        portrait.save(self.assets / "立绘.png")
        self.config["images"] = [self.scene(speaker="另一人")]
        package, _ = self.build()
        expected = Image.alpha_composite(Image.new("RGBA", (1, 1), "white"),
                                        Image.new("RGBA", (1, 1), (114, 0, 0, 128))).convert("RGB").getpixel((0, 0))
        with Image.open(package / "images/01.png") as image:
            actual = image.getpixel((540, 900))
        self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(actual, expected)), (actual, expected))

    def test_note_file_and_assets_resolve_from_config_even_in_other_cwd(self):
        del self.config["post"]["note"]
        self.config["post"]["note_file"] = "正文.txt"
        note = "完整正文第一行。\n第二行也应保留。"
        (self.root / "正文.txt").write_text(note, encoding="utf-8-sig")
        process = subprocess.run([sys.executable, "-B", str(Path(composer.__file__).resolve()), "--config", str(self.write())],
                                 cwd=self.assets, capture_output=True, encoding="utf-8", errors="replace",
                                 env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(process.returncode, 0, process.stderr)
        package = Path(json.loads(process.stdout)["package"])
        self.assertEqual(json.loads((package / "post.json").read_text(encoding="utf-8"))["note"], note)

    def test_rebuild_never_overwrites_existing_package(self):
        first, _ = self.build()
        (first / "用户保留文件.txt").write_text("keep", encoding="utf-8")
        second, _ = self.build()
        self.assertNotEqual(first, second)
        self.assertEqual((first / "用户保留文件.txt").read_text(encoding="utf-8"), "keep")
        self.assertFalse((second / "用户保留文件.txt").exists())

    def test_verify_detects_modified_text_and_extra_images(self):
        for damage in ("text", "extra", "image", "missing"):
            with self.subTest(damage=damage):
                package, _ = self.build()
                if damage == "text":
                    (package / "post.json").write_text("{}", encoding="utf-8")
                elif damage == "extra":
                    (package / "images/old.png").write_bytes(b"old")
                elif damage == "image":
                    (package / "images/01.png").write_bytes(b"edited")
                else:
                    (package / "preview.jpg").unlink()
                with self.assertRaises(composer.ConfigError):
                    composer.verify_package(package)

    def test_invalid_config_and_metadata_fail_without_output(self):
        original = copy.deepcopy(self.config)
        mutations = [
            lambda c: c.update(unknown_field=True),
            lambda c: c.update(text_overflow="truncate"),
            lambda c: c["post"].update(title="长" * 21),
            lambda c: c["post"].update(note="含\x00控制字符"),
            lambda c: c["post"].update(note_file="正文.txt"),
            lambda c: c["images"][0].update(fit="stretch"),
        ]
        for mutate in mutations:
            self.config = copy.deepcopy(original)
            mutate(self.config)
            with self.subTest(config=self.config), self.assertRaises(composer.ConfigError):
                composer.compose(self.write())
        self.assertFalse((self.root / "交付").exists())

    def test_missing_font_fails_explicitly(self):
        self.config["font"] = "missing-font.ttf"
        with self.assertRaisesRegex(composer.ConfigError, "中文字体"):
            composer.compose(self.write())

    def test_empty_portrait_and_missing_asset_fail(self):
        Image.new("RGBA", (100, 100)).save(self.assets / "立绘.png")
        self.config["images"] = [self.scene()]
        with self.assertRaisesRegex(composer.ConfigError, "完全透明"):
            composer.compose(self.write())
        self.config["images"] = [self.image_item(path="missing.png")]
        with self.assertRaises(OSError):
            composer.compose(self.write())

    def test_long_tag_fails_instead_of_clipping(self):
        self.config["chapter_tag"] = "过长角标" * 30
        self.config["images"] = [self.scene()]
        with self.assertRaisesRegex(composer.ConfigError, "角标过长"):
            composer.compose(self.write())

    def test_validate_only_does_not_write_outputs(self):
        result = composer.compose(self.write(), validate_only=True)
        self.assertEqual(result["image_count"], 1)
        self.assertFalse((self.root / "交付").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

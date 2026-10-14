"""Check mixed Chinese/Latin labels and standalone SVG output."""

from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import visuals


class VisualsTests(unittest.TestCase):
    def test_cjk_truncation_counts_display_columns(self):
        self.assertEqual(visuals._display_width("GitHub 主页"), 11)
        self.assertEqual(visuals._short("中文Python工具", 11), "中文Python…")
        self.assertEqual(visuals._short("中文", 4), "中文")
        self.assertEqual(visuals._display_width("e\u0301中文"), 5)

    def test_mixed_text_wraps_without_losing_content(self):
        value = "GitHub 个人主页与 Python 自动化工具"
        lines = visuals._wrap(value, 12, maximum=20)
        self.assertTrue(all(visuals._display_width(line) <= 12 for line in lines))
        self.assertEqual("".join(lines).replace(" ", ""), value.replace(" ", ""))
        self.assertIn("GitHub", lines[0])
        limited = visuals._wrap("中文技术生态与工具链" * 3, 10, maximum=2)
        self.assertEqual(len(limited), 2)
        self.assertTrue(limited[-1].endswith("…"))
        self.assertTrue(all(visuals._display_width(line) <= 10 for line in limited))

    def test_heading_rule_clears_chinese_text(self):
        element = ET.fromstring(visuals.heading("system info"))
        ns = {"s": "http://www.w3.org/2000/svg"}
        title = element.find("s:text", ns)
        rule = element.find("s:line", ns)
        self.assertEqual(title.text, "系统信息")
        self.assertGreater(float(rule.get("x1")), 4 * 16)
        self.assertIn("Microsoft YaHei", title.get("font-family"))

    def test_all_sections_remain_valid_xml_with_chinese_and_symbols(self):
        config = {
            "username": "corerce", "display_name": "corerce", "tagline": "Build with curiosity",
            "info": [{"label": "方向<&", "value": "Python 与中文工具链 <安全>"}],
            "ecosystem": [{"label": "开发工具", "items": ["GitHub", "Python", "自动化"]}],
            "timeline": [{"date": "NEXT", "title": "新的里程碑", "detail": "继续构建与学习"}],
        }
        snapshot = {"available": False, "profile": {}, "languages": {}, "updated_at": None}
        images = [visuals.heading("projects"), visuals.hero(config), visuals.portrait(config),
                  visuals.system_info(config, snapshot), visuals.ecosystem(config),
                  visuals.timeline(config), visuals.language_stats(snapshot)]
        for image in images:
            with self.subTest(label=ET.fromstring(image).get("aria-label")):
                self.assertNotIn("<script", image)
                self.assertNotIn("<foreignObject", image)
        self.assertIn("未同步", images[3])
        self.assertIn("暂无语言数据", images[6])
        self.assertIn("下一站", images[5])
        self.assertIn('class="rule pulse"', images[5])
        # ASCII art inherits the original monospace family, without the CJK override.
        hero_root = ET.fromstring(images[1])
        ns = {"s": "http://www.w3.org/2000/svg"}
        ascii_rows = [text for text in hero_root.findall(".//s:text", ns)
                      if text.get("{http://www.w3.org/XML/1998/namespace}space") == "preserve"]
        self.assertEqual(len(ascii_rows), 7)
        self.assertTrue(all(text.get("font-family") is None for text in ascii_rows))

    def test_language_scope_and_percentage_note_are_chinese(self):
        snapshot = {"available": True, "languages": {"Python": 123, "TypeScript": 246},
                    "scope": "public non-fork non-archived repositories, excluding profile repo"}
        image = visuals.language_stats(snapshot)
        ET.fromstring(image)
        self.assertIn("公开、非 Fork、未归档仓库，不含个人主页仓库", image)
        self.assertIn("占比不代表熟练度", image)
        self.assertIn("Python", image)

    def test_six_ecosystem_nodes_do_not_restore_removed_placeholders(self):
        labels = ["开发语言", "常用 IDE", "常用模型", "系统环境", "加密货币", "免杀对抗"]
        config = {"username": "CoreRCE", "ecosystem": [
            {"label": label, "items": ["已填写"]} for label in labels
        ]}
        element = ET.fromstring(visuals.ecosystem(config))
        ns = {"s": "http://www.w3.org/2000/svg"}
        captions = [node.text for node in element.findall(".//s:text", ns)]
        for label in labels:
            self.assertEqual(captions.count(label), 1)
        self.assertNotIn("待补充", captions)
        connections = [line for line in element.findall(".//s:line", ns)
                       if "draw" in line.get("class", "").split()]
        self.assertEqual(len(connections), len(labels))
        nodes = [rect for rect in element.findall(".//s:rect", ns)
                 if rect.get("class") == "rule" and rect.get("width") == "230"]
        self.assertEqual(len(nodes), len(labels))

    def test_cards_have_no_background_elements(self):
        config = {"username": "CoreRCE", "info": [{"label": "状态", "value": "已填写"}],
                  "ecosystem": [{"label": "开发语言", "items": ["Python"]}]}
        images = {
            "system_info": visuals.system_info(config, {"available": False}),
            "ecosystem": visuals.ecosystem(config),
            "language_data": visuals.language_stats({"available": True, "languages": {"Python": 123}}),
            "language_empty": visuals.language_stats({"available": True, "languages": {}}),
            "language_unsynced": visuals.language_stats({"available": False}),
        }
        ns = {"s": "http://www.w3.org/2000/svg"}
        for name, image in images.items():
            with self.subTest(section=name):
                root = ET.fromstring(image)
                self.assertFalse(any("surface" in element.get("class", "").split()
                                     for element in root.iter()))
                self.assertFalse(any(rect.get("width") == root.get("width")
                                     and rect.get("height") == root.get("height")
                                     for rect in root.findall(".//s:rect", ns)))
        # Language bars still carry data fill; only the canvas background is removed.
        data_rectangles = ET.fromstring(images["language_data"]).findall(".//s:rect", ns)
        self.assertTrue(any(rect.get("class") == "data" for rect in data_rectangles))

    def test_ecosystem_lines_connect_edges_without_crossing_card_interiors(self):
        ns = {"s": "http://www.w3.org/2000/svg"}

        def bounds(rect):
            x, y = float(rect.get("x")), float(rect.get("y"))
            return x, y, x + float(rect.get("width")), y + float(rect.get("height"))

        def on_edge(point, box):
            x, y = point
            left, top, right, bottom = box
            return (left - .02 <= x <= right + .02 and top - .02 <= y <= bottom + .02
                    and min(abs(x - left), abs(x - right), abs(y - top), abs(y - bottom)) <= .02)

        def crosses_interior(start, end, box):
            # Clip the segment against a slightly inset box so a boundary touch
            # is accepted while a line through text/card content is rejected.
            low, high = 0.0, 1.0
            for origin, target, minimum, maximum in (
                    (start[0], end[0], box[0] + .03, box[2] - .03),
                    (start[1], end[1], box[1] + .03, box[3] - .03)):
                delta = target - origin
                if abs(delta) < 1e-9:
                    if not minimum < origin < maximum:
                        return False
                    continue
                entry, leave = sorted(((minimum - origin) / delta, (maximum - origin) / delta))
                low, high = max(low, entry), min(high, leave)
                if low >= high:
                    return False
            return low < high

        for count in (6, 8):
            with self.subTest(nodes=count):
                root = ET.fromstring(visuals.ecosystem({"username": "CoreRCE", "ecosystem": [
                    {"label": f"节点 {index}", "items": ["已填写"]} for index in range(count)
                ]}))
                rectangles = root.findall(".//s:rect", ns)
                hub = next(bounds(rect) for rect in rectangles if rect.get("width") == "240")
                nodes = [bounds(rect) for rect in rectangles if rect.get("width") == "230"]
                connections = [line for line in root.findall(".//s:line", ns)
                               if "draw" in line.get("class", "").split()]
                self.assertEqual(len(connections), count)
                self.assertEqual(len(nodes), count)
                for line, node in zip(connections, nodes):
                    start = float(line.get("x1")), float(line.get("y1"))
                    end = float(line.get("x2")), float(line.get("y2"))
                    self.assertTrue(on_edge(start, hub))
                    self.assertTrue(on_edge(end, node))
                    for box in [hub] + nodes:
                        self.assertFalse(crosses_interior(start, end, box))


if __name__ == "__main__":
    unittest.main()

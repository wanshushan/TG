from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageStat


def _load_center_image(img_path: str | Path, target_size: tuple[int, int] = (224, 224)) -> Image.Image:
	image = Image.open(img_path).convert("RGB")
	width, height = image.size
	if width > 0 and height > 0:
		crop_ratio = 0.8
		crop_w = int(width * crop_ratio)
		crop_h = int(height * crop_ratio)
		left = max((width - crop_w) // 2, 0)
		top = max((height - crop_h) // 2, 0)
		right = min(left + crop_w, width)
		bottom = min(top + crop_h, height)
		image = image.crop((left, top, right, bottom))
	return image.resize(target_size)


def _predict_tongue_color_label(img_path: str | Path) -> str:
	image = _load_center_image(img_path)
	stat = ImageStat.Stat(image)
	r_mean, g_mean, b_mean = stat.mean

	if r_mean < 110 and b_mean >= g_mean:
		return "紫舌"
	if r_mean < 145 and abs(r_mean - g_mean) <= 10 and b_mean > 95:
		return "淡白舌"
	if r_mean > 175 and g_mean < 95 and b_mean < 95:
		return "绛舌"
	if r_mean > 155 and g_mean < 130:
		return "红舌"
	return "淡红舌"


def _predict_tongue_coat_label(img_path: str | Path) -> str:
	image = _load_center_image(img_path)
	hsv_stat = ImageStat.Stat(image.convert("HSV"))
	gray_stat = ImageStat.Stat(image.convert("L"))

	s_mean = hsv_stat.mean[1] / 255.0
	v_mean = hsv_stat.mean[2] / 255.0
	gray_std = gray_stat.stddev[0]

	if (v_mean > 0.62 and s_mean < 0.25) or gray_std < 35:
		return "舌苔湿润"
	if (v_mean < 0.50 and s_mean > 0.30) or gray_std > 55:
		return "舌苔干燥"
	return "舌苔湿润"


def predict_tongue_color_text(img_path: str | Path) -> str:
	tongue_color = _predict_tongue_color_label(img_path)
	return "\n".join([
		f"【舌色结果】：{tongue_color}",
	])


def predict_tongue_coat_text(img_path: str | Path) -> str:
	tongue_coat = _predict_tongue_coat_label(img_path)
	return "\n".join([
		f"【舌苔状态】：{tongue_coat}",
		"=" * 30,
	])


def predict_hu_tongue(img_path: str | Path) -> tuple[str, str]:
	return predict_tongue_color_text(img_path), predict_tongue_coat_text(img_path)


if __name__ == "__main__":
	test_image = Path(__file__).resolve().parent / "ML-hu-main" / "test.png"
	if test_image.exists():
		color_text, coat_text = predict_hu_tongue(test_image)
		print(color_text)
		print(coat_text)

from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from torchvision.models import resnet18

BASE_DIR = Path(__file__).resolve().parent

CLASS_NAMES = ["薄舌", "厚舌", "老舌", "裂纹", "嫩舌"]

TRANSFORM = transforms.Compose([
	transforms.Resize((224, 224)),
	transforms.ToTensor(),
	transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def load_tongue_classifier(model_path: str | Path | None = None):
	target_model_path = Path(model_path) if model_path is not None else BASE_DIR / "yzp" / "tongue_classifier.pth"
	model = resnet18(weights=None)
	model.fc = nn.Linear(model.fc.in_features, len(CLASS_NAMES))
	model.load_state_dict(torch.load(target_model_path, map_location="cpu"))
	model.eval()
	return model


def predict_tongue_quality_label(
	img_path: str | Path,
	model_path: str | Path | None = None,
) -> str:
	model = load_tongue_classifier(model_path)
	image = Image.open(img_path).convert("RGB")
	x = TRANSFORM(image).unsqueeze(0)

	with torch.no_grad():
		output = model(x)
		pred = torch.argmax(output, dim=1).item()

	return CLASS_NAMES[pred]


def build_result_text(tongue_quality: str) -> str:
	return "\n".join([
		f"【苔质类型】：{tongue_quality}",
	])


def predict_tongue_quality(
	img_path: str | Path,
	model_path: str | Path | None = None,
) -> str:
	tongue_quality = predict_tongue_quality_label(img_path=img_path, model_path=model_path)
	return build_result_text(tongue_quality)


if __name__ == "__main__":
	print(
		predict_tongue_quality(
			img_path=BASE_DIR / "yzp" / "test.png",
			model_path=BASE_DIR / "yzp" / "tongue_classifier.pth",
		)
	)

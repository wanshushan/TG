import torch
from torchvision import transforms
from PIL import Image
from torchvision.models import resnet18
import torch.nn as nn
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 加载模型
def load_model(num_classes, path):
    model = resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    model.load_state_dict(torch.load(path, map_location="cpu"))
    model.eval()
    return model

# 预处理
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

# 预测函数
def predict(img_path, model, class_names):
    img = Image.open(img_path).convert('RGB')
    img = transform(img).unsqueeze(0)
    with torch.no_grad():
        output = model(img)
        _, pred = torch.max(output, 1)
    return class_names[pred.item()]

def build_result_text(color_result: str, spirit_result: str) -> str:
    return "\n".join([
        "=" * 30,
        f"【苔色】：{color_result}",
        f"【舌神】：{spirit_result}",
        "=" * 30,
    ])


def predict_color_spirit(
    img_path: str | Path | None = None,
    color_model_path: str | Path | None = None,
    spirit_model_path: str | Path | None = None,
) -> str:
    target_color_model_path = Path(color_model_path) if color_model_path is not None else BASE_DIR / "color_model.pt"
    target_spirit_model_path = Path(spirit_model_path) if spirit_model_path is not None else BASE_DIR / "spirit_model.pt"

    color_model = load_model(4, target_color_model_path)
    spirit_model = load_model(2, target_spirit_model_path)

    color_classes = ["白", "黄", "灰", "黑"]
    spirit_classes = ["荣", "枯"]

    target_img_path = Path(img_path) if img_path is not None else BASE_DIR / "test.jpg"
    color_result = predict(target_img_path, color_model, color_classes)
    spirit_result = predict(target_img_path, spirit_model, spirit_classes)
    return build_result_text(color_result, spirit_result)


if __name__ == "__main__":
    print(predict_color_spirit(r"RD\docter_tg\ay_color_sprit\test.jpg", r"RD\docter_tg\ay_color_sprit\color_model.pt", r"RD\docter_tg\ay_color_sprit\spirit_model.pt"))
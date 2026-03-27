import torch
import torch.nn as nn
from torchvision import transforms
from PIL import Image
from torchvision.models import resnet18

# 你的类别（要和训练时顺序完全一样）
class_names = ["薄舌", "厚舌", "老舌", "裂纹", "嫩舌"]

# 图片预处理（必须和训练时一致）
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])


model = resnet18(pretrained=False)
model.fc = nn.Linear(model.fc.in_features, 5)
model.load_state_dict(torch.load(r"RD\docter_tg\yzp\tongue_classifier.pth"))
model.eval()


img_path = r"RD\docter_tg\yzp\test.png"   # 这里换成你的图片路径
image = Image.open(img_path).convert("RGB")
x = transform(image).unsqueeze(0)

# 推理
with torch.no_grad():
    output = model(x)
    pred = torch.argmax(output, dim=1).item()

print("="*30)
print(f"[苔质类型]：{class_names[pred]}")
print("="*30)

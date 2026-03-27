import os
import random

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"

import torch
from ultralytics import YOLO
import warnings

warnings.filterwarnings(action="ignore", category=UserWarning)

# ===================== 舌色 类别映射（改成你训练的类别）=====================
class_map = {
    0: "淡白舌",
    1: "淡红舌",
    2: "红舌",
    3: "绛舌",
    4: "紫舌"
}

# ===================== 推理输出（舌色专用）=====================
def predict_and_print_result(model_path, img_path):
    print("\n" + "=" * 60)
    print("📝 舌色检测结果（文字输出）")
    print("=" * 60)

    model = YOLO(model_path)
    results = model(img_path, verbose=False)  # 关闭多余日志

    # 只输出一次最终结果
    res = results[0]
    if len(res.boxes) > 0:
        cls_id = int(res.boxes.cls[0])
        color = class_map[cls_id]
        print(f"【舌色结果】：{color}")
    else:
        print(f"【舌色结果】：未检测到舌头")

    print("=" * 60 + "\n")

# ===================== 随机选测试图 =====================
def get_random_test_image():
    # 你的测试集图片路径
    test_img_dir = r"C:\Users\lenovo\Desktop\舌色与苔质\tongue_color\Tongue-color_data\test\images"

    if not os.path.exists(test_img_dir):
        print(f"路径不存在: {test_img_dir}")
        return None

    img_extensions = ('.jpg', '.jpeg', '.png', '.bmp')
    img_list = [f for f in os.listdir(test_img_dir) if f.lower().endswith(img_extensions)]

    if not img_list:
        print(f"文件夹中没有找到图片！")
        return None

    random_img = random.choice(img_list)
    return os.path.join(test_img_dir, random_img)


if __name__ == '__main__':
    print("CUDA 是否可用:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("当前 GPU:", torch.cuda.get_device_name())

    # ===================== 你的舌色模型路径 =====================
    best_model_path = r"RD\docter_tg\ML-hu-main\model\best.pt"

    # 随机选一张测试图
    test_img_path = get_random_test_image()

    if test_img_path:
        print(f"\n🎲 随机选中测试图片: {os.path.basename(test_img_path)}")
        predict_and_print_result(best_model_path, test_img_path)
    else:
        print("\n⚠️  无法进行测试，请先在 test 文件夹放入图片。")
import os

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"

import torch
from ultralytics import YOLO
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

if __name__ == '__main__':
    print("CUDA:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))

    # 加载模型
    model = YOLO(r"C:\Users\lenovo\Desktop\yolo26\ultralytics-main\ultralytics\cfg\models\26\yolo26.yaml")

    # 训练
    model.train(
        data=r"C:\Users\lenovo\Desktop\舌色与苔质\tongue_color\Tongue-color_data\data.yaml",
        epochs=100,
        imgsz=640,
        batch=8,
        device=0,
        pretrained=True,
        name="yolo26_tongue",
        patience=5,
        save_period=5,
        cache="disk",
        amp=True,
        workers=0,

        lr0=0.0005,
        lrf=0.005,
        momentum=0.9,
        weight_decay=0.001,
        optimizer="AdamW",

        hsv_h=0.005,
        hsv_s=0.1,
        hsv_v=0.15,
        degrees=2,
        translate=0.03,
        scale=0.03,
        fliplr=0.2,
        flipud=0.0,
        mosaic=0.5
    )
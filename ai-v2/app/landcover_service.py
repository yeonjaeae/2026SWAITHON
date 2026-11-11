
import os
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import (
    AutoImageProcessor,
    Mask2FormerForUniversalSegmentation,
)

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)

MODEL_NAME = "mfaytin/mask2former-satellite"

TILE_SIZE = 512
OVERLAP = 64
CORE_SIZE = TILE_SIZE - 2 * OVERLAP


def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@lru_cache(maxsize=1)
def load_model():
    print("Mask2Former 모델 로딩 중...")

    processor = AutoImageProcessor.from_pretrained(
        MODEL_NAME
    )

    model = (
        Mask2FormerForUniversalSegmentation
        .from_pretrained(MODEL_NAME)
    )

    device = get_device()
    model.to(device)
    model.eval()

    print("✅ Mask2Former 로딩 완료:", device)
    print("클래스 정보:", model.config.id2label)

    return processor, model, device


def predict_landcover(image):
    processor, model, device = load_model()

    image = image.convert("RGB")
    width, height = image.size

    segmentation = np.zeros(
        (height, width), dtype=np.int32
    )

    # 핵심 영역 주변 64px 문맥을 포함해 추론
    for y in range(0, height, CORE_SIZE):
        for x in range(0, width, CORE_SIZE):

            core_x2 = min(x + CORE_SIZE, width)
            core_y2 = min(y + CORE_SIZE, height)

            left = max(0, x - OVERLAP)
            top = max(0, y - OVERLAP)
            right = min(width, core_x2 + OVERLAP)
            bottom = min(height, core_y2 + OVERLAP)

            tile = image.crop(
                (left, top, right, bottom)
            )

            inputs = processor(
                images=tile,
                return_tensors="pt"
            ).to(device)

            with torch.inference_mode():
                outputs = model(**inputs)

            pred = processor.post_process_semantic_segmentation(
                outputs,
                target_sizes=[(tile.height, tile.width)]
            )[0].cpu().numpy()

            # 겹친 부분은 버리고 중심 영역 사용
            segmentation[y:core_y2, x:core_x2] = pred[
                y - top:core_y2 - top,
                x - left:core_x2 - left
            ]

            print(
                f"추론 완료: x={x}, y={y}",
                flush=True
            )

    return segmentation


def save_class_previews(image, segmentation):
    image_np = np.array(image.convert("RGB"))

    ids, counts = np.unique(
        segmentation, return_counts=True
    )

    print("\n===== 클래스별 비율 =====")

    for class_id, count in zip(ids, counts):
        ratio = count / segmentation.size * 100
        print(f"Class {class_id}: {ratio:.2f}%")

        mask = segmentation == class_id

        # 클래스별 마스크 저장
        Image.fromarray(
            (mask * 255).astype(np.uint8)
        ).save(
            OUTPUTS / f"class_{class_id}.png"
        )

        # 항공사진 위에 빨간색으로 표시
        overlay = image_np.copy()

        overlay[mask] = (
            image_np[mask] * 0.5
            + np.array([255, 50, 50]) * 0.5
        ).astype(np.uint8)

        Image.fromarray(overlay).save(
            OUTPUTS / f"class_{class_id}_overlay.png"
        )

    print("\n✅ 클래스별 분석 이미지 저장 완료!")

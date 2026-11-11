from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

image = Image.open(ROOT / "data" / "aerial.png").convert("RGB")

fig, ax = plt.subplots(figsize=(12, 12))
ax.imshow(image)

# 128픽셀 간격으로 좌표 표시
ax.set_xticks(np.arange(0, 2049, 128))
ax.set_yticks(np.arange(0, 2049, 128))

ax.grid(color="red", alpha=0.35)
ax.set_xlim(0, 2048)
ax.set_ylim(2048, 0)
ax.tick_params(labelsize=8)

plt.tight_layout()

output_path = ROOT / "outputs" / "aerial_grid.png"
plt.savefig(output_path, dpi=160)
plt.show()

print("✅ 좌표 이미지 저장:", output_path)
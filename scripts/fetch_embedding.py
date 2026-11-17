"""Download pinned ONNX assets at build time. Serving uses local files only."""
import os
from pathlib import Path
from urllib.request import urlretrieve

REVISION = "75c43b069aac4d136ba6bc1122f995fedcfd2781"
BASE = f"https://huggingface.co/Xenova/bge-small-zh-v1.5/resolve/{REVISION}"
FILES = {"tokenizer.json": "tokenizer.json", "model.onnx": "onnx/model_quantized.onnx"}

if __name__ == "__main__":
    directory = Path(os.environ.get("MODEL_DIR", "models"))
    directory.mkdir(parents=True, exist_ok=True)
    for local, remote in FILES.items():
        destination = directory / local
        temporary = destination.with_suffix(".download")
        urlretrieve(f"{BASE}/{remote}", temporary)
        temporary.replace(destination)

"""Download pinned ONNX assets at build time. Serving uses local files only."""
import hashlib
import os
import shutil
from pathlib import Path
from time import sleep
from urllib.request import urlopen

REVISION = "75c43b069aac4d136ba6bc1122f995fedcfd2781"
BASE = f"https://huggingface.co/Xenova/bge-small-zh-v1.5/resolve/{REVISION}"
FILES = {
    "tokenizer.json": (
        "tokenizer.json", "48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26"
    ),
    "model.onnx": (
        "onnx/model_quantized.onnx", "15b717c382bcb518ba457b93ea6850ede7f4f1cd8937454aa06972366cd19bcc"
    ),
}


def download(remote, temporary):
    for attempt in range(3):
        try:
            with urlopen(f"{BASE}/{remote}", timeout=60) as source, temporary.open("wb") as target:
                shutil.copyfileobj(source, target)
            return
        except OSError:
            if attempt == 2:
                raise
            sleep(2 ** attempt)

if __name__ == "__main__":
    directory = Path(os.environ.get("MODEL_DIR", "models"))
    directory.mkdir(parents=True, exist_ok=True)
    for local, (remote, checksum) in FILES.items():
        destination = directory / local
        temporary = destination.with_suffix(".download")
        download(remote, temporary)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"SHA-256 mismatch for {remote}")
        temporary.replace(destination)

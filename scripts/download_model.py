"""下载 ONNX embedding 模型"""

import shutil
import sys
from pathlib import Path
from huggingface_hub import hf_hub_download


MODELS = {
    "all-MiniLM-L6-v2": {
        "repo": "sentence-transformers/all-MiniLM-L6-v2",
        "files": ["onnx/model.onnx", "tokenizer.json", "tokenizer_config.json"],
    },
    "bge-small-zh-v1.5": {
        "repo": "BAAI/bge-small-zh-v1.5",
        "files": ["onnx/model.onnx", "tokenizer.json", "tokenizer_config.json"],
    },
}


def download_model(model_name: str, model_dir: str = "./models"):
    if model_name not in MODELS:
        print(f"可用模型: {list(MODELS.keys())}")
        sys.exit(1)

    info = MODELS[model_name]
    target_dir = Path(model_dir) / model_name
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"下载模型: {model_name}")
    print(f"来源: {info['repo']}")
    print(f"目标: {target_dir}")

    for filename in info["files"]:
        print(f"  下载 {filename}...")
        local_path = hf_hub_download(
            repo_id=info["repo"],
            filename=filename,
            local_dir=str(target_dir),
        )
        # 如果下载到子目录（如 onnx/model.onnx），移动到目标位置
        src = Path(local_path)
        if "onnx/" in filename:
            dst = target_dir / filename.replace("onnx/", "")
            if src != dst:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"    -> {dst}")

    print(f"\n模型下载完成: {target_dir}")
    print("文件列表:")
    for f in sorted(target_dir.rglob("*")):
        if f.is_file():
            size_mb = f.stat().st_size / 1024 / 1024
            print(f"  {f.relative_to(target_dir)} ({size_mb:.1f}MB)")


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "all-MiniLM-L6-v2"
    model_dir = sys.argv[2] if len(sys.argv) > 2 else "./models"
    download_model(model, model_dir)

"""
Split dataset into:
- train
- val
- internal_test

Expects classes directly under dataset-dir (e.g. dataset/fist/, dataset/none/).
Moves files into dataset-dir/train/, dataset-dir/val/, dataset-dir/internal_test/.
Preserves class balance.
"""

import os
import shutil
import random
import argparse

# ---------------- CONFIG ---------------- #

parser = argparse.ArgumentParser()
parser.add_argument("--dataset-dir", default="dataset",
                    help="Dataset root containing class subfolders")
parser.add_argument("--train-ratio", type=float, default=0.7)
parser.add_argument("--val-ratio", type=float, default=0.15)
parser.add_argument("--seed", type=int, default=42)

args = parser.parse_args()
random.seed(args.seed)

assert args.train_ratio + args.val_ratio < 1.0, "Invalid split ratios"

DATASET_DIR = args.dataset_dir
TRAIN_DIR = os.path.join(DATASET_DIR, "train")
VAL_DIR = os.path.join(DATASET_DIR, "val")
TEST_DIR = os.path.join(DATASET_DIR, "internal_test")

RESERVED = {"train", "val", "internal_test"}

# ---------------- UTILS ---------------- #

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

# ---------------- MAIN ---------------- #

classes = sorted([
    d for d in os.listdir(DATASET_DIR)
    if os.path.isdir(os.path.join(DATASET_DIR, d)) and d not in RESERVED
])

if not classes:
    raise RuntimeError(f"No class folders found in '{DATASET_DIR}'. "
                       "Expected subfolders like dataset/fist/, dataset/open/, ...")

print(f"Found {len(classes)} classes: {classes}")

ensure_dir(TRAIN_DIR)
ensure_dir(VAL_DIR)
ensure_dir(TEST_DIR)

for cls in classes:
    src_cls_dir = os.path.join(DATASET_DIR, cls)
    images = [
        f for f in os.listdir(src_cls_dir)
        if f.lower().endswith((".jpg", ".png", ".jpeg"))
    ]

    random.shuffle(images)

    n = len(images)
    n_train = int(n * args.train_ratio)
    n_val = int(n * args.val_ratio)

    train_images = images[:n_train]
    val_images = images[n_train:n_train + n_val]
    test_images = images[n_train + n_val:]

    # Create destination class folders
    ensure_dir(os.path.join(TRAIN_DIR, cls))
    ensure_dir(os.path.join(VAL_DIR, cls))
    ensure_dir(os.path.join(TEST_DIR, cls))

    # Move files
    for img in train_images:
        shutil.move(
            os.path.join(src_cls_dir, img),
            os.path.join(TRAIN_DIR, cls, img)
        )

    for img in val_images:
        shutil.move(
            os.path.join(src_cls_dir, img),
            os.path.join(VAL_DIR, cls, img)
        )

    for img in test_images:
        shutil.move(
            os.path.join(src_cls_dir, img),
            os.path.join(TEST_DIR, cls, img)
        )

    print(f"  {cls:15s}: total={n}, train={len(train_images)}, val={len(val_images)}, test={len(test_images)}")

    # Remove now-empty source class folder
    remaining = os.listdir(src_cls_dir)
    if not remaining:
        os.rmdir(src_cls_dir)

print("\nDataset split completed successfully!")
print(f"  Train:         {TRAIN_DIR}")
print(f"  Validation:    {VAL_DIR}")
print(f"  Internal test: {TEST_DIR}")

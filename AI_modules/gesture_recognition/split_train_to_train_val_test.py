"""
Split existing train dataset into:
- train
- val
- internal_test

Preserve class balance
"""

import os
import shutil
import random
import argparse

# ---------------- CONFIG ---------------- #

parser = argparse.ArgumentParser()
parser.add_argument("--dataset-dir", default="dataset",
                    help="Dataset root containing train/")
parser.add_argument("--train-ratio", type=float, default=0.7)
parser.add_argument("--val-ratio", type=float, default=0.15)
parser.add_argument("--seed", type=int, default=42)

args = parser.parse_args()
random.seed(args.seed)

assert args.train_ratio + args.val_ratio < 1.0, "Invalid split ratios"

TRAIN_DIR = os.path.join(args.dataset_dir, "train")
VAL_DIR = os.path.join(args.dataset_dir, "val")
TEST_DIR = os.path.join(args.dataset_dir, "internal_test")

# ---------------- UTILS ---------------- #

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

# ---------------- MAIN ---------------- #

classes = sorted([
    d for d in os.listdir(TRAIN_DIR)
    if os.path.isdir(os.path.join(TRAIN_DIR, d))
])

print(f"Found {len(classes)} classes: {classes}")

ensure_dir(VAL_DIR)
ensure_dir(TEST_DIR)

for cls in classes:
    cls_train_dir = os.path.join(TRAIN_DIR, cls)
    images = [
        f for f in os.listdir(cls_train_dir)
        if f.lower().endswith((".jpg", ".png", ".jpeg"))
    ]

    random.shuffle(images)

    n = len(images)
    n_train = int(n * args.train_ratio)
    n_val = int(n * args.val_ratio)

    val_images = images[n_train:n_train + n_val]
    test_images = images[n_train + n_val:]

    # Create class folders
    ensure_dir(os.path.join(VAL_DIR, cls))
    ensure_dir(os.path.join(TEST_DIR, cls))

    # Move files
    for img in val_images:
        shutil.move(
            os.path.join(cls_train_dir, img),
            os.path.join(VAL_DIR, cls, img)
        )

    for img in test_images:
        shutil.move(
            os.path.join(cls_train_dir, img),
            os.path.join(TEST_DIR, cls, img)
        )

    print(f"{cls}: train={n_train}, val={len(val_images)}, test={len(test_images)}")

print("\n✅ Dataset split completed successfully!")
print(f"Train remains in: {TRAIN_DIR}")
print(f"Validation set:   {VAL_DIR}")
print(f"Internal test:    {TEST_DIR}")

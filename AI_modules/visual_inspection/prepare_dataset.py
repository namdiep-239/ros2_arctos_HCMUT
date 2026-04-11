"""
Prepare dataset: split raw images from dataset/raw/{PASS,FAIL}/
into dataset/split/{train,val,test}/{PASS,FAIL}/ structure
"""

import os
import shutil
import random
import argparse
from glob import glob

parser = argparse.ArgumentParser()
parser.add_argument("--raw-dir", type=str, default="dataset/raw",
                    help="Source directory with PASS/ and FAIL/ subfolders")
parser.add_argument("--out-dir", type=str, default="dataset/split",
                    help="Output directory for train/val/test splits")
parser.add_argument("--val-ratio", type=float, default=0.15)
parser.add_argument("--test-ratio", type=float, default=0.15)
parser.add_argument("--seed", type=int, default=42)
args = parser.parse_args()

random.seed(args.seed)

classes = ["PASS", "FAIL"]
splits = ["train", "val", "test"]

# Create output dirs
for split in splits:
    for cls in classes:
        os.makedirs(os.path.join(args.out_dir, split, cls), exist_ok=True)

for cls in classes:
    # Images are inside per-sample subdirectories (s01/, s02/, ...)
    images = sorted(glob(os.path.join(args.raw_dir, f"*/{cls}_*.jpg")))
    random.shuffle(images)

    n = len(images)
    n_test = int(n * args.test_ratio)
    n_val = int(n * args.val_ratio)
    n_train = n - n_val - n_test

    split_map = {
        "train": images[:n_train],
        "val": images[n_train:n_train + n_val],
        "test": images[n_train + n_val:]
    }

    for split, files in split_map.items():
        for src in files:
            dst = os.path.join(args.out_dir, split, cls, os.path.basename(src))
            shutil.copy2(src, dst)
        print(f"  {cls}/{split}: {len(files)} images")

print(f"\nDataset split saved to: {args.out_dir}")

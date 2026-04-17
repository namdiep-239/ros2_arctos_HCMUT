"""
Convert retrained Keras model to TFLite with full INT8 quantization
"""

import tensorflow as tf
import argparse
import os
import sys
import numpy as np
from glob import glob

parser = argparse.ArgumentParser()
parser.add_argument("--h5-model", type=str, required=True)
parser.add_argument("--output", type=str, default="models")
parser.add_argument("--data-dir", type=str, default="./dataset",
                    help="Root dataset train folder for representative dataset")
parser.add_argument("--image-size", type=int, default=224)
parser.add_argument("--max-samples", type=int, default=500)
args = parser.parse_args()

os.makedirs(args.output, exist_ok=True)

# Load representative dataset for quantization
IMG_SHAPE = (args.image_size, args.image_size)

def load_images(folder):
    images = []
    classes = sorted(os.listdir(folder))
    for cls in classes:
        cls_folder = os.path.join(folder, cls)
        if not os.path.isdir(cls_folder):
            continue
        files = sorted(
            f for ext in ("*.jpg", "*.jpeg", "*.png")
            for f in glob(os.path.join(cls_folder, ext))
        )
        for f in files:
            img = tf.io.read_file(f)
            img = tf.image.decode_image(img, channels=3, expand_animations=False)
            img = tf.image.resize(img, IMG_SHAPE)
            img = img / 255.0
            images.append(img.numpy())
            if len(images) >= args.max_samples:
                return images
    return images

imgs = load_images(os.path.join(args.data_dir, "train"))
print(f"Loaded {len(imgs)} images for quantization calibration")

def representative_generator():
    for img in imgs:
        yield [np.expand_dims(img.astype(np.float32), axis=0)]

model = tf.keras.models.load_model(args.h5_model)

converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_generator
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.uint8
converter.inference_output_type = tf.uint8

tflite_model = converter.convert()
tflite_path = os.path.join(args.output, "gesture_retrained_int8.tflite")
with open(tflite_path, "wb") as f:
    f.write(tflite_model)

print(f"TFLite INT8 saved to {tflite_path}")

# edgetpu_compiler ./models/gesture_retrained_int8.tflite
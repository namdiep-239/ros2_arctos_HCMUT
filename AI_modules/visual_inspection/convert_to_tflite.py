"""
Convert trained Keras model to INT8 TFLite for Google Coral EdgeTPU.

After running this script, compile with:
    edgetpu_compiler models/inspection_model_int8.tflite
"""

import os
import argparse
import numpy as np
import tensorflow as tf
from glob import glob

parser = argparse.ArgumentParser()
parser.add_argument("--h5-model", type=str, default="models/inspection_model.h5")
parser.add_argument("--output", type=str, default="models")
parser.add_argument("--data-dir", type=str, default="dataset/split",
                    help="Root dataset dir (uses train/ for calibration)")
parser.add_argument("--image-size", type=int, default=224)
parser.add_argument("--max-samples", type=int, default=200,
                    help="Number of images for quantization calibration")
args = parser.parse_args()

os.makedirs(args.output, exist_ok=True)

IMG_SHAPE = (args.image_size, args.image_size)


def load_images(folder):
    images = []
    classes = sorted(os.listdir(folder))
    for cls in classes:
        cls_folder = os.path.join(folder, cls)
        if not os.path.isdir(cls_folder):
            continue
        files = glob(os.path.join(cls_folder, "*.jpg"))
        for f in files:
            img = tf.io.read_file(f)
            img = tf.image.decode_jpeg(img, channels=3)
            img = tf.image.resize(img, IMG_SHAPE)
            img = img / 255.0
            images.append(img.numpy())
            if len(images) >= args.max_samples:
                return images
    return images


imgs = load_images(os.path.join(args.data_dir, "train"))
print(f"Loaded {len(imgs)} calibration images")


def representative_generator():
    for img in imgs:
        yield [np.expand_dims(img.astype(np.float32), axis=0)]


model = tf.keras.models.load_model(args.h5_model)

# ── CPU model: INT8 internal ops, float32 I/O ────────────────────────────────
# Keeps full numerical precision at the input/output boundary.
# Works on CPU and avoids the TF 2.x uint8-output calibration collapse bug
# (where very-confident softmax outputs get quantized to [128,128]).
converter_cpu = tf.lite.TFLiteConverter.from_keras_model(model)
converter_cpu.optimizations = [tf.lite.Optimize.DEFAULT]
converter_cpu.representative_dataset = representative_generator
converter_cpu.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
# Do NOT set inference_output_type — leave output as float32

tflite_cpu = converter_cpu.convert()
cpu_path = os.path.join(args.output, "inspection_model_int8.tflite")
with open(cpu_path, "wb") as f:
    f.write(tflite_cpu)
print(f"CPU INT8 model saved to: {cpu_path}")

# ── EdgeTPU model: full uint8 I/O (required by Coral compiler) ───────────────
# Must set both input and output to uint8.
# Use a fresh representative_generator for this pass.
converter_tpu = tf.lite.TFLiteConverter.from_keras_model(model)
converter_tpu.optimizations = [tf.lite.Optimize.DEFAULT]
converter_tpu.representative_dataset = representative_generator
converter_tpu.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter_tpu.inference_input_type  = tf.uint8
converter_tpu.inference_output_type = tf.uint8

tflite_tpu = converter_tpu.convert()
tpu_path = os.path.join(args.output, "inspection_model_int8_edgetpu_src.tflite")
with open(tpu_path, "wb") as f:
    f.write(tflite_tpu)
print(f"EdgeTPU-ready INT8 model saved to: {tpu_path}")
print("\nNext step — compile for EdgeTPU:")
print(f"  edgetpu_compiler {tpu_path}")

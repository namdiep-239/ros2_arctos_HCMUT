"""
Compare accuracy between:
- Raw Keras FP32 model (.h5)
- TFLite INT8 model (pre-EdgeTPU)

Equivalent to Coral retrain classification accuracy comparison
"""

import os
import json
import argparse
import numpy as np
import cv2
import tensorflow as tf

from sklearn.metrics import accuracy_score, confusion_matrix, classification_report


# ================= CONFIG ================= #

IMAGE_SIZE = (224, 224)


# ================= DATASET ================= #

def load_test_dataset(dataset_path):
    images, labels = [], []

    class_names = sorted([
        d for d in os.listdir(dataset_path)
        if os.path.isdir(os.path.join(dataset_path, d))
    ])
    class_to_idx = {c: i for i, c in enumerate(class_names)}

    for cls in class_names:
        cls_dir = os.path.join(dataset_path, cls)
        for f in sorted(os.listdir(cls_dir)):
            if not f.lower().endswith((".jpg", ".png", ".jpeg")):
                continue

            img_path = os.path.join(cls_dir, f)
            img = cv2.imread(img_path)
            if img is None:
                continue

            img = cv2.resize(img, IMAGE_SIZE)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            images.append(img)
            labels.append(class_to_idx[cls])

    images = np.array(images)
    labels = np.array(labels)

    return images, labels, class_names


# ================= RAW MODEL ================= #

def predict_raw(model, images, batch_size=32):
    """Predict with batching to reduce memory usage"""
    preds = []
    for i in range(0, len(images), batch_size):
        batch = images[i:i+batch_size].astype(np.float32) / 255.0
        batch_preds = model(batch, training=False).numpy()
        preds.extend(np.argmax(batch_preds, axis=1))
    return np.array(preds)


# ================= TFLITE MODEL ================= #

def load_tflite(model_path):
    interpreter = tf.lite.Interpreter(model_path=model_path)
    interpreter.allocate_tensors()
    return interpreter


def predict_tflite(interpreter, images):
    """Predict with TFLite — runs single-image sequentially (TFLite has no native batching)"""
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    preds = []
    total = len(images)

    for idx, img in enumerate(images):
        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1}/{total} images")
        
        # training used /255.0 → int8 expects uint8 [0,255]
        img_uint8 = img.astype(np.uint8)
        img_uint8 = np.expand_dims(img_uint8, axis=0)

        interpreter.set_tensor(input_details[0]["index"], img_uint8)
        interpreter.invoke()

        out = interpreter.get_tensor(output_details[0]["index"])
        preds.append(np.argmax(out))

    return np.array(preds)


# ================= MAIN ================= #

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-model", required=True, help=".h5 model path")
    parser.add_argument("--tflite-model", required=True, help=".tflite INT8 model path")
    parser.add_argument("--dataset", required=True, help="Path to test dataset")
    parser.add_argument("--output", default="results/compare_results.json")
    parser.add_argument("--max-samples", type=int, default=None,
                        help="Limit number of samples (for testing)")

    args = parser.parse_args()
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    print("Loading dataset...")
    images, labels, class_names = load_test_dataset(args.dataset)
    
    if args.max_samples and args.max_samples < len(images):
        images = images[:args.max_samples]
        labels = labels[:args.max_samples]
    
    print(f"Loaded {len(images)} test images")

    print("\nLoading raw FP32 model...")
    raw_model = tf.keras.models.load_model(args.raw_model)

    print("Loading TFLite INT8 model...")
    tflite_interpreter = load_tflite(args.tflite_model)

    print("\nRunning inference (RAW FP32)...")
    preds_raw = predict_raw(raw_model, images)

    print("Running inference (TFLite INT8)...")
    preds_tflite = predict_tflite(tflite_interpreter, images)

    # ================= METRICS ================= #

    acc_raw = accuracy_score(labels, preds_raw)
    acc_tflite = accuracy_score(labels, preds_tflite)

    cm_raw = confusion_matrix(labels, preds_raw)
    cm_tflite = confusion_matrix(labels, preds_tflite)

    mismatch = int(np.sum(preds_raw != preds_tflite))

    print("\n================ ACCURACY COMPARISON ================")
    print(f"RAW FP32 Accuracy:     {acc_raw*100:.2f}%")
    print(f"TFLite INT8 Accuracy:  {acc_tflite*100:.2f}%")
    print(f"Prediction mismatch:  {mismatch}/{len(labels)} samples")
    print("=====================================================")

    print("\nRAW MODEL CLASSIFICATION REPORT:")
    print(classification_report(labels, preds_raw, target_names=class_names))

    print("\nTFLITE MODEL CLASSIFICATION REPORT:")
    print(classification_report(labels, preds_tflite, target_names=class_names))

    results = {
        "raw_fp32": {
            "accuracy": float(acc_raw),
            "confusion_matrix": cm_raw.tolist()
        },
        "tflite_int8": {
            "accuracy": float(acc_tflite),
            "confusion_matrix": cm_tflite.tolist()
        },
        "prediction_mismatch": mismatch,
        "num_samples": int(len(labels))
    }

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()

"""
Run inference on a single image or webcam stream.

Keras model (fastest for prototyping — no TFLite needed):
    python inference.py --keras-model models/best_model.h5 --image path/to/img.jpg
    python inference.py --keras-model models/best_model.h5 --webcam

CPU TFLite:
    python inference.py --model models/inspection_model_int8.tflite --image path/to/img.jpg

EdgeTPU (Coral USB connected):
    python inference.py --model models/inspection_model_int8_edgetpu.tflite --webcam --edgetpu
"""

import os
import argparse
import json
import time
import numpy as np
import cv2

parser = argparse.ArgumentParser()
parser.add_argument("--model", type=str, default=None,
                    help="Path to .tflite model")
parser.add_argument("--keras-model", type=str, default=None,
                    help="Path to Keras .h5 model (bypasses TFLite, good for prototyping)")
parser.add_argument("--metadata", type=str, default="models/model_metadata.json")
parser.add_argument("--image", type=str, default=None)
parser.add_argument("--webcam", action="store_true")
parser.add_argument("--edgetpu", action="store_true",
                    help="Use Google Coral EdgeTPU delegate")
parser.add_argument("--camera-id", type=int, default=None,
                    help="Webcam index (auto-detect if omitted)")
parser.add_argument("--threshold", type=float, default=0.7,
                    help="Confidence threshold for FAIL alert")
args = parser.parse_args()

# ---------------------------------------------------------------------
# Load metadata
# ---------------------------------------------------------------------

with open(args.metadata) as f:
    meta = json.load(f)

class_names = meta["class_names"]
img_size = tuple(meta["image_size"])  # (224, 224)

# ---------------------------------------------------------------------
# Load interpreter
# ---------------------------------------------------------------------

if not args.model and not args.keras_model:
    print("ERROR: provide --model <tflite> or --keras-model <h5>")
    exit(1)

# ── Keras direct mode ────────────────────────────────────────────────────────
if args.keras_model:
    import tensorflow as tf
    keras_model = tf.keras.models.load_model(args.keras_model)
    print(f"Keras model loaded: {args.keras_model}")
    print(f"Classes: {class_names}")

    def preprocess(frame):
        img = cv2.resize(frame, img_size)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return np.expand_dims(img / 255.0, axis=0).astype(np.float32)

    def run_inference(frame):
        t0 = time.perf_counter()
        output = keras_model.predict(preprocess(frame), verbose=0)[0]
        latency_ms = (time.perf_counter() - t0) * 1000
        pred_idx = int(np.argmax(output))
        return class_names[pred_idx], float(output[pred_idx]), latency_ms

# ── TFLite mode ──────────────────────────────────────────────────────────────
else:
    if args.edgetpu:
        from pycoral.utils.edgetpu import make_interpreter
        interpreter = make_interpreter(args.model)
    else:
        try:
            import tflite_runtime.interpreter as tflite
            interpreter = tflite.Interpreter(model_path=args.model)
        except ImportError:
            import tensorflow as tf
            interpreter = tf.lite.Interpreter(model_path=args.model)

    interpreter.allocate_tensors()
    input_details  = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    input_dtype  = input_details[0]["dtype"]
    input_index  = input_details[0]["index"]
    output_index = output_details[0]["index"]

    print(f"TFLite model loaded: {args.model}")
    print(f"Input dtype: {input_dtype}  Shape: {input_details[0]['shape']}")
    print(f"Classes: {class_names}")

    def preprocess(frame):
        img = cv2.resize(frame, img_size)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = np.expand_dims(img, axis=0)
        if input_dtype == np.uint8:
            return img.astype(np.uint8)
        return (img / 255.0).astype(np.float32)

    def run_inference(frame):
        tensor = preprocess(frame)
        interpreter.set_tensor(input_index, tensor)

        t0 = time.perf_counter()
        interpreter.invoke()
        latency_ms = (time.perf_counter() - t0) * 1000

        output = interpreter.get_tensor(output_index)[0]

        # Dequantize uint8 output if needed
        if output_details[0]["dtype"] == np.uint8:
            scale, zero_point = output_details[0]["quantization"]
            output = (output.astype(np.float32) - zero_point) * scale

        pred_idx = int(np.argmax(output))
        return class_names[pred_idx], float(output[pred_idx]), latency_ms


# ---------------------------------------------------------------------
# Single image
# ---------------------------------------------------------------------

if args.image:
    frame = cv2.imread(args.image)
    if frame is None:
        print(f"Cannot read image: {args.image}")
        exit(1)
    label, conf, lat = run_inference(frame)
    print(f"Result: {label}  Confidence: {conf:.2%}  Latency: {lat:.1f} ms")

# ---------------------------------------------------------------------
# Webcam stream
# ---------------------------------------------------------------------

elif args.webcam:
    # Auto-detect: prefer UGREEN, fall back to first available camera
    def _find_cam():
        import glob as _glob
        prefer = ("ugreen", "ultra hd", "4k")
        for p in sorted(_glob.glob("/sys/class/video4linux/video*/name")):
            try:
                name = open(p).read().strip().lower()
                idx  = int(os.path.basename(os.path.dirname(p)).replace("video", ""))
            except Exception:
                continue
            if any(k in name for k in prefer):
                return idx
        for idx in range(8):
            c = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if c.isOpened():
                c.release()
                return idx
        return None

    cam_idx = args.camera_id if args.camera_id is not None else _find_cam()
    if cam_idx is None:
        print("ERROR: no camera found.")
        exit(1)

    cap = cv2.VideoCapture(cam_idx, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        print(f"ERROR: cannot open camera index {cam_idx}.")
        print("Pass the correct index with --camera-id N")
        exit(1)
    print(f"Camera opened on index {cam_idx}")

    print("Press Q to quit")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        label, conf, lat = run_inference(frame)

        color = (0, 200, 0) if label == "PASS" else (0, 0, 220)
        text = f"{label}  {conf:.1%}  {lat:.0f}ms"
        cv2.putText(frame, text, (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 2)

        if label == "FAIL" and conf >= args.threshold:
            cv2.rectangle(frame, (0, 0), (frame.shape[1], frame.shape[0]),
                          (0, 0, 220), 4)

        cv2.imshow("Visual Inspection", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

else:
    print("Provide --image <path> or --webcam")

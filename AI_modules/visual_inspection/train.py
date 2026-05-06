"""
Train MobileNetV2 classifier for visual inspection (PASS / FAIL)
with transfer learning + fine-tuning.

Key design decisions for this dataset:
  - PASS has only 1 physical sample (s01, 479 images) → strong augmentation
  - FAIL has 6 defect types (1082 images) → moderate augmentation
  - 50/50 batch sampling replaces class_weight (more stable for single-sample minority)
  - Dropout 0.5 + label smoothing to prevent overfitting to s01 surface texture
"""

import os
import argparse
import json
import numpy as np
import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras import layers, models, optimizers, callbacks
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report

# ─── Args ─────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--data-dir",    type=str, default="dataset/split")
parser.add_argument("--output-dir",  type=str, default="models")
parser.add_argument("--image-size",  type=int, default=224)
parser.add_argument("--batch-size",  type=int, default=16,
                    help="Must be even — split equally between PASS and FAIL batches")
parser.add_argument("--epochs",      type=int, default=50)
parser.add_argument("--fine-tune",   type=int, default=30,
                    help="Unfreeze last N layers of MobileNetV2 for fine-tuning")
args = parser.parse_args()

assert args.batch_size % 2 == 0, "--batch-size must be even"
os.makedirs(args.output_dir, exist_ok=True)

IMG_SIZE  = args.image_size
IMG_SHAPE = (IMG_SIZE, IMG_SIZE, 3)
HALF      = args.batch_size // 2   # images per class per batch

TRAIN_DIR = os.path.join(args.data_dir, "train")
VAL_DIR   = os.path.join(args.data_dir, "val")
TEST_DIR  = os.path.join(args.data_dir, "test")

# ─── Augmentation ─────────────────────────────────────────────────────────────
#
# PASS: single physical sample → maximum synthetic diversity
#   - Wide brightness range: simulate condA / condB / condC and transitions
#   - channel_shift_range:   simulate slight white-balance / color cast variations
#   - Larger rotation / zoom: simulate hand-holding variations
#
# FAIL: 6 defect types already provide visual diversity
#   - Moderate augmentation; preserve defect-specific patterns
#

pass_datagen = ImageDataGenerator(
    rescale=1.0 / 255.0,
    rotation_range=40,
    width_shift_range=0.25,
    height_shift_range=0.25,
    shear_range=0.20,
    zoom_range=[0.75, 1.25],
    brightness_range=[0.45, 1.65],
    channel_shift_range=25.0,
    horizontal_flip=True,
    fill_mode="nearest",
)

fail_datagen = ImageDataGenerator(
    rescale=1.0 / 255.0,
    rotation_range=20,
    width_shift_range=0.15,
    height_shift_range=0.15,
    zoom_range=0.15,
    brightness_range=[0.75, 1.30],
    horizontal_flip=True,
    fill_mode="nearest",
)

val_datagen = ImageDataGenerator(rescale=1.0 / 255.0)

# ─── Per-class image generators (no labels — handled in combined_generator) ──

pass_img_gen = pass_datagen.flow_from_directory(
    TRAIN_DIR,
    classes=["PASS"],
    target_size=(IMG_SIZE, IMG_SIZE),
    batch_size=HALF,
    class_mode=None,
    shuffle=True,
    seed=42,
)

fail_img_gen = fail_datagen.flow_from_directory(
    TRAIN_DIR,
    classes=["FAIL"],
    target_size=(IMG_SIZE, IMG_SIZE),
    batch_size=HALF,
    class_mode=None,
    shuffle=True,
    seed=42,
)

# Discover class ordering from val set (alphabetical: FAIL=0, PASS=1)
_ref = val_datagen.flow_from_directory(TRAIN_DIR, batch_size=1,
                                       class_mode="categorical")
class_names   = list(_ref.class_indices.keys())   # ["FAIL", "PASS"]
num_classes   = len(class_names)
PASS_IDX      = _ref.class_indices["PASS"]        # 1
FAIL_IDX      = _ref.class_indices["FAIL"]        # 0
n_train_pass  = pass_img_gen.n
n_train_fail  = fail_img_gen.n
del _ref

print(f"Classes:    {class_names}  (PASS idx={PASS_IDX}, FAIL idx={FAIL_IDX})")
print(f"Train PASS: {n_train_pass}  Train FAIL: {n_train_fail}")

# Fixed one-hot labels
_PASS_LABEL = np.zeros(num_classes, dtype=np.float32); _PASS_LABEL[PASS_IDX] = 1.0
_FAIL_LABEL = np.zeros(num_classes, dtype=np.float32); _FAIL_LABEL[FAIL_IDX] = 1.0

# ─── Combined 50/50 generator ─────────────────────────────────────────────────

def combined_train_generator():
    """Yield batches with equal PASS and FAIL images, shuffled within each batch."""
    while True:
        pass_imgs = next(pass_img_gen)   # (HALF, H, W, 3)
        fail_imgs = next(fail_img_gen)   # (HALF, H, W, 3)
        n_p = len(pass_imgs)
        n_f = len(fail_imgs)
        pass_labels = np.tile(_PASS_LABEL, (n_p, 1))
        fail_labels = np.tile(_FAIL_LABEL, (n_f, 1))
        x = np.concatenate([pass_imgs, fail_imgs], axis=0)
        y = np.concatenate([pass_labels, fail_labels], axis=0)
        perm = np.random.permutation(len(x))
        yield x[perm], y[perm]

# steps_per_epoch: each epoch drains the larger class once
steps_per_epoch = max(n_train_pass, n_train_fail) // HALF

# ─── Val / test generators ────────────────────────────────────────────────────

val_gen = val_datagen.flow_from_directory(
    VAL_DIR,
    target_size=(IMG_SIZE, IMG_SIZE),
    batch_size=args.batch_size,
    class_mode="categorical",
    shuffle=False,
)

test_gen = val_datagen.flow_from_directory(
    TEST_DIR,
    target_size=(IMG_SIZE, IMG_SIZE),
    batch_size=args.batch_size,
    class_mode="categorical",
    shuffle=False,
)

print(f"Val: {val_gen.n}   Test: {test_gen.n}")
print(f"Steps per epoch: {steps_per_epoch}")

# ─── Model ────────────────────────────────────────────────────────────────────

base_model = MobileNetV2(
    input_shape=IMG_SHAPE,
    include_top=False,
    weights="imagenet",
)
base_model.trainable = False

model = models.Sequential([
    base_model,
    layers.GlobalAveragePooling2D(),
    layers.Dropout(0.5),           # higher dropout — prevent overfitting to s01 texture
    layers.Dense(128, activation="relu"),
    layers.Dropout(0.5),
    layers.Dense(num_classes, activation="softmax"),
])

model.compile(
    optimizer=optimizers.Adam(learning_rate=1e-3),
    loss=tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.1),
    metrics=["accuracy"],
)
model.summary()

# ─── Callbacks ────────────────────────────────────────────────────────────────

best_ckpt = os.path.join(args.output_dir, "best_model.h5")

cb = [
    callbacks.EarlyStopping(monitor="val_loss", patience=10,
                            restore_best_weights=True),
    callbacks.ReduceLROnPlateau(monitor="val_loss",
                                factor=0.5, patience=5, min_lr=1e-7),
    callbacks.ModelCheckpoint(best_ckpt, monitor="val_loss",
                              save_best_only=True, verbose=1),
]

# ─── Phase 1: train head only ─────────────────────────────────────────────────

print("\n── Phase 1: training classification head ──")
history = model.fit(
    combined_train_generator(),
    steps_per_epoch=steps_per_epoch,
    validation_data=val_gen,
    epochs=args.epochs,
    callbacks=cb,
)

# ─── Phase 2: fine-tune last N layers of MobileNetV2 ─────────────────────────

print(f"\n── Phase 2: fine-tuning last {args.fine_tune} MobileNetV2 layers ──")
base_model.trainable = True
for layer in base_model.layers[: -args.fine_tune]:
    layer.trainable = False

model.compile(
    optimizer=optimizers.Adam(learning_rate=1e-4),
    loss=tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.1),
    metrics=["accuracy"],
)

fine_history = model.fit(
    combined_train_generator(),
    steps_per_epoch=steps_per_epoch,
    validation_data=val_gen,
    initial_epoch=len(history.epoch),
    epochs=len(history.epoch) + args.fine_tune,
    callbacks=cb,
)

# ─── Plot training history ────────────────────────────────────────────────────

acc     = history.history["accuracy"]     + fine_history.history["accuracy"]
val_acc = history.history["val_accuracy"] + fine_history.history["val_accuracy"]
loss    = history.history["loss"]         + fine_history.history["loss"]
val_loss= history.history["val_loss"]     + fine_history.history["val_loss"]

phase2_start = len(history.epoch)
epochs_range = range(len(acc))

plt.figure(figsize=(12, 4))
plt.subplot(1, 2, 1)
plt.axvline(phase2_start, color="gray", linestyle="--", alpha=0.5, label="Fine-tune start")
plt.plot(epochs_range, acc,     label="Train accuracy")
plt.plot(epochs_range, val_acc, label="Val accuracy")
plt.legend(); plt.title("Accuracy")

plt.subplot(1, 2, 2)
plt.axvline(phase2_start, color="gray", linestyle="--", alpha=0.5, label="Fine-tune start")
plt.plot(epochs_range, loss,     label="Train loss")
plt.plot(epochs_range, val_loss, label="Val loss")
plt.legend(); plt.title("Loss")

plt.tight_layout()
plt.savefig(os.path.join(args.output_dir, "training_history.png"), dpi=150)
plt.close()
print("Saved training_history.png")

# ─── Save model ───────────────────────────────────────────────────────────────

model_path = os.path.join(args.output_dir, "inspection_model.h5")
model.save(model_path)
print(f"Model saved → {model_path}")
print(f"Best checkpoint → {best_ckpt}")

# ─── Evaluate on test set ─────────────────────────────────────────────────────

test_loss, test_acc = model.evaluate(test_gen, verbose=2)
print(f"\nTest loss: {test_loss:.4f}   Test accuracy: {test_acc:.4f}")

y_pred         = model.predict(test_gen)
y_pred_classes = np.argmax(y_pred, axis=1)
y_true         = test_gen.classes

cm = confusion_matrix(y_true, y_pred_classes)
print("Confusion matrix:")
print(cm)

plt.figure(figsize=(5, 4))
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
            xticklabels=class_names, yticklabels=class_names)
plt.title("Confusion Matrix — test set")
plt.ylabel("True"); plt.xlabel("Predicted")
plt.tight_layout()
plt.savefig(os.path.join(args.output_dir, "confusion_matrix.png"), dpi=200)
plt.close()
print("Saved confusion_matrix.png")

report = classification_report(y_true, y_pred_classes, target_names=class_names)
print(report)

with open(os.path.join(args.output_dir, "classification_report.txt"), "w") as f:
    f.write(f"Test loss: {test_loss:.4f}   Test accuracy: {test_acc:.4f}\n\n")
    f.write("Confusion matrix:\n")
    f.write(str(cm))
    f.write("\n\nClassification report:\n")
    f.write(report)

# ─── Metadata ─────────────────────────────────────────────────────────────────

metadata = {
    "class_names":  class_names,
    "num_classes":  num_classes,
    "image_size":   [IMG_SIZE, IMG_SIZE],
    "test_accuracy": round(float(test_acc), 4),
    "model_type":   "MobileNetV2",
    "framework":    "TensorFlow",
    "optimized_for": "Google Coral EdgeTPU",
}
with open(os.path.join(args.output_dir, "model_metadata.json"), "w") as f:
    json.dump(metadata, f, indent=2)

print("\nDone.")

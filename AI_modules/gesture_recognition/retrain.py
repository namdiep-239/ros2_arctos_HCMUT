"""
Retrain MobileNetV2 classifier with transfer learning
Then fine-tune and save .h5 model

Follows Coral TF2 retrain classification tutorial principles
"""

import os
import argparse
import numpy as np
import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras import layers, models, optimizers, callbacks
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

parser = argparse.ArgumentParser()
parser.add_argument("--data-dir", type=str, required=True,
                    help="Root dataset path (with train/val subfolders)")
parser.add_argument("--output-dir", type=str, default="models",
                    help="Output directory for saved models")
parser.add_argument("--image-size", type=int, default=224)
parser.add_argument("--batch-size", type=int, default=32)
parser.add_argument("--epochs", type=int, default=30)
parser.add_argument("--fine-tune", type=int, default=10,
                    help="Fine-tune last N layers of base model")
args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)

IMG_SHAPE = (args.image_size, args.image_size, 3)

# ---------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------

train_datagen = ImageDataGenerator(
    rescale=1.0/255.0,
    rotation_range=25,
    width_shift_range=0.2,
    height_shift_range=0.2,
    shear_range=0.2,
    zoom_range=0.2,
    horizontal_flip=True,
    fill_mode='nearest'
)

val_datagen = ImageDataGenerator(rescale=1.0/255.0)

train_gen = train_datagen.flow_from_directory(
    os.path.join(args.data_dir, "train"),
    target_size=(args.image_size, args.image_size),
    batch_size=args.batch_size,
    class_mode="categorical",
    shuffle=True
)

val_gen = val_datagen.flow_from_directory(
    os.path.join(args.data_dir, "val"),
    target_size=(args.image_size, args.image_size),
    batch_size=args.batch_size,
    class_mode="categorical",
    shuffle=False
)

test_datagen = ImageDataGenerator(rescale=1.0/255.0)

test_gen = test_datagen.flow_from_directory(
    os.path.join(args.data_dir, "internal_test"),
    target_size=(args.image_size, args.image_size),
    batch_size=args.batch_size,
    class_mode="categorical",
    shuffle=False
)

num_classes = train_gen.num_classes
print(f"Training on {num_classes} classes")

# ---------------------------------------------------------------------
# Build model
# ---------------------------------------------------------------------

base_model = MobileNetV2(
    input_shape=IMG_SHAPE,
    include_top=False,
    weights="imagenet"
)
base_model.trainable = False

model = models.Sequential([
    base_model,
    layers.GlobalAveragePooling2D(),
    layers.Dropout(0.3),
    layers.Dense(128, activation="relu"),
    layers.Dropout(0.3),
    layers.Dense(num_classes, activation="softmax")
])

model.compile(
    optimizer=optimizers.Adam(learning_rate=1e-3),
    loss="categorical_crossentropy",
    metrics=["accuracy"]
)

model.summary()

# ---------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------

cb = [
    callbacks.EarlyStopping(monitor="val_loss", patience=5,
                            restore_best_weights=True),
    callbacks.ReduceLROnPlateau(monitor="val_loss",
                                factor=0.5, patience=3, min_lr=1e-6)
]

# ---------------------------------------------------------------------
# Initial train
# ---------------------------------------------------------------------

history = model.fit(
    train_gen,
    validation_data=val_gen,
    epochs=args.epochs,
    callbacks=cb
)

# ---------------------------------------------------------------------
# Fine-tune (unfreeze last layers)
# ---------------------------------------------------------------------

print("Fine-tuning base model...")
base_model.trainable = True
for layer in base_model.layers[:-args.fine_tune]:
    layer.trainable = False

model.compile(
    optimizer=optimizers.Adam(learning_rate=1e-4),
    loss="categorical_crossentropy",
    metrics=["accuracy"]
)

fine_history = model.fit(
    train_gen,
    validation_data=val_gen,
    epochs=args.epochs + args.fine_tune,
    callbacks=cb
)

# ---------------------------------------------------------------------
# Plot training history
# ---------------------------------------------------------------------

# Combine histories
acc = history.history['accuracy'] + fine_history.history['accuracy']
val_acc = history.history['val_accuracy'] + fine_history.history['val_accuracy']
loss = history.history['loss'] + fine_history.history['loss']
val_loss = history.history['val_loss'] + fine_history.history['val_loss']
epochs_range = range(len(acc))

plt.figure(figsize=(12, 4))
plt.subplot(1, 2, 1)
plt.plot(epochs_range, acc, label='Training Accuracy')
plt.plot(epochs_range, val_acc, label='Validation Accuracy')
plt.legend(loc='lower right')
plt.title('Training and Validation Accuracy')

plt.subplot(1, 2, 2)
plt.plot(epochs_range, loss, label='Training Loss')
plt.plot(epochs_range, val_loss, label='Validation Loss')
plt.legend(loc='upper right')
plt.title('Training and Validation Loss')

plt.savefig(os.path.join(args.output_dir, 'training_history.png'))
print("Training history plot saved to training_history.png")

# ---------------------------------------------------------------------
# Save final model
# ---------------------------------------------------------------------

model_path = os.path.join(args.output_dir, "gesture_retrained.h5")
model.save(model_path)
print(f"Model saved to {model_path}")

# ---------------------------------------------------------------------
# Evaluate on test set
# ---------------------------------------------------------------------

test_loss, test_acc = model.evaluate(test_gen, verbose=2)
print(f"Test Loss: {test_loss:.4f}")
print(f"Test Accuracy: {test_acc:.4f}")

# ---------------------------------------------------------------------
# Confusion Matrix and Classification Report
# ---------------------------------------------------------------------

y_pred = model.predict(test_gen)
y_pred_classes = np.argmax(y_pred, axis=1)
y_true = test_gen.classes

cm = confusion_matrix(y_true, y_pred_classes)
print("Confusion Matrix:")
print(cm)

# Plot confusion matrix
plt.figure(figsize=(10, 8))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
            xticklabels=list(test_gen.class_indices.keys()),
            yticklabels=list(test_gen.class_indices.keys()),
            cbar_kws={'label': 'Count'})
plt.title('Confusion Matrix', fontsize=14, fontweight='bold')
plt.ylabel('True label', fontsize=12)
plt.xlabel('Predicted label', fontsize=12)
plt.tight_layout()
plt.savefig(os.path.join(args.output_dir, 'confusion_matrix.png'), dpi=300, bbox_inches='tight')
plt.close()
print("Confusion matrix plot saved to confusion_matrix.png")

report = classification_report(y_true, y_pred_classes, target_names=list(test_gen.class_indices.keys()))
print("Classification Report:")
print(report)

# Save classification report to file
with open(os.path.join(args.output_dir, 'classification_report.txt'), 'w') as f:
    f.write("Test Loss: {:.4f}\n".format(test_loss))
    f.write("Test Accuracy: {:.4f}\n\n".format(test_acc))
    f.write("Confusion Matrix:\n")
    f.write(str(cm))
    f.write("\n\nClassification Report:\n")
    f.write(report)

print("Classification report saved to classification_report.txt")

"""
Hand Gesture Recognition Inference on CPU
Model: gesture_retrained.h5 (raw FP32 model)
Supports both webcam and dataset image inference
"""

import time
import numpy as np
import cv2
import os
import argparse
import json
from pathlib import Path
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report


class GestureCPUInference:
    def __init__(self, model_path, metadata_path=None):
        print("Loading Keras model...")
        self.model = tf.keras.models.load_model(model_path)
        
        self.input_size = (224, 224)
        self.labels = None

        if metadata_path and os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                self.labels = metadata.get("class_names")

        print(f"Model input size: {self.input_size}")
        print(f"Total classes: {len(self.labels) if self.labels else 'Unknown'}")
        print("CPU model ready.")

    def preprocess(self, frame):
        """
        Preprocess image for MobileNetV2 FP32 model
        """
        img = cv2.resize(frame, self.input_size)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Convert to float32 and normalize to [0, 1]
        img = img.astype(np.float32) / 255.0

        return img

    def infer(self, frame):
        """
        Run inference on a single frame
        """
        input_tensor = self.preprocess(frame)
        input_tensor = np.expand_dims(input_tensor, axis=0)

        start = time.perf_counter()
        predictions = self.model.predict(input_tensor, verbose=0)
        latency = (time.perf_counter() - start) * 1000  # ms

        class_id = np.argmax(predictions[0])
        confidence = predictions[0][class_id]
        label = self.labels[class_id] if self.labels else str(class_id)

        return {
            "class_id": class_id,
            "label": label,
            "confidence": float(confidence),
            "latency_ms": latency
        }


def run_webcam_demo(model_path, metadata_path=None, camera_id=0):
    inferencer = GestureCPUInference(model_path, metadata_path)

    cap = cv2.VideoCapture(camera_id)
    assert cap.isOpened(), "Cannot open camera"

    print("Starting real-time gesture inference (press 'q' to quit)...")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        result = inferencer.infer(frame)

        text = f"{result['label']} ({result['confidence']*100:.1f}%) | {result['latency_ms']:.2f} ms"
        cv2.putText(frame, text, (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        cv2.imshow("Gesture Recognition - CPU (FP32)", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


def run_dataset_inference(model_path, metadata_path, dataset_path, output_file=None, charts_dir=None):
    """Run inference on all images in dataset directory"""
    inferencer = GestureCPUInference(model_path, metadata_path)
    
    results = []
    total_latency = 0
    image_count = 0
    
    print(f"Running inference on dataset: {dataset_path}")
    print("=" * 60)
    
    # Iterate through class folders
    class_dirs = sorted([d for d in os.listdir(dataset_path) 
                         if os.path.isdir(os.path.join(dataset_path, d))])
    
    y_true = []
    y_pred = []
    
    for class_name in class_dirs:
        class_path = os.path.join(dataset_path, class_name)
        image_files = sorted([f for f in os.listdir(class_path) 
                             if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        
        print(f"\nClass: {class_name} ({len(image_files)} images)")
        
        correct = 0
        class_results = []
        
        for img_file in image_files:
            img_path = os.path.join(class_path, img_file)
            
            # Read and infer
            frame = cv2.imread(img_path)
            if frame is None:
                print(f"  ⚠ Skipped {img_file} (cannot read)")
                continue
            
            result = inferencer.infer(frame)
            result['image_path'] = img_path
            
            # Normalize ground truth to match label format
            # e.g., "fist-samples" -> "fist", "thumbs_up-samples" -> "thumbs_up"
            ground_truth = class_name.replace("-samples", "").replace("-", "_")
            result['ground_truth'] = ground_truth
            
            # Check if prediction matches ground truth
            predicted_label = result['label'].replace("-", "_").lower()
            result['correct'] = predicted_label == ground_truth
            
            if result['correct']:
                correct += 1
            
            class_results.append(result)
            results.append(result)
            image_count += 1
            total_latency += result['latency_ms']
            
            # Store for confusion matrix
            y_true.append(ground_truth)
            y_pred.append(predicted_label)
            
            # Print progress
            status = "✓" if result['correct'] else "✗"
            print(f"  {status} {img_file}: {result['label']} ({result['confidence']*100:.1f}%) - {result['latency_ms']:.2f}ms")
        
        if image_files:
            accuracy = correct / len(image_files) * 100
            print(f"  Class Accuracy: {accuracy:.1f}% ({correct}/{len(image_files)})")
    
    # Print summary
    print("\n" + "=" * 60)
    print("INFERENCE SUMMARY")
    print("=" * 60)
    
    if image_count > 0:
        correct_total = sum(1 for r in results if r['correct'])
        avg_latency = total_latency / image_count
        overall_accuracy = correct_total / image_count * 100
        
        print(f"Total images processed: {image_count}")
        print(f"Overall Accuracy: {overall_accuracy:.2f}% ({correct_total}/{image_count})")
        print(f"Average Latency: {avg_latency:.2f} ms")
        print(f"Total Time: {total_latency/1000:.2f} s")
    
    # Save results to JSON if requested
    if output_file:
        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # Convert numpy types to native Python types for JSON serialization
        results_serializable = []
        for r in results:
            r_copy = r.copy()
            r_copy['class_id'] = int(r_copy['class_id'])
            r_copy['confidence'] = float(r_copy['confidence'])
            r_copy['latency_ms'] = float(r_copy['latency_ms'])
            results_serializable.append(r_copy)
        
        with open(output_file, 'w') as f:
            json.dump(results_serializable, f, indent=2)
        print(f"\nResults saved to: {output_file}")
    
    # Generate charts if requested
    if charts_dir and image_count > 0:
        os.makedirs(charts_dir, exist_ok=True)
        
        # Get unique class names in order
        unique_classes = sorted(set(y_true))
        
        # Confusion Matrix
        print("\nGenerating confusion matrix...")
        cm = confusion_matrix(y_true, y_pred, labels=unique_classes)
        
        plt.figure(figsize=(10, 8))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                   xticklabels=unique_classes, yticklabels=unique_classes,
                   cbar_kws={'label': 'Count'})
        plt.title('Confusion Matrix - CPU FP32 Model', fontsize=14, fontweight='bold')
        plt.ylabel('True label', fontsize=12)
        plt.xlabel('Predicted label', fontsize=12)
        plt.tight_layout()
        
        cm_path = os.path.join(charts_dir, 'confusion_matrix.png')
        plt.savefig(cm_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  Saved: {cm_path}")
        
        # Per-class Accuracy
        print("Generating per-class accuracy chart...")
        class_accuracies = {}
        for i, cls in enumerate(unique_classes):
            if cm[i].sum() > 0:
                class_accuracies[cls] = cm[i, i] / cm[i].sum() * 100
            else:
                class_accuracies[cls] = 0.0
        
        plt.figure(figsize=(10, 6))
        classes = list(class_accuracies.keys())
        accuracies = list(class_accuracies.values())
        
        bars = plt.bar(classes, accuracies, color='steelblue', alpha=0.7)
        plt.axhline(y=overall_accuracy, color='r', linestyle='--', label=f'Overall: {overall_accuracy:.2f}%')
        plt.ylabel('Accuracy (%)')
        plt.title('Per-Class Accuracy - CPU FP32 Model')
        plt.ylim(0, 105)
        plt.legend()
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%', ha='center', va='bottom')
        
        plt.tight_layout()
        accuracy_path = os.path.join(charts_dir, 'per_class_accuracy.png')
        plt.savefig(accuracy_path, dpi=100, bbox_inches='tight')
        plt.close()
        print(f"  Saved: {accuracy_path}")
        
        # Classification Report
        print("Generating classification report...")
        report = classification_report(y_true, y_pred, target_names=unique_classes)
        
        report_path = os.path.join(charts_dir, 'classification_report.txt')
        with open(report_path, 'w') as f:
            f.write("CLASSIFICATION REPORT - CPU FP32 MODEL\n")
            f.write("=" * 60 + "\n")
            f.write(f"Overall Accuracy: {overall_accuracy:.2f}% ({correct_total}/{image_count})\n")
            f.write(f"Average Latency: {avg_latency:.2f} ms\n")
            f.write("=" * 60 + "\n\n")
            f.write(report)
        print(f"  Saved: {report_path}")
        
        print(f"\nAll charts saved to: {charts_dir}")
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hand Gesture Recognition Inference on CPU (FP32)")
    parser.add_argument("--model", default="models/gesture_retrained.h5",
                        help="Path to Keras .h5 model")
    parser.add_argument("--metadata", default="models/model_metadata.json",
                        help="Path to model metadata JSON")
    parser.add_argument("--mode", choices=["webcam", "dataset"], default="webcam",
                        help="Inference mode: webcam or dataset")
    parser.add_argument("--dataset", help="Path to dataset folder for dataset mode")
    parser.add_argument("--camera-id", type=int, default=0,
                        help="Camera ID for webcam mode (default: 0)")
    parser.add_argument("--output", help="Output JSON file to save results (dataset mode only)")
    parser.add_argument("--charts", help="Output directory for charts (confusion matrix, per-class accuracy)")
    
# python3 ./inference_testing_cpu.py --mode dataset --dataset ./dataset/internal_test --output ./results/internal_cpu.json --charts ./results/internal_cpu/
# python3 ./inference_testing_cpu.py --mode dataset --dataset ./dataset/external_test --output ./results/external_cpu.json --charts ./results/external_cpu/

    args = parser.parse_args()
    
    # Check if model exists
    if not os.path.exists(args.model):
        print(f"ERROR: Model not found at {args.model}")
        exit(1)
    
    # Check if metadata exists
    if not os.path.exists(args.metadata):
        print(f"WARNING: Metadata not found at {args.metadata}")
        args.metadata = None
    
    if args.mode == "webcam":
        print("=" * 60)
        print("MODE: Webcam Inference (CPU - FP32)")
        print("=" * 60)
        run_webcam_demo(args.model, args.metadata, args.camera_id)
    
    elif args.mode == "dataset":
        if not args.dataset:
            print("ERROR: --dataset argument required for dataset mode")
            exit(1)
        
        if not os.path.isdir(args.dataset):
            print(f"ERROR: Dataset path not found: {args.dataset}")
            exit(1)
        
        print("=" * 60)
        print("MODE: Dataset Inference (CPU - FP32)")
        print("=" * 60)
        run_dataset_inference(args.model, args.metadata, args.dataset, args.output, args.charts)

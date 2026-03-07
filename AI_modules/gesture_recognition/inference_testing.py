"""
Hand Gesture Recognition Inference on Google Coral EdgeTPU
Model: gesture_model_quantized_edgetpu.tflite
Supports both webcam and dataset image inference
"""

import time
import numpy as np
import cv2
import os
import argparse
import json
from pathlib import Path
from pycoral.utils.edgetpu import make_interpreter
from pycoral.adapters import common, classify
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report


class GestureEdgeTPUInference:
    def __init__(self, model_path, metadata_path=None):
        print("Initializing EdgeTPU Interpreter...")
        self.interpreter = make_interpreter(model_path)
        self.interpreter.allocate_tensors()

        self.input_size = common.input_size(self.interpreter)
        self.labels = None

        if metadata_path:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                self.labels = metadata.get("class_names")

        print(f"Model input size: {self.input_size}")
        print("EdgeTPU ready.")

    def preprocess(self, frame):
        """
        Preprocess image for MobileNetV2 INT8 model
        """
        img = cv2.resize(frame, self.input_size)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Convert to uint8 (EdgeTPU expects uint8)
        img = img.astype(np.uint8)

        return img

    def infer(self, frame):
        """
        Run inference on a single frame
        """
        input_tensor = self.preprocess(frame)

        common.set_input(self.interpreter, input_tensor)
        
        start = time.perf_counter()
        self.interpreter.invoke()
        latency = (time.perf_counter() - start) * 1000  # ms

        classes = classify.get_classes(self.interpreter, top_k=1)

        if classes:
            class_id = classes[0].id
            score = classes[0].score
            label = self.labels[class_id] if self.labels else str(class_id)
        else:
            class_id, score, label = -1, 0.0, "Unknown"

        return {
            "class_id": class_id,
            "label": label,
            "confidence": score,
            "latency_ms": latency
        }


def run_webcam_demo(model_path, metadata_path=None, camera_id=0):
    inferencer = GestureEdgeTPUInference(model_path, metadata_path)

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

        cv2.imshow("Gesture Recognition - EdgeTPU", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


def run_dataset_inference(model_path, metadata_path, dataset_path, output_file=None, chart_dir=None):
    """Run inference on all images in dataset directory"""
    inferencer = GestureEdgeTPUInference(model_path, metadata_path)
    
    results = []
    total_latency = 0
    image_count = 0
    
    print(f"Running inference on dataset: {dataset_path}")
    print("=" * 60)
    
    # Iterate through class folders
    class_dirs = sorted([d for d in os.listdir(dataset_path) 
                         if os.path.isdir(os.path.join(dataset_path, d))])
    
    # Store for analysis
    y_true = []
    y_pred = []
    class_accuracy_dict = {}
    
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
            class_accuracy_dict[ground_truth] = accuracy
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
    if chart_dir and len(y_true) > 0:
        os.makedirs(chart_dir, exist_ok=True)
        
        # Get unique classes sorted
        classes = sorted(list(set(y_true)))
        
        # 1. Confusion Matrix
        print("\nGenerating confusion matrix chart...")
        cm = confusion_matrix(y_true, y_pred, labels=classes)
        
        plt.figure(figsize=(10, 8))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                   xticklabels=classes, yticklabels=classes,
                   cbar_kws={'label': 'Count'})
        plt.title('Confusion Matrix - EdgeTPU Inference')
        plt.ylabel('Ground Truth')
        plt.xlabel('Predicted Label')
        plt.tight_layout()
        cm_path = os.path.join(chart_dir, 'confusion_matrix.png')
        plt.savefig(cm_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  Saved to: {cm_path}")
        
        # 2. Per-Class Accuracy
        print("Generating per-class accuracy chart...")
        class_names = sorted(class_accuracy_dict.keys())
        accuracies = [class_accuracy_dict[c] for c in class_names]
        
        plt.figure(figsize=(10, 6))
        bars = plt.bar(class_names, accuracies, color='steelblue', edgecolor='navy', linewidth=1.5)
        plt.ylabel('Accuracy (%)', fontsize=12)
        plt.xlabel('Gesture Class', fontsize=12)
        plt.title('Per-Class Accuracy - EdgeTPU Inference', fontsize=14, fontweight='bold')
        plt.ylim([0, 105])
        plt.xticks(rotation=45, ha='right')
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')
        
        plt.grid(axis='y', alpha=0.3, linestyle='--')
        plt.tight_layout()
        acc_path = os.path.join(chart_dir, 'per_class_accuracy.png')
        plt.savefig(acc_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  Saved to: {acc_path}")
        
        # 3. Classification Report
        print("Generating classification report...")
        class_report = classification_report(y_true, y_pred, target_names=classes, 
                                            digits=4, output_dict=False)
        
        report_path = os.path.join(chart_dir, 'classification_report.txt')
        with open(report_path, 'w') as f:
            f.write("Classification Report - EdgeTPU Inference\n")
            f.write("=" * 60 + "\n\n")
            f.write(class_report)
        print(f"  Saved to: {report_path}")
        
        # 4. Summary Statistics
        print("Generating summary statistics...")
        summary_path = os.path.join(chart_dir, 'inference_summary.txt')
        with open(summary_path, 'w') as f:
            f.write("INFERENCE SUMMARY\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Total images processed: {image_count}\n")
            f.write(f"Overall Accuracy: {overall_accuracy:.2f}% ({correct_total}/{image_count})\n")
            f.write(f"Average Latency: {avg_latency:.2f} ms\n")
            f.write(f"Total Time: {total_latency/1000:.2f} s\n\n")
            f.write("Per-Class Accuracy:\n")
            for cls in sorted(class_accuracy_dict.keys()):
                f.write(f"  {cls}: {class_accuracy_dict[cls]:.2f}%\n")
        print(f"  Saved to: {summary_path}")
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hand Gesture Recognition Inference")
    parser.add_argument("--model", default="models/gesture_retrained_int8_edgetpu.tflite",
                        help="Path to EdgeTPU TFLite model")
    parser.add_argument("--metadata", default="models/model_metadata.json",
                        help="Path to model metadata JSON")
    parser.add_argument("--mode", choices=["webcam", "dataset"], default="webcam",
                        help="Inference mode: webcam or dataset")
    parser.add_argument("--dataset", help="Path to dataset folder for dataset mode")
    parser.add_argument("--camera-id", type=int, default=0,
                        help="Camera ID for webcam mode (default: 0)")
    parser.add_argument("--output", help="Output JSON file to save results (dataset mode only)")
    parser.add_argument("--charts", help="Directory to save visualization charts (dataset mode only)")
    
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
        print("MODE: Webcam Inference")
        print("=" * 60)
        run_webcam_demo(args.model, args.metadata, args.camera_id)
    
    elif args.mode == "dataset":
        if not args.dataset:
            print("ERROR: --dataset argument required for dataset mode")
            exit(1)
        
        if not os.path.isdir(args.dataset):
            print(f"ERROR: Dataset path not found: {args.dataset}")
            exit(1)
        
        # Set default chart directory if not specified
        if not args.charts and args.output:
            args.charts = os.path.join(os.path.dirname(args.output), "charts")
        
        print("=" * 60)
        print("MODE: Dataset Inference")
        print("=" * 60)
        run_dataset_inference(args.model, args.metadata, args.dataset, args.output, args.charts)

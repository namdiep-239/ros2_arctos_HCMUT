# Hand Gesture Recognition with Google Coral EdgeTPU

A machine learning project for real-time hand gesture recognition using TensorFlow Lite models optimized for Google Coral EdgeTPU devices.

## Project Overview

This project implements hand gesture recognition for 5 different gestures:
- **Fist** - Closed fist
- **Open** - Open hand
- **Point** - Pointing gesture
- **Thumbs Up** - Thumbs up gesture
- **None** - No gesture detected

The system supports:
- Real-time inference via webcam
- Batch inference on dataset images
- Model conversion and quantization for EdgeTPU
- Comprehensive performance metrics and visualizations

## Project Structure

```
gesture_final/
├── models/                          # Pre-trained models
│   ├── gesture_retrained.h5         # Original Keras model
│   ├── gesture_retrained_int8.tflite         # Standard TFLite model
│   ├── gesture_retrained_int8_edgetpu.tflite # EdgeTPU optimized model
│   └── model_metadata.json          # Model metadata
│
├── dataset/                         # Training/validation/test data
│   ├── train/                       # Training dataset
│   ├── val/                         # Validation dataset
│   ├── internal_test/               # Internal test set
│   └── external_test/               # External test set
│
├── results/                         # Inference results and metrics
│   ├── internal_cpu/                # CPU inference results
│   ├── internal_edgetpu/            # EdgeTPU inference results
│   ├── external_cpu/                
│   └── external_edgetpu/
│
├── inference_testing.py             # EdgeTPU inference with visualizations
├── inference_testing_cpu.py         # CPU inference testing
├── retrain.py                       # Model retraining script
├── convert_to_tflite.py             # Model conversion to TFLite
├── compare_raw_vs_tflite.py         # Compare performance metrics
└── split_train_to_train_val_test.py # Dataset splitting utility
```

## Installation

### Requirements
- Python 3.8+
- TensorFlow 2.x
- OpenCV
- NumPy, Matplotlib, Seaborn
- scikit-learn
- pycoral (for EdgeTPU support)

### Setup

```bash
# Clone/download the project
cd gesture_final

# Install dependencies
pip install tensorflow opencv-python numpy matplotlib seaborn scikit-learn

# For EdgeTPU support (Linux/Raspberry Pi):
pip install pycoral

# Or on Raspberry Pi:
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" | sudo tee /etc/apt/sources.list.d/coral-edgetpu.list
sudo apt-get update
sudo apt-get install python3-pycoral
```

## Usage

### Real-time Gesture Recognition (Webcam)

```bash
# Using EdgeTPU (requires Coral device)
python inference_testing.py --mode webcam \
    --model models/gesture_retrained_int8_edgetpu.tflite \
    --metadata models/model_metadata.json

# Using CPU
python inference_testing_cpu.py --mode webcam \
    --model models/gesture_retrained_int8.tflite \
    --metadata models/model_metadata.json
```

### Dataset Inference

```bash
# Test on internal test set with EdgeTPU
python inference_testing.py --mode dataset \
    --model models/gesture_retrained_int8_edgetpu.tflite \
    --metadata models/model_metadata.json \
    --dataset dataset/internal_test \
    --output results/internal_edgetpu.json \
    --charts results/internal_edgetpu/

# Test on external test set with CPU
python inference_testing_cpu.py --mode dataset \
    --model models/gesture_retrained_int8.tflite \
    --metadata models/model_metadata.json \
    --dataset dataset/external_test \
    --output results/external_cpu.json \
    --charts results/external_cpu/
```

### Model Retraining

```bash
python retrain.py --dataset dataset/train \
                  --validation dataset/val \
                  --epochs 50 \
                  --output models/gesture_retrained.h5
```

### Convert Model to TFLite

```bash
python convert_to_tflite.py --input models/gesture_retrained.h5 \
                            --output models/gesture_retrained_int8.tflite \
                            --quantization int8
```

## Key Features

- **Real-time Inference**: Process webcam frames at >30 FPS with EdgeTPU
- **Multiple Backends**: Support for CPU and EdgeTPU inference
- **Comprehensive Metrics**: 
  - Confusion matrices
  - Per-class accuracy
  - Classification reports
  - Latency measurements
- **Model Optimization**: INT8 quantization for faster inference
- **Visualization**: Automatic generation of performance charts

## Performance

### EdgeTPU Inference
- **Latency**: ~5-10ms per frame
- **Accuracy**: 95%+ on validation set
- **Power Consumption**: Minimal with dedicated accelerator

### CPU Inference
- **Latency**: ~30-50ms per frame
- **Accuracy**: Same as EdgeTPU (same model)
- **Compatibility**: Runs on any platform with TensorFlow

## Model Architecture

The model is based on **MobileNetV2** fine-tuned for gesture recognition:
- Input size: 224×224 RGB
- Output: 5-class classification
- Quantization: INT8 for optimized inference
- Total model size: ~4.5 MB

## Results

Test results are saved in the `results/` directory with:
- JSON files containing per-image predictions
- Confusion matrix visualizations
- Classification reports
- Summary statistics

## Hardware Requirements

### CPU Mode
- Any machine with Python and TensorFlow

### EdgeTPU Mode
- Google Coral USB Accelerator or
- Google Coral Dev Board or
- Raspberry Pi with Coral Module

## Troubleshooting

### EdgeTPU Device Not Found
```bash
# Check device connection
lsusb | grep Coral

# Install required drivers
sudo apt-get install libedgetpu1-std
```

### Model Loading Errors
- Ensure model file paths are correct
- Verify model format (EdgeTPU models must be .tflite)
- Check metadata.json is in same directory as model

### Poor Recognition Performance
- Check lighting conditions
- Ensure gestures are clearly visible
- Verify dataset quality
- Consider retraining with more diverse samples

## Citation

If you use this project in your research, please cite:
```
@misc{gesture_recognition_2024,
  title={Hand Gesture Recognition with Google Coral EdgeTPU},
  author={},
  year={2024}
}
```

## License

This project is provided as-is for educational and research purposes.

## Contact

For questions or issues, please open an issue on the repository.

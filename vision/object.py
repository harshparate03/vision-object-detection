import os
import sys
import time
import logging
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Tuple, List, Optional, Union
from urllib.request import urlretrieve

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("YOLODetector")

class YOLODetector:
    """
    YOLOv8 detector with support for multiple pre-trained models
    """
    
    # Available pre-trained YOLOv8 models
    AVAILABLE_MODELS = {
        'yolov8n': {
            'url': 'https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt',
            'description': 'YOLOv8 Nano - fastest, smallest model (3.2 MB)'
        },
        'yolov8s': {
            'url': 'https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8s.pt',
            'description': 'YOLOv8 Small - good balance of speed/accuracy (11.2 MB)'
        },
        'yolov8m': {
            'url': 'https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8m.pt',
            'description': 'YOLOv8 Medium - better accuracy, still reasonable speed (25.9 MB)'
        },
        'yolov8l': {
            'url': 'https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8l.pt',
            'description': 'YOLOv8 Large - high accuracy, slower inference (43.7 MB)'
        },
        'yolov8x': {
            'url': 'https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8x.pt',
            'description': 'YOLOv8 XLarge - highest accuracy, slowest (68.2 MB)'
        }
    }
    
    def __init__(
        self,
        model_name: str = 'yolov8n',
        confidence: float = 0.35,
        iou_threshold: float = 0.45,
        img_size: int = 640,
        device: Optional[str] = None,
        models_dir: str = 'models'
    ):
        """
        Initialize YOLOv8 detector
        
        Args:
            model_name: Name of model to use ('yolov8n', 'yolov8s', 'yolov8m', 'yolov8l', 'yolov8x')
            confidence: Detection confidence threshold (0.01-1.0)
            iou_threshold: IoU threshold for NMS (0.01-1.0)
            img_size: Image size for inference (multiple of 32)
            device: Computing device ('cuda', 'cpu', or None for auto-detection)
            models_dir: Directory to store/load models
        """
        # Create models directory if it doesn't exist
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Auto-detect device if not specified
        if device is None:
            import torch
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        else:
            self.device = device
            
        logger.info(f"Using device: {self.device}")
        
        # Store parameters
        self.confidence = confidence
        self.iou_threshold = iou_threshold
        self.img_size = img_size
        self.model_name = model_name
        
        # Load the model
        self.model_path = self._get_model(model_name)
        self._load_model()
        
        # Generate color palette for visualization
        self.colors = self._generate_colors(len(self.model.names))
        
        # Track performance metrics
        self.inference_times = []
        self.avg_inference_time = 0
        self.frame_count = 0
        
    def _load_model(self):
        import torch
        """Load the YOLO model"""
        try:
            # Import YOLO here to avoid import errors if missing
            from ultralytics import YOLO
            
            logger.info(f"Loading YOLOv8 model: {self.model_path}")
            self.model = YOLO(self.model_path)
            self.model.to(self.device)
            
            # Enable optimizations if using CUDA
            if self.device == 'cuda':
                logger.info("Enabling CUDA optimizations")
                torch.backends.cudnn.benchmark = True
            
            # Store model info
            self.class_names = self.model.names
            logger.info(f"Model loaded with {len(self.class_names)} classes")
            logger.info(f"Class names: {', '.join(list(self.class_names.values())[:10])}...")
            
        except ImportError:
            logger.error("Failed to import ultralytics YOLO. Please install with: pip install ultralytics")
            raise
        except Exception as e:
            logger.error(f"Model loading failed: {e}")
            raise
    
    def _get_model(self, model_name: str) -> str:
        """
        Get the model file path, downloading if necessary
        
        Args:
            model_name: Name of model to use
            
        Returns:
            Path to model file
        """
        # Handle full paths to custom models
        if os.path.isfile(model_name):
            return model_name
            
        # Handle standard model names
        if model_name in self.AVAILABLE_MODELS:
            model_file = self.models_dir / f"{model_name}.pt"
            
            # Download if model doesn't exist
            if not model_file.exists():
                url = self.AVAILABLE_MODELS[model_name]['url']
                logger.info(f"Downloading {model_name} from {url}")
                
                try:
                    # Create progress indicator
                    def progress_callback(blocks, block_size, total_size):
                        downloaded = blocks * block_size
                        percent = min(100, int(downloaded * 100 / total_size))
                        sys.stdout.write(f"\rDownloading: {percent}% [{downloaded} / {total_size}]")
                        sys.stdout.flush()
                    
                    # Download the model file
                    urlretrieve(url, model_file, progress_callback)
                    print()  # New line after progress
                    logger.info(f"Download complete: {model_file}")
                except Exception as e:
                    logger.error(f"Download failed: {e}")
                    raise
            
            return str(model_file)
        else:
            # List available models for error message
            available = ", ".join(self.AVAILABLE_MODELS.keys())
            raise ValueError(f"Unknown model: {model_name}. Available models: {available}")
    
    def _generate_colors(self, num_classes: int) -> List[Tuple[int, int, int]]:
        """Generate distinct colors for visualization"""
        np.random.seed(42)  # For reproducibility
        
        # Generate visually distinct colors (HSV space for better distinction)
        colors = []
        for i in range(num_classes):
            # Generate evenly spaced hues, with good saturation and value
            h = i / num_classes
            s = 0.8
            v = 0.9
            
            # Convert HSV to RGB
            r, g, b = self._hsv_to_rgb(h, s, v)
            colors.append((int(r * 255), int(g * 255), int(b * 255)))
            
        return colors
    
    def _hsv_to_rgb(self, h, s, v):
        """Convert HSV color to RGB color"""
        if s == 0.0:
            return v, v, v
            
        i = int(h * 6)
        f = (h * 6) - i
        p = v * (1 - s)
        q = v * (1 - s * f)
        t = v * (1 - s * (1 - f))
        
        i %= 6
        
        if i == 0:
            return v, t, p
        elif i == 1:
            return q, v, p
        elif i == 2:
            return p, v, t
        elif i == 3:
            return p, q, v
        elif i == 4:
            return t, p, v
        else:
            return v, p, q
    
    def detect_objects(
        self, 
        frame: np.ndarray,
        classes: Optional[List[int]] = None,
        draw_boxes: bool = True,
        draw_stats: bool = True
    ) -> Tuple[np.ndarray, Dict[str, int], List[Dict]]:
        """
        Detect objects in a frame
        
        Args:
            frame: Input image/frame (numpy array)
            classes: List of class IDs to detect (None for all classes)
            draw_boxes: Whether to draw bounding boxes on the frame
            draw_stats: Whether to draw performance stats on the frame
            
        Returns:
            annotated_frame: Frame with bounding boxes drawn
            detected_objects: Dictionary with object counts
            detections: List of detection results (class, confidence, bbox)
        """
        try:
            # Ensure frame is valid
            if frame is None or frame.size == 0:
                logger.warning("Empty frame received")
                return frame, {}, []
            
            # Create a copy if drawing is enabled
            annotated_frame = frame.copy() if draw_boxes else frame
            
            # Measure inference time
            start_time = time.time()
            
            # Run inference
            results = self.model(
                frame, 
                conf=self.confidence,
                iou=self.iou_threshold,
                max_det=100,
                imgsz=self.img_size,
                verbose=False,
                classes=classes  # Filter by class IDs if specified
            )
            
            # Calculate inference time
            inference_time = time.time() - start_time
            self.inference_times.append(inference_time)
            self.frame_count += 1
            
            # Update running average (with decay)
            if len(self.inference_times) > 100:
                self.inference_times.pop(0)  # Keep last 100 frames
            self.avg_inference_time = sum(self.inference_times) / len(self.inference_times)
            
            # Dictionary to store detection counts
            detected_objects = {}
            
            # List to store detection details
            detections = []
            
            # Process each detection
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Extract detection info
                    cls_id = int(box.cls[0])
                    label = self.class_names[cls_id]
                    conf = float(box.conf[0])
                    
                    # Get bounding box coordinates
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # Count detections by class
                    detected_objects[label] = detected_objects.get(label, 0) + 1
                    
                    # Add to detections list
                    detections.append({
                        'class_id': cls_id,
                        'class_name': label,
                        'confidence': conf,
                        'bbox': (x1, y1, x2, y2)
                    })
                    
                    # Draw bounding box if enabled
                    if draw_boxes:
                        # Get color for this class
                        color = self.colors[cls_id]
                        
                        # Draw bounding box
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                        
                        # Prepare label with confidence
                        text = f"{label} {conf:.2f}"
                        
                        # Get text size for background
                        (text_width, text_height), baseline = cv2.getTextSize(
                            text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2
                        )
                        
                        # Draw label background
                        cv2.rectangle(
                            annotated_frame, 
                            (x1, y1 - text_height - 10), 
                            (x1 + text_width, y1), 
                            color, 
                            -1  # Filled rectangle
                        )
                        
                        # Draw label text (white for better contrast)
                        cv2.putText(
                            annotated_frame, text,
                            (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                            (255, 255, 255), 2
                        )
            
            # Draw performance stats if enabled
            if draw_stats and draw_boxes:
                fps = 1.0 / (inference_time + 1e-9)  # Avoid division by zero
                
                # Add FPS counter
                cv2.putText(
                    annotated_frame,
                    f"FPS: {fps:.1f}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1, (0, 255, 0), 2
                )
                
                # Add device info
                cv2.putText(
                    annotated_frame,
                    f"Device: {self.device}",
                    (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 255, 0), 2
                )
                
                # Add model info
                cv2.putText(
                    annotated_frame,
                    f"Model: {self.model_name}",
                    (10, 100),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 255, 0), 2
                )
                
                # Add detection counts
                if detected_objects:
                    y_pos = 130
                    for label, count in detected_objects.items():
                        cv2.putText(
                            annotated_frame,
                            f"{label}: {count}",
                            (10, y_pos),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 255, 0), 2
                        )
                        y_pos += 30
            
            return annotated_frame, detected_objects, detections
            
        except Exception as e:
            logger.error(f"Error in detection: {e}")
            return frame, {}, []

    def get_available_models(self) -> Dict[str, Dict]:
        """
        Get information about available pre-trained models
        
        Returns:
            Dictionary of model information
        """
        return self.AVAILABLE_MODELS
    
    def process_image(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        classes: Optional[List[int]] = None,
        show_result: bool = False
    ) -> Tuple[str, Dict[str, int]]:
        """
        Process a single image file
        
        Args:
            image_path: Path to input image
            output_path: Path to save output image (None for auto)
            classes: List of class IDs to detect (None for all)
            show_result: Whether to display the result
            
        Returns:
            Tuple of (output path, detected objects)
        """
        try:
            # Read image
            logger.info(f"Processing image: {image_path}")
            image = cv2.imread(image_path)
            
            if image is None:
                raise ValueError(f"Could not read image: {image_path}")
            
            # Process image
            annotated_image, detected_objects, _ = self.detect_objects(
                image, 
                classes=classes
            )
            
            # Determine output path
            if output_path is None:
                # Auto-generate output filename
                input_path = Path(image_path)
                output_dir = input_path.parent / "detections"
                output_dir.mkdir(exist_ok=True)
                output_path = str(output_dir / f"{input_path.stem}_detected{input_path.suffix}")
            
            # Save output image
            cv2.imwrite(output_path, annotated_image)
            logger.info(f"Saved result to: {output_path}")
            
            # Display results summary
            for label, count in detected_objects.items():
                logger.info(f"- {label}: {count}")
            
            # Show result if requested
            if show_result:
                cv2.imshow("YOLOv8 Detection", annotated_image)
                cv2.waitKey(0)
                cv2.destroyAllWindows()
            
            return output_path, detected_objects
            
        except Exception as e:
            logger.error(f"Image processing error: {e}")
            raise
    
    def process_video(
        self,
        source: Union[str, int],
        output_path: Optional[str] = None,
        classes: Optional[List[int]] = None,
        show_result: bool = False,
        progress_callback: Optional[callable] = None
    ) -> str:
        """
        Process video file or camera stream
        
        Args:
            source: Path to video file or camera index
            output_path: Path to save output video (None for auto)
            classes: List of class IDs to detect (None for all)
            show_result: Whether to display result in real-time
            progress_callback: Optional callback function to report progress (0-100)
            
        Returns:
            Path to output video file
        """
        try:
            # Handle numeric camera index
            if isinstance(source, str) and source.isdigit():
                source = int(source)
            
            # Open video source
            logger.info(f"Opening video source: {source}")
            cap = cv2.VideoCapture(source)
            
            if not cap.isOpened():
                raise ValueError(f"Could not open video source: {source}")
            
            # Get video properties
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(cap.get(cv2.CAP_PROP_FPS) or 30)  # Default to 30 if reading fails
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or -1
            
            logger.info(f"Video properties: {width}x{height}, {fps} FPS, {total_frames} frames")
            
            # Determine output path
            if output_path is None:
                # Auto-generate output filename
                output_dir = Path("detections")
                output_dir.mkdir(exist_ok=True)
                
                if isinstance(source, int):
                    output_path = str(output_dir / f"camera_{source}_detected.mp4")
                else:
                    input_path = Path(source)
                    output_path = str(output_dir / f"{input_path.stem}_detected.mp4")
            
            logger.info(f"Output will be saved to: {output_path}")
            
            # Initialize video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Use 'avc1' for better compatibility
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            
            if not writer.isOpened():
                raise RuntimeError(f"Failed to open VideoWriter for: {output_path}")
            
            # Process frames
            frame_idx = 0
            detection_stats = {}
            start_time = time.time()
            
            while True:
                # Read frame
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Process frame
                annotated_frame, detections, _ = self.detect_objects(
                    frame,
                    classes=classes
                )
                
                # Update detection stats
                for obj, count in detections.items():
                    if obj not in detection_stats:
                        detection_stats[obj] = []
                    detection_stats[obj].append(count)
                
                # Write frame to output
                writer.write(annotated_frame)
                
                # Display if requested
                if show_result:
                    cv2.imshow("YOLOv8 Detection", annotated_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                
                # Update progress
                frame_idx += 1
                if total_frames > 0 and progress_callback:
                    progress = min(100, int(frame_idx * 100 / total_frames))
                    progress_callback(progress)
                
                # Log progress for long videos
                if frame_idx % 100 == 0:
                    elapsed = time.time() - start_time
                    avg_fps = frame_idx / elapsed
                    logger.info(f"Processed {frame_idx} frames ({avg_fps:.1f} FPS)")
            
            # Clean up
            cap.release()
            writer.release()
            if show_result:
                cv2.destroyAllWindows()
            
            # Calculate statistics
            elapsed_time = time.time() - start_time
            avg_fps = frame_idx / elapsed_time
            
            logger.info(f"Video processing complete:")
            logger.info(f"- Processed {frame_idx} frames in {elapsed_time:.1f} seconds")
            logger.info(f"- Average FPS: {avg_fps:.1f}")
            
            # Log detection statistics
            logger.info("Detection statistics:")
            for obj_class, counts in detection_stats.items():
                avg_count = sum(counts) / len(counts)
                max_count = max(counts)
                logger.info(f"- {obj_class}: Avg: {avg_count:.1f}, Max: {max_count}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Video processing error: {e}")
            raise

# Create a singleton detector instance
_detector_instance = None

def get_detector(
    model_name: str = 'yolov8n',
    confidence: float = 0.35,
    iou_threshold: float = 0.45,
    img_size: int = 640,
    device: Optional[str] = None
) -> YOLODetector:
    """
    Get or create a YOLODetector instance
    
    Args:
        model_name: Model name or path
        confidence: Detection confidence threshold
        iou_threshold: IoU threshold for NMS
        img_size: Image size for inference
        device: Computing device
        
    Returns:
        YOLODetector instance
    """
    global _detector_instance
    
    # Create new detector if not yet created or parameters changed
    if _detector_instance is None:
        _detector_instance = YOLODetector(
            model_name=model_name,
            confidence=confidence,
            iou_threshold=iou_threshold,
            img_size=img_size,
            device=device
        )
    
    return _detector_instance

def detect_objects(
    frame: np.ndarray,
    model_name: str = 'yolov8n',
    confidence: float = 0.35,
    iou_threshold: float = 0.45,
    img_size: int = 640,
    classes: Optional[List[int]] = None
) -> Tuple[np.ndarray, Dict[str, int]]:
    """
    Detect objects in a frame (main function to be imported)
    
    Args:
        frame: Input image/frame
        model_name: Model name or path
        confidence: Detection confidence threshold
        iou_threshold: IoU threshold for NMS
        img_size: Image size for inference
        classes: List of class IDs to detect
        
    Returns:
        Tuple of (annotated frame, object counts)
    """
    detector = get_detector(
        model_name=model_name, 
        confidence=confidence,
        iou_threshold=iou_threshold,
        img_size=img_size
    )
    
    annotated_frame, detected_objects, _ = detector.detect_objects(
        frame,
        classes=classes
    )
    
    return annotated_frame, detected_objects

def get_available_models() -> Dict[str, Dict]:
    """
    Get information about available pre-trained models
    
    Returns:
        Dictionary of model information
    """
    return YOLODetector.AVAILABLE_MODELS

def print_available_models():
    """Print information about available pre-trained models"""
    models = get_available_models()
    print("\nAvailable pre-trained YOLOv8 models:")
    print("-" * 50)
    for name, info in models.items():
        print(f"• {name}: {info['description']}")
    print("-" * 50)
    print("Usage example: detector = YOLODetector(model_name='yolov8s')")

# Main entry point for direct execution
if __name__ == "__main__":
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="YOLOv8 Object Detection")
    parser.add_argument(
        "--source", "-s",
        help="Path to image/video file or camera index (0, 1, ...)",
        default="0"  # Default to camera 0
    )
    parser.add_argument(
        "--model", "-m",
        help="Model name (yolov8n, yolov8s, yolov8m, yolov8l, yolov8x) or path to custom model",
        default="yolov8n"
    )
    parser.add_argument(
        "--confidence", "-c",
        type=float,
        help="Detection confidence threshold (0.01-1.0)",
        default=0.35
    )
    parser.add_argument(
        "--iou",
        type=float,
        help="IoU threshold for NMS (0.01-1.0)",
        default=0.45
    )
    parser.add_argument(
        "--size",
        type=int,
        help="Image size for inference",
        default=640
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: auto-generated)",
        default=None
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available pre-trained models and exit"
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Disable real-time display (useful for headless systems)"
    )
    
    args = parser.parse_args()
    
    # List models if requested
    if args.list_models:
        print_available_models()
        sys.exit(0)
    
    # Create detector with specified parameters
    detector = YOLODetector(
        model_name=args.model,
        confidence=args.confidence,
        iou_threshold=args.iou,
        img_size=args.size
    )
    
    # Process input based on type
    source = args.source
    if source.isdigit():
        # Camera input
        detector.process_video(
            int(source),
            output_path=args.output,
            show_result=not args.no_display
        )
    elif source.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.webp')):
        # Image input
        detector.process_image(
            source,
            output_path=args.output,
            show_result=not args.no_display
        )
    elif source.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
        # Video input
        detector.process_video(
            source,
            output_path=args.output,
            show_result=not args.no_display
        )
    else:
        logger.error(f"Unsupported input format: {source}")
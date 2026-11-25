
import argparse
import logging
import os
import time
from pathlib import Path
from typing import Dict, Tuple, List, Optional
import cv2
import numpy as np

class YOLODetector:
    """Optimized YOLO Object Detection implementation"""
    
    def __init__(
        self,
        model_path: str = 'yolov8n.pt',
        confidence: float = 0.35,
        iou_threshold: float = 0.45,
        img_size: int = 640,
        device: Optional[str] = None,
        output_dir: str = 'outputs'
    ):
        """
        Initialize YOLO detector with optimized parameters
        
        Args:
            model_path: Path to YOLOv8 model (.pt file)
            confidence: Confidence threshold for detections
            iou_threshold: IoU threshold for NMS
            img_size: Inference image size
            device: Computing device ('cuda', 'cpu', or None for auto-detection)
            output_dir: Directory to save detection outputs
        """
        # Set up logging
        self.logger = self._setup_logger()
        
        # Create output directory
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set detector parameters
        self.confidence = confidence
        self.iou_threshold = iou_threshold
        self.img_size = img_size
        
        # Auto-detect device if not specified
        if device is None:
            import torch
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        else:
            self.device = device
            
        self.logger.info(f"Using device: {self.device}")
        
        # Load model with optimizations
        try:
            from ultralytics import YOLO
            import torch
            self.model = YOLO(model_path)
            self.model.to(self.device)
            if self.device == 'cuda':
                self.logger.info("Enabling CUDA optimizations")
                torch.backends.cudnn.benchmark = True
                
            self.logger.info(f"Loaded YOLOv8 model: {model_path}")
            self.class_names = self.model.names
            
        except Exception as e:
            self.logger.error(f"Model loading failed: {e}")
            raise
        
        # Generate color palette for visualization
        self.colors = self._generate_colors(len(self.class_names))
        
    def _setup_logger(self) -> logging.Logger:
        """Configure logging with clear formatting"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        return logging.getLogger("YOLODetector")
        
    def _generate_colors(self, num_classes: int) -> List[Tuple[int, int, int]]:
        """Generate distinct colors for visualization"""
        np.random.seed(42)  # For reproducibility
        
        # Generate visually distinct colors (HSV space provides better distinction)
        colors = []
        for i in range(num_classes):
            # Generate evenly spaced hues, with good saturation and value
            h = i / num_classes
            s = 0.8
            v = 0.9
            
            # Convert HSV to RGB
            r, g, b = colorsys_hsv_to_rgb(h, s, v)
            colors.append((int(r * 255), int(g * 255), int(b * 255)))
            
        return colors
        
    def process_frame(
        self, 
        frame: np.ndarray,
        draw_fps: bool = True
    ) -> Tuple[np.ndarray, Dict[str, int]]:
        """
        Detect and annotate objects in a single frame
        
        Args:
            frame: Input image frame
            draw_fps: Whether to draw FPS counter on frame
            
        Returns:
            Annotated frame and detection counts
        """
        start_time = time.time()
        
        # Perform detection with optimized parameters
        results = self.model(
            frame, 
            imgsz=self.img_size,
            conf=self.confidence,
            iou=self.iou_threshold,
            max_det=100,  # Limit max detections
            verbose=False  # Reduce console spam
        )
        
        # Process time for FPS calculation
        process_time = time.time() - start_time
        fps = 1.0 / (process_time + 1e-9)  # Avoid division by zero
        
        # Initialize detection tracking
        detections: Dict[str, int] = {}
        
        # Get a copy of the frame for drawing
        annotated_frame = frame.copy()
        
        # Process each detection
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # Extract detection info
                cls_id = int(box.cls[0])
                label = self.class_names[cls_id]
                conf = float(box.conf[0])
                
                # Count detections by class
                detections[label] = detections.get(label, 0) + 1
                
                # Get color for this class
                color = self.colors[cls_id]
                
                # Draw bounding box
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                
                # Prepare label with confidence
                text = f"{label} {conf:.2f}"
                
                # Get text size for background
                (text_width, text_height), baseline = cv2.getTextSize(
                    text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
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
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, 
                    (255, 255, 255), 2
                )
        
        # Draw FPS counter if requested
        if draw_fps:
            fps_text = f"FPS: {fps:.1f}"
            cv2.putText(
                annotated_frame, fps_text,
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                1, (0, 255, 0), 2
            )
            
            # Add device info
            device_text = f"Device: {self.device}"
            cv2.putText(
                annotated_frame, device_text,
                (10, 70), cv2.FONT_HERSHEY_SIMPLEX,
                0.6, (0, 255, 0), 2
            )
        
        return annotated_frame, detections

    def process_image(self, image_path: str, show_result: bool = True):
        """
        Process a single image and save annotated output
        
        Args:
            image_path: Path to input image
            show_result: Whether to display the result
            
        Returns:
            Path to processed image
        """
        try:
            self.logger.info(f"Processing image: {image_path}")
            
            # Read image
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Could not read image: {image_path}")
            
            # Detect objects
            annotated_image, detections = self.process_frame(image)
            
            # Create output filename
            output_filename = self.output_dir / f"{Path(image_path).stem}_detected.jpg"
            
            # Save output
            cv2.imwrite(str(output_filename), annotated_image)
            
            # Log detection results
            self.logger.info(f"Saved result to: {output_filename}")
            self.logger.info(f"Detected objects: {detections}")
            
            # Display result if requested
            if show_result:
                try:
                    cv2.imshow('YOLOv8 Detection', annotated_image)
                    cv2.waitKey(0)
                    cv2.destroyAllWindows()
                except cv2.error:
                    self.logger.warning("GUI display unavailable in headless OpenCV environment.")
                
            return str(output_filename)
            
        except Exception as e:
            self.logger.error(f"Image processing error: {e}")
            return None

    def process_video(self, video_path: str, show_result: bool = True):
        """
        Process video and save annotated output
        
        Args:
            video_path: Path to input video or camera index (0 for webcam)
            show_result: Whether to display the result in real-time
            
        Returns:
            Path to processed video
        """
        try:
            # Handle numeric camera index
            if isinstance(video_path, (int, str)) and video_path.isdigit():
                video_path = int(video_path)
                self.logger.info(f"Opening camera index: {video_path}")
            else:
                self.logger.info(f"Processing video: {video_path}")
                
            # Open video source
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Could not open video source: {video_path}")

            # Get video properties
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(cap.get(cv2.CAP_PROP_FPS) or 30)  # Default to 30 if reading fails
            
            # Prepare output filename
            if isinstance(video_path, int):
                output_file = self.output_dir / f"camera_{video_path}_detected.mp4"
            else:
                output_file = self.output_dir / f"{Path(video_path).stem}_detected.mp4"
                
            self.logger.info(f"Output will be saved to: {output_file}")

            # Initialize video writer
            writer = cv2.VideoWriter(
                str(output_file),
                cv2.VideoWriter_fourcc(*'mp4v'),  # Use 'avc1' for better compatibility
                fps,
                (frame_width, frame_height)
            )

            if not writer.isOpened():
                self.logger.error(f"Failed to open VideoWriter for: {output_file}")
                return None

            # Process frames
            frame_count = 0
            detection_stats = {}
            start_time = time.time()
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Process frame
                annotated_frame, detections = self.process_frame(frame, draw_fps=True)
                
                # Update detection stats
                for key, value in detections.items():
                    if key not in detection_stats:
                        detection_stats[key] = []
                    detection_stats[key].append(value)
                
                # Display if requested
                if show_result:
                    try:
                        cv2.imshow('YOLOv8 Detection', annotated_frame)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break
                    except cv2.error:
                        show_result = False
                
                # Write frame to output video
                writer.write(annotated_frame)
                frame_count += 1
                
                # Log progress for long videos
                if frame_count % 100 == 0:
                    elapsed = time.time() - start_time
                    avg_fps = frame_count / elapsed
                    self.logger.info(f"Processed {frame_count} frames ({avg_fps:.1f} FPS)")

            # Clean up
            cap.release()
            writer.release()
            if show_result:
                try:
                    cv2.destroyAllWindows()
                except cv2.error:
                    pass
                
            # Calculate and log statistics
            total_time = time.time() - start_time
            avg_fps = frame_count / total_time
            
            self.logger.info(f"Video processing complete:")
            self.logger.info(f"- Processed {frame_count} frames in {total_time:.1f} seconds")
            self.logger.info(f"- Average FPS: {avg_fps:.1f}")
            
            # Log detection statistics
            self.logger.info("Detection statistics:")
            for obj_class, counts in detection_stats.items():
                avg_count = sum(counts) / len(counts)
                max_count = max(counts)
                self.logger.info(f"- {obj_class}: Avg: {avg_count:.1f}, Max: {max_count}")
            
            if os.path.exists(output_file):
                self.logger.info(f"Processed video saved to: {output_file}")
                return str(output_file)
            else:
                self.logger.error("Video was not saved properly")
                return None

        except Exception as e:
            self.logger.error(f"Video processing error: {e}")
            return None


def colorsys_hsv_to_rgb(h, s, v):
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


def parse_arguments():
    """Parse command-line arguments with improved help messages"""
    parser = argparse.ArgumentParser(
        description='YOLOv8 Object Detection',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Path to input image/video or camera index (0 for webcam)'
    )
    
    parser.add_argument(
        '-m', '--model',
        default='yolov8n.pt',
        help='YOLO model path (n=nano, s=small, m=medium, l=large, x=xlarge)'
    )
    
    parser.add_argument(
        '-c', '--confidence',
        type=float,
        default=0.35,
        help='Minimum confidence threshold (0.01-1.0)'
    )
    
    parser.add_argument(
        '--iou',
        type=float,
        default=0.45,
        help='IoU threshold for NMS (0.01-1.0)'
    )
    
    parser.add_argument(
        '-s', '--size',
        type=int,
        default=640,
        help='Inference image size (must be multiple of 32)'
    )
    
    parser.add_argument(
        '-d', '--device',
        default=None,
        help='Computing device (cuda, cpu, or auto)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='outputs',
        help='Output directory'
    )
    
    parser.add_argument(
        '--no-show',
        action='store_true',
        help='Disable displaying results (useful for headless systems)'
    )
    
    return parser.parse_args()


def main():
    """Main execution function"""
    args = parse_arguments()
    
    # Initialize detector with optimized parameters
    detector = YOLODetector(
        model_path=args.model,
        confidence=args.confidence,
        iou_threshold=args.iou,
        img_size=args.size,
        device=args.device,
        output_dir=args.output
    )
    
    # Process input based on type
    input_path = args.input
    show_result = not args.no_show
    
    if input_path.isdigit():
        # Camera input
        output_path = detector.process_video(int(input_path), show_result)
    elif input_path.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
        # Image input
        output_path = detector.process_image(input_path, show_result)
    elif input_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        # Video input
        output_path = detector.process_video(input_path, show_result)
    else:
        detector.logger.error(f"Unsupported input format: {input_path}")
        return
    
    if output_path:
        detector.logger.info(f"Processing complete. Output saved to: {output_path}")
    else:
        detector.logger.error("Processing failed")


if __name__ == "__main__":
    main()

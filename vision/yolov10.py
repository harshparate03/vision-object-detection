import cv2
from ultralytics import YOLO
import numpy as np
import time
import torch

def draw_boxes(frame, results, model, conf_threshold=0.5):
    """Draw detection boxes on frame"""
    # Process detections
    for box in results[0].boxes:
        # Get box coordinates
        coords = box.xyxy[0].tolist()  # get box coordinates in (x1, y1, x2, y2) format
        conf = float(box.conf[0])
        cls = int(box.cls[0])
        
        if conf > conf_threshold:
            x1, y1, x2, y2 = map(int, coords)
            
            # Generate random color for each class
            color = tuple(map(int, np.random.randint(0, 255, 3)))
            
            # Draw box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Add label with confidence
            label = f"{model.names[cls]} {conf:.2f}"
            text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
            
            # Draw label background
            cv2.rectangle(frame, (x1, y1 - text_size[1] - 10), 
                         (x1 + text_size[0], y1), color, -1)
            
            # Draw label text
            cv2.putText(frame, label, (x1, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    return frame

def main():
    # Check for GPU availability
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")

    # Initialize YOLOv8 model
    print("Loading YOLOv8 model...")
    model = YOLO('yolov10n.pt')  # Start with nano model for faster processing
    
    # Model configuration
    model.conf = 0.5  # Confidence threshold
    model.iou = 0.45  # NMS IoU threshold

    # Initialize video capture
    print("Starting video stream...")
    cap = cv2.VideoCapture(0)  # Use 0 for webcam
    
    # Set resolution (adjust if needed)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    if not cap.isOpened():
        print("Error: Could not open video stream")
        return

    # Initialize FPS counter
    fps = 0
    frame_count = 0
    start_time = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Could not read frame")
                break

            # Mirror the frame
            frame = cv2.flip(frame, 1)

            # Perform detection
            results = model(frame, verbose=False)
            
            # Draw detection boxes
            frame = draw_boxes(frame, results, model)

            # Calculate and display FPS
            frame_count += 1
            if frame_count >= 30:
                end_time = time.time()
                fps = frame_count / (end_time - start_time)
                frame_count = 0
                start_time = time.time()

            # Display FPS
            cv2.putText(frame, f"FPS: {fps:.2f}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # Show the frame
            try:
                cv2.imshow("YOLOv8 Detection (Mirrored)", frame)
                cv2.setWindowProperty("YOLOv8 Detection (Mirrored)", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            except cv2.error:
                print("GUI display unavailable in headless OpenCV environment.")
                break

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        import traceback
        traceback.print_exc()  # Print full error traceback

    finally:
        print("Cleaning up...")
        cap.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass

if __name__ == "__main__":
    main()

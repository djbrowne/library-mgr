import base64
import re
import numpy as np
import cv2
import zxingcpp
from pyzbar import pyzbar

def clean_code(raw: str) -> str:
    """Strip extraneous whitespace and control characters."""
    if not raw:
        return ""
    return raw.strip()

def is_isbn_like(code: str) -> bool:
    """Check if code matches ISBN-10 or ISBN-13 format."""
    cleaned = re.sub(r'[^0-9Xx]', '', code).upper()
    return len(cleaned) in (10, 13)

def _crop_center_roi(img: np.ndarray, w_pct: float = 0.70, h_pct: float = 0.55) -> np.ndarray:
    """Crop the central region of interest where the user aims the barcode."""
    h, w = img.shape[:2]
    crop_w = int(w * w_pct)
    crop_h = int(h * h_pct)
    x1 = max(0, (w - crop_w) // 2)
    y1 = max(0, (h - crop_h) // 2)
    x2 = min(w, x1 + crop_w)
    y2 = min(h, y1 + crop_h)
    return img[y1:y2, x1:x2]

def _decode_numpy_frame(img: np.ndarray) -> dict:
    """
    High-performance multi-engine barcode recognition pipeline.
    Combines zxing-cpp (primary), pyzbar (secondary), angle rotation sweeps,
    center ROI cropping/zoom, and CLAHE contrast enhancement.
    """
    if img is None or img.size == 0:
        return {"found": False, "error": "Empty or corrupted image frame"}

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    # Helper: try zxingcpp on an image candidate
    def try_zxing(candidate):
        try:
            barcodes = zxingcpp.read_barcodes(
                candidate,
                try_rotate=True,
                try_downscale=True,
                try_invert=True
            )
            for b in barcodes:
                if b.valid and b.text:
                    text = clean_code(b.text)
                    if text:
                        return {
                            "found": True,
                            "barcode": text,
                            "type": b.format.name,
                            "is_isbn": is_isbn_like(text)
                        }
        except Exception:
            pass
        return None

    # Helper: try pyzbar on an image candidate
    def try_pyzbar(candidate):
        try:
            results = pyzbar.decode(candidate)
            if results:
                primary = results[0]
                text = primary.data.decode('utf-8', errors='ignore').strip()
                if text:
                    return {
                        "found": True,
                        "barcode": text,
                        "type": str(primary.type),
                        "is_isbn": is_isbn_like(text)
                    }
        except Exception:
            pass
        return None

    # -------------------------------------------------------------
    # Pass 1: Direct full frame scan via zxing-cpp
    # -------------------------------------------------------------
    res = try_zxing(img)
    if res:
        return res

    res = try_zxing(gray)
    if res:
        return res

    # -------------------------------------------------------------
    # Pass 2: Center ROI (viewfinder box target area) + 1.5x / 2.0x zoom
    # Books held 10-15 inches away have barcodes centered in the reticle.
    # -------------------------------------------------------------
    roi = _crop_center_roi(img, w_pct=0.75, h_pct=0.60)
    res = try_zxing(roi)
    if res:
        return res

    roi_gray = _crop_center_roi(gray, w_pct=0.75, h_pct=0.60)
    res = try_zxing(roi_gray)
    if res:
        return res

    # Upscale ROI 1.5x (enhances narrow barcode bars for fixed-focus laptop webcams)
    roi_h, roi_w = roi_gray.shape[:2]
    if roi_h > 30 and roi_w > 60:
        roi_upscaled = cv2.resize(roi_gray, (int(roi_w * 1.5), int(roi_h * 1.5)), interpolation=cv2.INTER_CUBIC)
        res = try_zxing(roi_upscaled)
        if res:
            return res

    # -------------------------------------------------------------
    # Pass 3: Tilted book rotation sweep (-20°, -10°, +10°, +20°, +30°, -30°)
    # Users naturally hold books at a tilt in front of a laptop camera.
    # -------------------------------------------------------------
    for angle in [15, -15, 25, -25, 35, -35]:
        center = (w // 2, h // 2)
        rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated_frame = cv2.warpAffine(gray, rot_mat, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        res = try_zxing(rotated_frame)
        if res:
            return res

    # -------------------------------------------------------------
    # Pass 4: CLAHE (Contrast Limited Adaptive Histogram Equalization)
    # Compensates for room lighting glare or glossy book paper reflections.
    # -------------------------------------------------------------
    try:
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        res = try_zxing(enhanced)
        if res:
            return res

        # Try sharpening filter on enhanced image
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(enhanced, -1, kernel)
        res = try_zxing(sharpened)
        if res:
            return res
    except Exception:
        pass

    # -------------------------------------------------------------
    # Pass 5: Fallback to pyzbar on full image, grayscale, and Otsu threshold
    # -------------------------------------------------------------
    res = try_pyzbar(img) or try_pyzbar(gray)
    if res:
        return res

    try:
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        res = try_pyzbar(thresh) or try_zxing(thresh)
        if res:
            return res
    except Exception:
        pass

    # -------------------------------------------------------------
    # Pass 6: Fallback to OpenCV BarcodeDetector
    # -------------------------------------------------------------
    if hasattr(cv2, 'barcode'):
        try:
            detector = cv2.barcode.BarcodeDetector()
            ok, decoded_info, decoded_type, _ = detector.detectAndDecode(gray)
            if ok and decoded_info:
                for info, b_type in zip(decoded_info, decoded_type):
                    if info:
                        cleaned = clean_code(info)
                        return {
                            "found": True,
                            "barcode": cleaned,
                            "type": str(b_type),
                            "is_isbn": is_isbn_like(cleaned)
                        }
        except Exception:
            pass

    return {
        "found": False,
        "error": "No barcode detected. Ensure barcode is flat, well-lit, and 6-10 inches from the camera."
    }

def decode_image_bytes(image_bytes: bytes) -> dict:
    """Decode barcode from raw image file bytes (JPG, PNG, WebP, etc.)."""
    if not image_bytes:
        return {"found": False, "error": "No image data received"}
    
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {"found": False, "error": "Could not decode image format"}
        try:
            cv2.imwrite('/tmp/last_scan_frame.jpg', img)
        except Exception:
            pass
        return _decode_numpy_frame(img)
    except Exception as e:
        return {"found": False, "error": f"Error decoding image: {str(e)}"}

def decode_base64_image(base64_str: str) -> dict:
    """Decode barcode from a base64 encoded string or Data URI."""
    if not base64_str:
        return {"found": False, "error": "Empty image string"}

    try:
        if ',' in base64_str:
            base64_str = base64_str.split(',', 1)[1]
        
        img_bytes = base64.b64decode(base64_str)
        return decode_image_bytes(img_bytes)
    except Exception as e:
        return {"found": False, "error": f"Invalid base64 image data: {str(e)}"}

def capture_from_local_camera(device_index: int = 0) -> dict:
    """
    Directly query the host machine's V4L2 camera (e.g. /dev/video0),
    read an HD frame, and decode any barcode present.
    """
    cap = None
    try:
        cap = cv2.VideoCapture(device_index)
        if not cap.isOpened():
            return {
                "found": False,
                "error": f"Camera /dev/video{device_index} is busy or not accessible. (If live browser video is running, close it first.)"
            }

        # Request HD resolution and MJPG
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # Allow camera auto-exposure and white balance to settle with warmup reads
        frame = None
        for _ in range(5):
            ret, frame = cap.read()
            if not ret:
                break

        if frame is None or frame.size == 0:
            return {"found": False, "error": "Failed to capture frame from camera"}

        result = _decode_numpy_frame(frame)

        # Include small base64 preview thumbnail for visual feedback
        try:
            thumb = cv2.resize(frame, (320, 180))
            _, buffer = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 75])
            result["preview_jpg_base64"] = "data:image/jpeg;base64," + base64.b64encode(buffer).decode('ascii')
        except Exception:
            pass

        return result
    except Exception as e:
        return {"found": False, "error": f"Camera hardware error: {str(e)}"}
    finally:
        if cap is not None:
            cap.release()

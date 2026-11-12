import os
from flask import Blueprint, request, jsonify, current_app
from app.services.barcode_service import (
    decode_image_bytes,
    decode_base64_image,
    capture_from_local_camera
)

bp = Blueprint('scanner', __name__, url_prefix='/api')

@bp.route('/scan-barcode', methods=['POST'])
def scan_barcode():
    """
    Decodes barcode from an uploaded image file (JPG, PNG, WebP)
    or from a Base64-encoded snapshot frame.
    """
    # 1. Check for file upload (multipart/form-data)
    uploaded_file = request.files.get('file') or request.files.get('image')
    if uploaded_file and uploaded_file.filename:
        file_bytes = uploaded_file.read()
        result = decode_image_bytes(file_bytes)
        return jsonify(result)

    # 2. Check for JSON base64 payload
    data = request.get_json(silent=True) or {}
    base64_image = data.get('image') or request.form.get('image')
    if base64_image:
        result = decode_base64_image(base64_image)
        return jsonify(result)

    return jsonify({
        "found": False,
        "error": "No image payload provided. Send a file or base64 data string."
    }), 400

@bp.route('/capture-camera', methods=['POST'])
def capture_camera():
    """
    Directly query the host machine's attached integrated camera (/dev/video0)
    to grab a live frame and decode any barcode present.
    """
    data = request.get_json(silent=True) or {}
    device_index = data.get('device', 0)
    try:
        device_index = int(device_index)
    except (ValueError, TypeError):
        device_index = 0

    result = capture_from_local_camera(device_index=device_index)
    return jsonify(result)

@bp.route('/camera-status', methods=['GET'])
def camera_status():
    """Check if local video hardware devices are present on the host."""
    video_devices = []
    dev_dir = '/dev'
    if os.path.exists(dev_dir):
        video_devices = sorted([f"/dev/{d}" for d in os.listdir(dev_dir) if d.startswith('video')])

    return jsonify({
        "camera_detected": len(video_devices) > 0,
        "devices": video_devices,
        "default_device": video_devices[0] if video_devices else None
    })

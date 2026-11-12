import io
import base64
import numpy as np
import cv2
from unittest.mock import patch, MagicMock
from app.services.barcode_service import (
    decode_image_bytes,
    decode_base64_image,
    capture_from_local_camera,
    is_isbn_like
)

def test_is_isbn_like():
    assert is_isbn_like("9780132350884") is True
    assert is_isbn_like("0132350882") is True
    assert is_isbn_like("978-0-13-235088-4") is True
    assert is_isbn_like("1001") is False
    assert is_isbn_like("ABC") is False

def test_camera_status_endpoint(client):
    res = client.get('/api/camera-status')
    assert res.status_code == 200
    data = res.get_json()
    assert 'camera_detected' in data
    assert 'devices' in data
    assert isinstance(data['devices'], list)

def test_scan_barcode_empty_payload(client):
    res = client.post('/api/scan-barcode', json={})
    assert res.status_code == 400
    data = res.get_json()
    assert data['found'] is False

def test_scan_barcode_blank_image_file(client):
    blank = np.full((120, 240, 3), 255, dtype=np.uint8)
    _, buf = cv2.imencode('.jpg', blank)
    data = {
        'file': (io.BytesIO(buf.tobytes()), 'test_blank.jpg')
    }
    res = client.post('/api/scan-barcode', data=data, content_type='multipart/form-data')
    assert res.status_code == 200
    result = res.get_json()
    assert result['found'] is False
    assert 'No barcode detected' in result['error']

def test_scan_barcode_base64_payload(client):
    blank = np.full((100, 200, 3), 255, dtype=np.uint8)
    _, buf = cv2.imencode('.jpg', blank)
    b64_str = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode('ascii')
    
    res = client.post('/api/scan-barcode', json={'image': b64_str})
    assert res.status_code == 200
    result = res.get_json()
    assert result['found'] is False

def test_scan_barcode_successful_decode(client):
    # Mock pyzbar.decode to simulate finding an EAN-13 ISBN barcode
    mock_item = MagicMock()
    mock_item.data = b"9780132350884"
    mock_item.type = "EAN13"

    with patch('app.services.barcode_service.pyzbar.decode', return_value=[mock_item]):
        blank = np.full((100, 200, 3), 255, dtype=np.uint8)
        _, buf = cv2.imencode('.jpg', blank)
        b64_str = base64.b64encode(buf.tobytes()).decode('ascii')

        res = client.post('/api/scan-barcode', json={'image': b64_str})
        assert res.status_code == 200
        result = res.get_json()
        assert result['found'] is True
        assert result['barcode'] == "9780132350884"
        assert result['type'] == "EAN13"
        assert result['is_isbn'] is True

def test_scan_user_id_barcode(client):
    # Mock pyzbar.decode to simulate scanning a 4-digit User ID barcode
    mock_item = MagicMock()
    mock_item.data = b"1001"
    mock_item.type = "CODE128"

    with patch('app.services.barcode_service.pyzbar.decode', return_value=[mock_item]):
        blank = np.full((100, 200, 3), 255, dtype=np.uint8)
        _, buf = cv2.imencode('.jpg', blank)
        data = {
            'file': (io.BytesIO(buf.tobytes()), 'user_id.png')
        }
        res = client.post('/api/scan-barcode', data=data, content_type='multipart/form-data')
        assert res.status_code == 200
        result = res.get_json()
        assert result['found'] is True
        assert result['barcode'] == "1001"
        assert result['type'] == "CODE128"
        assert result['is_isbn'] is False

def test_capture_camera_endpoint(client):
    res = client.post('/api/capture-camera', json={'device': 0})
    assert res.status_code == 200
    data = res.get_json()
    assert 'found' in data
    # /dev/video0 is present on this host
    assert 'error' in data or data['found'] is True

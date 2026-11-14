// Tanager Library Management System Client Script

document.addEventListener('DOMContentLoaded', () => {
    // 1. Autofocus priority for barcode scanner fields
    const autoFocusEl = document.querySelector('[data-autofocus]');
    if (autoFocusEl) {
        autoFocusEl.focus();
    }

    // 2. Barcode scanner keydown listener (Enter key jump/submit)
    const scanInputs = document.querySelectorAll('.barcode-input');
    scanInputs.forEach(input => {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const nextInputId = input.getAttribute('data-next-focus');
                if (nextInputId) {
                    const nextInput = document.getElementById(nextInputId);
                    if (nextInput && !nextInput.value.trim()) {
                        e.preventDefault();
                        nextInput.focus();
                        return;
                    }
                }
            }
        });
    });

    // 3. ISBN Metadata Lookup button / live trigger
    const lookupBtn = document.getElementById('btn-lookup-isbn');
    const isbnInput = document.getElementById('reg-isbn');
    if (lookupBtn && isbnInput) {
        lookupBtn.addEventListener('click', performIsbnLookup);
        isbnInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                performIsbnLookup();
            }
        });
    }

    // 4. Modal auto-fill for Admin Reconciliation
    const reconcileModal = document.getElementById('reconcileModal');
    if (reconcileModal) {
        reconcileModal.addEventListener('show.bs.modal', function (event) {
            const button = event.relatedTarget;
            if (!button) return;
            const copyId = button.getAttribute('data-copy-id');
            const status = button.getAttribute('data-status');
            const condition = button.getAttribute('data-condition');
            const location = button.getAttribute('data-location');
            const title = button.getAttribute('data-title');

            document.getElementById('modal-copy-id').value = copyId;
            document.getElementById('modal-display-copy').textContent = copyId;
            document.getElementById('modal-display-title').textContent = title || '';
            document.getElementById('modal-status').value = status;
            document.getElementById('modal-condition').value = condition;
            document.getElementById('modal-location').value = location;
        });
    }

    // 5. Drag & drop setup for file dropzone
    const dropzone = document.getElementById('scanner-file-dropzone');
    if (dropzone) {
        ['dragenter', 'dragover'].forEach(eventName => {
            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('drag-active');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('drag-active');
            }, false);
        });

        dropzone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files.length > 0) {
                processBarcodeImageFile(files[0]);
            }
        });
    }

    // Clean up camera stream if user dismisses modal via Escape key or backdrop click
    const scannerModalEl = document.getElementById('barcodeScannerModal');
    if (scannerModalEl) {
        scannerModalEl.addEventListener('hidden.bs.modal', () => {
            closeBarcodeScanner();
        });
    }
});

function performIsbnLookup() {
    const isbnInput = document.getElementById('reg-isbn');
    const statusText = document.getElementById('lookup-status');
    const rawIsbn = isbnInput ? isbnInput.value.trim() : '';

    if (!rawIsbn) {
        if (statusText) statusText.innerHTML = '<span class="text-danger">Please enter an ISBN first.</span>';
        return;
    }

    if (statusText) {
        statusText.innerHTML = '<span class="text-primary"><span class="spinner-border spinner-border-sm me-1"></span> Fetching metadata from Open Library & Google Books...</span>';
    }

    fetch(`/catalog/lookup-isbn?isbn=${encodeURIComponent(rawIsbn)}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                if (statusText) statusText.innerHTML = `<span class="text-danger">${data.error}</span>`;
                return;
            }

            document.getElementById('reg-title').value = data.title || '';
            document.getElementById('reg-authors').value = data.authors || '';
            document.getElementById('reg-publisher').value = data.publisher || '';
            document.getElementById('reg-publish-year').value = data.publish_year || '';
            document.getElementById('reg-description').value = data.description || '';

            // Populate Genre and Tags
            if (data.genre) {
                const genreSelect = document.getElementById('reg-genre');
                if (genreSelect) {
                    let optionExists = false;
                    for (let i = 0; i < genreSelect.options.length; i++) {
                        if (genreSelect.options[i].value.toLowerCase() === data.genre.toLowerCase()) {
                            genreSelect.selectedIndex = i;
                            optionExists = true;
                            break;
                        }
                    }
                    if (!optionExists) {
                        const opt = new Option(data.genre, data.genre, true, true);
                        genreSelect.add(opt);
                    }
                }
            }
            if (data.tags && data.tags.length > 0) {
                const tagsInput = document.getElementById('reg-tags');
                if (tagsInput) {
                    tagsInput.value = data.tags.join(', ');
                }
            }

            if (!data.description) {
                // Look up description separately if missing from initial metadata
                fetchDescriptionSeparately(true);
            }

            const previewImg = document.getElementById('cover-preview-img');
            const previewHolder = document.getElementById('cover-preview-container');
            const coverInput = document.getElementById('reg-cover-path');
            if (coverInput && data.cover_image_path) {
                coverInput.value = data.cover_image_path;
            }
            if (data.cover_image_path && previewImg) {
                previewImg.src = `/static/${data.cover_image_path}`;
                previewImg.classList.remove('d-none');
                if (previewHolder) previewHolder.classList.add('d-none');
            }

            let msg = '<span class="text-success"><i class="bi bi-check-circle"></i> Metadata loaded!';
            if (data.already_in_catalog) {
                msg += ` (Title already in catalog with ${data.existing_copies_count} copy/copies - next copy number will be assigned automatically.)`;
            }
            msg += '</span>';

            if (statusText) statusText.innerHTML = msg;
        })
        .catch(err => {
            if (statusText) {
                statusText.innerHTML = '<span class="text-warning">Could not fetch online metadata. You can enter details manually.</span>';
            }
        });
}

function fetchDescriptionSeparately(isAuto = false) {
    const isbnInput = document.getElementById('reg-isbn');
    const titleInput = document.getElementById('reg-title');
    const authorsInput = document.getElementById('reg-authors');
    const descTextarea = document.getElementById('reg-description');
    const statusEl = document.getElementById('desc-lookup-status');

    const isbn = isbnInput ? isbnInput.value.trim() : '';
    const title = titleInput ? titleInput.value.trim() : '';
    const authors = authorsInput ? authorsInput.value.trim() : '';

    if (!isbn && !title) {
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">Enter ISBN or Title first.</span>';
        return;
    }

    if (statusEl) {
        statusEl.innerHTML = '<span class="text-primary"><span class="spinner-border spinner-border-sm me-1"></span> Searching separate description sources...</span>';
    }

    const params = new URLSearchParams({ isbn, title, authors });
    fetch(`/catalog/lookup-description?${params.toString()}`)
        .then(res => res.json())
        .then(data => {
            if (data.description && descTextarea) {
                descTextarea.value = data.description;
                if (statusEl) {
                    statusEl.innerHTML = '<span class="text-success"><i class="bi bi-check-circle me-1"></i> Description found and loaded!</span>';
                }
            } else {
                if (statusEl && !isAuto) {
                    statusEl.innerHTML = '<span class="text-muted">No external description found. You may enter one manually.</span>';
                } else if (statusEl && isAuto) {
                    statusEl.innerHTML = '';
                }
            }
        })
        .catch(err => {
            if (statusEl && !isAuto) {
                statusEl.innerHTML = '<span class="text-warning">Could not fetch separate description.</span>';
            }
        });
}

// =========================================================================
// Real-Time High-Definition Barcode Scanner & JPG Upload Engine
// =========================================================================

let activeScannerTargetInputId = null;
let cameraMediaStream = null;
let zxingReader = null;
let autoScanTimer = null;
let isScanInFlight = false;
let currentSelectedCameraId = null;
let isSuccessTriggered = false;

/**
 * Open the universal Barcode Scanner Modal for a specific input field.
 */
function openBarcodeScanner(targetInputId) {
    activeScannerTargetInputId = targetInputId;
    isSuccessTriggered = false;

    const modalEl = document.getElementById('barcodeScannerModal');
    if (!modalEl) {
        alert("Barcode scanner modal element not found in DOM.");
        return;
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

    resetScannerUI();
    startIntegratedCamera();
}

/**
 * Backwards-compatibility alias for older templates.
 */
function startCameraScanner(targetInputId) {
    openBarcodeScanner(targetInputId);
}

/**
 * Reset scanner dialog UI components.
 */
function resetScannerUI() {
    isScanInFlight = false;
    isSuccessTriggered = false;

    const targetBox = document.getElementById('modal-scanner-target-box');
    if (targetBox) targetBox.classList.remove('success');

    const spinner = document.getElementById('modal-scanner-spinner');
    if (spinner) spinner.classList.remove('d-none');

    const statusText = document.getElementById('modal-scanner-status-text');
    if (statusText) {
        statusText.className = '';
        statusText.textContent = "Point the book's ISBN barcode at the camera lens...";
    }

    const previewContainer = document.getElementById('file-preview-container');
    if (previewContainer) previewContainer.classList.add('d-none');

    const snapPreview = document.getElementById('snapshot-preview-container');
    if (snapPreview) snapPreview.classList.add('d-none');
}

/**
 * Populate the camera switcher dropdown with available devices.
 */
function populateCameraDropdownWithDevices(videoDevices, preferredDeviceId = null) {
    const select = document.getElementById('scanner-camera-select');
    if (!select || !videoDevices || videoDevices.length === 0) return;

    select.innerHTML = '';
    videoDevices.forEach((dev, idx) => {
        const opt = document.createElement('option');
        opt.value = dev.deviceId;
        opt.textContent = dev.label || `Camera ${idx + 1}`;
        if (preferredDeviceId && dev.deviceId === preferredDeviceId) {
            opt.selected = true;
        } else if (!preferredDeviceId && currentSelectedCameraId && dev.deviceId === currentSelectedCameraId) {
            opt.selected = true;
        } else if (!preferredDeviceId && !currentSelectedCameraId && idx === 0) {
            opt.selected = true;
        }
        select.appendChild(opt);
    });
}

/**
 * Switch camera device from dropdown.
 */
function switchCameraDevice(deviceId) {
    currentSelectedCameraId = deviceId;
    stopActiveStreams();
    startIntegratedCamera(deviceId);
}

/**
 * Stop active camera streams and readers without closing the modal.
 */
function stopActiveStreams() {
    if (zxingReader) {
        try { zxingReader.reset(); } catch(e) {}
    }
    if (autoScanTimer) {
        clearInterval(autoScanTimer);
        autoScanTimer = null;
    }
    if (cameraMediaStream) {
        cameraMediaStream.getTracks().forEach(track => {
            try { track.stop(); } catch(e) {}
        });
        cameraMediaStream = null;
    }
    const video = document.getElementById('modal-scanner-video');
    if (video) {
        video.srcObject = null;
    }
}

/**
 * Initialize WebRTC stream for the integrated camera.
 * Uses client-side ZXing continuous video reader if available,
 * with server-side snapshot fallback.
 */
async function startIntegratedCamera(preferredDeviceId = null) {
    const video = document.getElementById('modal-scanner-video');
    if (!video) return;

    // 1. Primary Engine: Client-Side ZXing BrowserMultiFormatReader
    if (window.ZXing && window.ZXing.BrowserMultiFormatReader) {
        try {
            if (!zxingReader) {
                const hints = new Map();
                const formats = [
                    ZXing.BarcodeFormat.EAN_13,
                    ZXing.BarcodeFormat.EAN_8,
                    ZXing.BarcodeFormat.UPC_A,
                    ZXing.BarcodeFormat.UPC_E,
                    ZXing.BarcodeFormat.CODE_128,
                    ZXing.BarcodeFormat.CODE_39,
                    ZXing.BarcodeFormat.QR_CODE
                ];
                hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, formats);
                hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
                zxingReader = new ZXing.BrowserMultiFormatReader(hints, 250);
            }

            const videoInputDevices = await zxingReader.getVideoInputDevices();
            populateCameraDropdownWithDevices(videoInputDevices, preferredDeviceId);

            const chosenDeviceId = preferredDeviceId || currentSelectedCameraId || (videoInputDevices.length > 0 ? videoInputDevices[0].deviceId : undefined);

            updateScannerStatus("Live scanner active. Hold book steady 8–12 inches away...", "primary");

            zxingReader.decodeFromVideoDevice(chosenDeviceId, 'modal-scanner-video', (result, error) => {
                if (result && !isSuccessTriggered) {
                    const barcode = result.getText();
                    const format = result.getBarcodeFormat();
                    handleBarcodeSuccess(barcode, format ? format.toString() : 'EAN13');
                }
            });

            // Also run a background periodic snapshot check against the backend zxing-cpp engine
            // in case the browser reader has trouble with a specific reflection/tilt
            if (autoScanTimer) clearInterval(autoScanTimer);
            autoScanTimer = setInterval(() => {
                const toggle = document.getElementById('scanner-autoscan-toggle');
                if (toggle && toggle.checked && !isSuccessTriggered) {
                    captureAndSendFrame(false);
                }
            }, 800);

            return;
        } catch (zxingErr) {
            console.warn("ZXing browser engine initialization error:", zxingErr);
        }
    }

    // 2. Fallback Engine: Standard WebRTC getUserMedia + server-side decoding
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        updateScannerStatus("Camera access is not supported by your browser.", "danger");
        return;
    }

    try {
        const videoConstraints = {
            width: { ideal: 1920, min: 1280 },
            height: { ideal: 1080, min: 720 }
        };

        const targetDevice = preferredDeviceId || currentSelectedCameraId;
        if (targetDevice) {
            videoConstraints.deviceId = { exact: targetDevice };
        }

        cameraMediaStream = await navigator.mediaDevices.getUserMedia({
            video: videoConstraints,
            audio: false
        });

        video.srcObject = cameraMediaStream;
        await video.play();

        updateScannerStatus("Camera active. Align barcode in box (keep 8–12 inches away)...", "primary");

        if (autoScanTimer) clearInterval(autoScanTimer);
        autoScanTimer = setInterval(() => {
            const toggle = document.getElementById('scanner-autoscan-toggle');
            if (toggle && toggle.checked && !isSuccessTriggered) {
                captureAndSendFrame(false);
            }
        }, 600);

    } catch (err) {
        updateScannerStatus(`Camera access failed: ${err.message}. You can upload a JPG photo of the barcode.`, "warning");
    }
}

/**
 * Grab video frame to canvas and send to backend /api/scan-barcode.
 */
function captureAndSendFrame(isManualSnap = false) {
    if (isScanInFlight || isSuccessTriggered) return;

    const video = document.getElementById('modal-scanner-video');
    const canvas = document.getElementById('scanner-capture-canvas');
    if (!video || !canvas || video.readyState < 2) return;

    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h || w <= 0 || h <= 0) return;

    canvas.width = w;
    canvas.height = h;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, w, h);

    const base64Data = canvas.toDataURL('image/jpeg', 0.90);

    if (isManualSnap) {
        const snapImg = document.getElementById('snapshot-preview-img');
        const snapContainer = document.getElementById('snapshot-preview-container');
        if (snapImg && snapContainer) {
            snapImg.src = base64Data;
            snapContainer.classList.remove('d-none');
        }
        updateScannerStatus("Analyzing snapshot frame with backend multi-engine decoder...", "info");
    }

    isScanInFlight = true;

    fetch('/api/scan-barcode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: base64Data })
    })
    .then(res => res.json())
    .then(data => {
        isScanInFlight = false;
        if (data.found && data.barcode && !isSuccessTriggered) {
            handleBarcodeSuccess(data.barcode, data.type);
        } else if (isManualSnap) {
            updateScannerStatus(data.error || "No barcode found in snapshot. Check focus/distance and try again.", "warning");
        }
    })
    .catch(err => {
        isScanInFlight = false;
        if (isManualSnap) {
            updateScannerStatus(`Scan request error: ${err.message}`, "danger");
        }
    });
}

/**
 * Manual trigger for snapping and scanning current frame.
 */
function triggerManualSnapshot() {
    captureAndSendFrame(true);
}

/**
 * Directly query the host's Linux V4L2 device (/dev/video0) on the server.
 */
function triggerDirectHostCapture() {
    updateScannerStatus("Querying host camera (/dev/video0)...", "info");

    fetch('/api/capture-camera', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device: 0 })
    })
    .then(res => res.json())
    .then(data => {
        if (data.found && data.barcode && !isSuccessTriggered) {
            handleBarcodeSuccess(data.barcode, data.type);
        } else {
            if (data.preview_jpg_base64) {
                const snapImg = document.getElementById('snapshot-preview-img');
                const snapContainer = document.getElementById('snapshot-preview-container');
                if (snapImg && snapContainer) {
                    snapImg.src = data.preview_jpg_base64;
                    snapContainer.classList.remove('d-none');
                }
            }
            updateScannerStatus(data.error || "No barcode found on /dev/video0. Close browser stream or adjust position.", "warning");
        }
    })
    .catch(err => {
        updateScannerStatus(`Host camera error: ${err.message}`, "danger");
    });
}

/**
 * Handle file input selection for JPG/PNG barcode images.
 */
function handleFileBarcodeUpload(event) {
    const file = event.target.files[0];
    if (file) {
        processBarcodeImageFile(file);
    }
}

/**
 * Process and send an image file to /api/scan-barcode.
 */
function processBarcodeImageFile(file) {
    if (!file || !file.type.startsWith('image/')) {
        updateScannerStatus("Please select a valid image file (JPG, PNG, WebP).", "danger");
        return;
    }

    const reader = new FileReader();
    reader.onload = function(e) {
        const previewImg = document.getElementById('file-preview-img');
        const previewContainer = document.getElementById('file-preview-container');
        if (previewImg && previewContainer) {
            previewImg.src = e.target.result;
            previewContainer.classList.remove('d-none');
        }
    };
    reader.readAsDataURL(file);

    updateScannerStatus(`Uploading and decoding ${file.name}...`, "info");

    const formData = new FormData();
    formData.append('file', file);

    fetch('/api/scan-barcode', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.found && data.barcode && !isSuccessTriggered) {
            handleBarcodeSuccess(data.barcode, data.type);
        } else {
            updateScannerStatus(data.error || "No barcode detected in uploaded image. Ensure the barcode is clear and unblurred.", "warning");
        }
    })
    .catch(err => {
        updateScannerStatus(`Upload decode failed: ${err.message}`, "danger");
    });
}

/**
 * When a barcode is successfully detected.
 */
function handleBarcodeSuccess(barcode, barcodeType) {
    if (isSuccessTriggered) return;
    isSuccessTriggered = true;

    // 1. Play success audio chime
    playScannerBeep();

    // 2. Visual success state
    const targetBox = document.getElementById('modal-scanner-target-box');
    if (targetBox) targetBox.classList.add('success');

    const spinner = document.getElementById('modal-scanner-spinner');
    if (spinner) spinner.classList.add('d-none');

    const statusText = document.getElementById('modal-scanner-status-text');
    if (statusText) {
        statusText.innerHTML = `<i class="bi bi-check-circle-fill text-success me-1"></i> <strong>Detected:</strong> ${barcode} <span class="badge bg-success ms-1">${barcodeType || 'ISBN'}</span>`;
    }

    // Stop streams and readers
    stopActiveStreams();

    // 3. Populate target input element
    if (activeScannerTargetInputId) {
        const targetInput = document.getElementById(activeScannerTargetInputId);
        if (targetInput) {
            targetInput.value = barcode;

            targetInput.dispatchEvent(new Event('input', { bubbles: true }));
            targetInput.dispatchEvent(new Event('change', { bubbles: true }));

            // If it's registration, trigger online metadata lookup
            if (activeScannerTargetInputId === 'reg-isbn') {
                setTimeout(() => performIsbnLookup(), 200);
            }

            const nextFocusId = targetInput.getAttribute('data-next-focus');
            if (nextFocusId) {
                const nextInput = document.getElementById(nextFocusId);
                if (nextInput) setTimeout(() => nextInput.focus(), 500);
            }
        }
    }

    // 4. Automatically close modal after brief confirmation display
    setTimeout(() => {
        closeBarcodeScanner();
    }, 750);
}

/**
 * Update the scanner feedback status banner.
 */
function updateScannerStatus(message, alertType) {
    const statusText = document.getElementById('modal-scanner-status-text');
    if (statusText) {
        statusText.textContent = message;
    }
    const feedback = document.getElementById('modal-scanner-feedback');
    if (feedback) {
        feedback.className = `alert alert-${alertType || 'secondary'} d-flex align-items-center py-2 px-3 mt-3 mb-0 small`;
    }
}

/**
 * Close scanner, stop video tracks, reset readers, and close modal.
 */
function closeBarcodeScanner() {
    stopActiveStreams();
    isScanInFlight = false;

    const modalEl = document.getElementById('barcodeScannerModal');
    if (modalEl) {
        const modalInstance = bootstrap.Modal.getInstance(modalEl);
        if (modalInstance) {
            modalInstance.hide();
        }
    }
}

/**
 * Synthesizes a crisp electronic beep on successful scan using Web Audio API.
 */
function playScannerBeep() {
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(1760, ctx.currentTime + 0.12);

        gain.gain.setValueAtTime(0.25, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.12);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start();
        osc.stop(ctx.currentTime + 0.12);
    } catch (e) {
        // AudioContext may be blocked before first user gesture
    }
}

/**
 * Add a new tag to the book on the details page.
 */
function addTagToBook(isbn) {
    const input = document.getElementById('new-tag-input');
    const tag = input ? input.value.trim() : '';
    const statusEl = document.getElementById('tag-feedback-status');

    if (!tag) return;

    fetch(`/catalog/book/${isbn}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            input.value = '';
            renderTagsList(isbn, data.all_tags);
            if (statusEl) {
                statusEl.innerHTML = `<span class="text-success"><i class="bi bi-check-circle"></i> Tag "${data.tag}" added!</span>`;
                setTimeout(() => statusEl.innerHTML = '', 3000);
            }
        } else {
            if (statusEl) {
                statusEl.innerHTML = `<span class="text-danger">${data.error || 'Could not add tag'}</span>`;
            }
        }
    })
    .catch(err => {
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">Network error adding tag.</span>';
    });
}

/**
 * Remove a tag from the book.
 */
function deleteTagFromBook(isbn, tagName) {
    const statusEl = document.getElementById('tag-feedback-status');
    fetch(`/catalog/book/${isbn}/tags/${encodeURIComponent(tagName)}/delete`, {
        method: 'POST'
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            renderTagsList(isbn, data.all_tags);
            if (statusEl) {
                statusEl.innerHTML = `<span class="text-muted"><i class="bi bi-trash"></i> Tag removed.</span>`;
                setTimeout(() => statusEl.innerHTML = '', 2000);
            }
        }
    })
    .catch(err => {
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">Error removing tag.</span>';
    });
}

/**
 * Re-render tag pills on the page dynamically.
 */
function renderTagsList(isbn, tags) {
    const container = document.getElementById('book-tags-container');
    if (!container) return;

    if (!tags || tags.length === 0) {
        container.innerHTML = '<span class="text-muted small fst-italic">No tags added yet.</span>';
        return;
    }

    let html = '';
    tags.forEach(t => {
        html += `
            <span class="badge bg-light text-dark border me-1 mb-1 p-2 d-inline-flex align-items-center">
                <a href="/catalog/?tag=${encodeURIComponent(t)}" class="text-decoration-none text-dark me-1">#${t}</a>
                <button type="button" class="btn-close ms-1" style="font-size: 0.55rem;" aria-label="Remove" onclick="deleteTagFromBook('${isbn}', '${t}')"></button>
            </span>
        `;
    });
    container.innerHTML = html;
}

/**
 * Save updated genre directly from details page.
 */
function updateBookGenre(isbn, newGenre) {
    const statusEl = document.getElementById('genre-feedback-status');
    fetch(`/catalog/book/${isbn}/genre`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ genre: newGenre })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            const badge = document.getElementById('display-genre-badge');
            if (badge) badge.textContent = data.genre;
            if (statusEl) {
                statusEl.innerHTML = '<span class="text-success"><i class="bi bi-check-circle"></i> Genre updated!</span>';
                setTimeout(() => statusEl.innerHTML = '', 2500);
            }
        }
    })
    .catch(err => {
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">Failed to update genre.</span>';
    });
}

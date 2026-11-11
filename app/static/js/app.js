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

            const previewImg = document.getElementById('cover-preview-img');
            const previewHolder = document.getElementById('cover-preview-container');
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

// 5. Camera Barcode Scanner using native BarcodeDetector API (Supported in Chrome/Edge/Android)
let videoStream = null;
async function startCameraScanner(targetInputId) {
    const video = document.getElementById('scanner-video');
    const container = document.getElementById('scanner-container');
    const status = document.getElementById('scanner-status');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert("Camera access is not supported by your browser or environment.");
        return;
    }

    try {
        if (!('BarcodeDetector' in window)) {
            if (status) status.textContent = "BarcodeDetector API not natively supported on this browser. Use USB hardware scanner or manual input.";
        }
        
        container.classList.remove('d-none');
        videoStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment' }
        });
        video.srcObject = videoStream;
        video.play();

        if ('BarcodeDetector' in window) {
            const barcodeDetector = new window.BarcodeDetector({
                formats: ['ean_13', 'ean_8', 'code_128', 'code_39', 'upc_a']
            });

            const scanInterval = setInterval(async () => {
                if (!videoStream) {
                    clearInterval(scanInterval);
                    return;
                }
                try {
                    const barcodes = await barcodeDetector.detect(video);
                    if (barcodes.length > 0) {
                        const code = barcodes[0].rawValue;
                        const targetInput = document.getElementById(targetInputId);
                        if (targetInput) {
                            targetInput.value = code;
                            stopCameraScanner();
                            targetInput.form.submit();
                        }
                    }
                } catch (e) {
                    // detection loop error
                }
            }, 300);
        }
    } catch (err) {
        alert("Could not access camera: " + err.message);
    }
}

function stopCameraScanner() {
    const container = document.getElementById('scanner-container');
    if (container) container.classList.add('d-none');
    if (videoStream) {
        videoStream.getTracks().forEach(track => track.stop());
        videoStream = null;
    }
}

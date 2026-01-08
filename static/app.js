// PDF to PowerPoint Converter - Unified Frontend Logic
// Apple-style white theme with mode selection and JSON download step

const API_BASE = '';
let currentMode = 'normal';  // 'normal' or 'json'
let currentJobId = null;
let statusCheckInterval = null;

// DOM Elements
const uploadSection = document.getElementById('upload-section');
const processingSection = document.getElementById('processing-section');
const jsonDownloadSection = document.getElementById('json-download-section');
const resultSection = document.getElementById('result-section');
const errorSection = document.getElementById('error-section');

const pdfInput = document.getElementById('pdf-input');
const jsonInput = document.getElementById('json-input');
const uploadZone = document.getElementById('upload-zone');
const jsonUploadZone = document.getElementById('json-upload-zone');
const jsonUploadArea = document.getElementById('json-upload-area');

const pdfFileInfo = document.getElementById('pdf-file-info');
const pdfFileName = document.getElementById('pdf-file-name');
const jsonFileInfo = document.getElementById('json-file-info');
const jsonFileName = document.getElementById('json-file-name');

const converterModeSelector = document.getElementById('converter-mode-selector');
const convertBtn = document.getElementById('convert-btn');

const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const processingTitle = document.getElementById('processing-title');
const processingMessage = document.getElementById('processing-message');

const resultFilename = document.getElementById('result-filename');
const errorMessage = document.getElementById('error-message');

// Mode Selection
document.querySelectorAll('input[name="app-mode"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        currentMode = e.target.value;

        // Show/hide JSON upload area
        if (currentMode === 'json') {
            jsonUploadArea.classList.remove('hidden');
        } else {
            jsonUploadArea.classList.add('hidden');
            // Reset JSON input
            jsonInput.value = '';
            jsonFileName.textContent = '';
            jsonFileInfo.classList.add('hidden');
        }

        updateConvertButton();
    });
});

// Upload Zone Click
uploadZone.addEventListener('click', () => pdfInput.click());
if (jsonUploadZone) {
    jsonUploadZone.addEventListener('click', () => jsonInput.click());
}

// Drag & Drop
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('drag-over');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('drag-over');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].name.endsWith('.pdf')) {
        handlePdfFile(files[0]);
    }
});

// File Input Handlers
pdfInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handlePdfFile(e.target.files[0]);
    }
});

jsonInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleJsonFile(e.target.files[0]);
    }
});

function handlePdfFile(file) {
    pdfFileName.textContent = file.name;
    uploadZone.classList.add('hidden');
    pdfFileInfo.classList.remove('hidden');
    updateConvertButton();
}

function handleJsonFile(file) {
    jsonFileName.textContent = file.name;
    jsonUploadZone.classList.add('hidden');
    jsonFileInfo.classList.remove('hidden');
    updateConvertButton();
}

// Remove File Buttons
document.getElementById('remove-pdf').addEventListener('click', () => {
    pdfInput.value = '';
    pdfFileName.textContent = '';
    pdfFileInfo.classList.add('hidden');
    uploadZone.classList.remove('hidden');
    updateConvertButton();
});

document.getElementById('remove-json').addEventListener('click', () => {
    jsonInput.value = '';
    jsonFileName.textContent = '';
    jsonFileInfo.classList.add('hidden');
    jsonUploadZone.classList.remove('hidden');
    updateConvertButton();
});

function updateConvertButton() {
    const hasPdf = pdfInput.files.length > 0;
    const hasJson = jsonInput.files.length > 0;

    let canConvert = false;
    if (currentMode === 'normal') {
        canConvert = hasPdf;
    } else {
        canConvert = hasPdf && hasJson;
    }

    if (canConvert) {
        converterModeSelector.classList.remove('hidden');
        convertBtn.classList.remove('hidden');
    } else {
        converterModeSelector.classList.add('hidden');
        convertBtn.classList.add('hidden');
    }
}

// Convert Button
convertBtn.addEventListener('click', startConversion);

async function startConversion() {
    const pdfFile = pdfInput.files[0];
    const jsonFile = currentMode === 'json' ? jsonInput.files[0] : null;
    const converterMode = document.querySelector('input[name="conversion-mode"]:checked').value;

    // Show processing
    showSection('processing');
    updateStep('upload', 'active');
    updateProgress(0, 'Uploading...');

    try {
        // Upload files
        const formData = new FormData();
        formData.append('pdf_file', pdfFile);
        if (jsonFile) {
            formData.append('json_file', jsonFile);
        }
        formData.append('mode', currentMode);
        formData.append('converter_mode', converterMode);

        const uploadResponse = await fetch(`${API_BASE}/api/upload`, {
            method: 'POST',
            body: formData
        });

        if (!uploadResponse.ok) {
            const error = await uploadResponse.json();
            throw new Error(error.detail || 'Upload failed');
        }

        const uploadData = await uploadResponse.json();
        currentJobId = uploadData.job_id;

        updateProgress(5, 'Upload complete. Starting processing...');
        updateStep('upload', 'completed');
        updateStep('analyze', 'active');

        // Start processing
        const processResponse = await fetch(`${API_BASE}/api/process/${currentJobId}`, {
            method: 'POST'
        });

        if (!processResponse.ok) {
            const error = await processResponse.json();
            throw new Error(error.detail || 'Processing failed');
        }

        // Start polling for status
        startStatusPolling();

    } catch (error) {
        showError(error.message);
    }
}

function startStatusPolling() {
    statusCheckInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/api/status/${currentJobId}`);

            if (!response.ok) {
                throw new Error('Status check failed');
            }

            const status = await response.json();

            // Update progress
            updateProgress(status.progress, status.message);

            // Update steps based on status
            if (status.status === 'analyzing') {
                updateStep('upload', 'completed');
                updateStep('analyze', 'active');
            } else if (status.status === 'generating') {
                updateStep('upload', 'completed');
                updateStep('analyze', 'completed');
                updateStep('generate', 'active');
            }

            // Check status
            if (status.status === 'json_ready') {
                // Normal mode: JSON is ready, show download option
                stopStatusPolling();
                updateStep('analyze', 'completed');
                showSection('json-download');
            } else if (status.status === 'completed') {
                // Completed
                stopStatusPolling();
                updateStep('generate', 'completed');
                updateStep('complete', 'completed');
                resultFilename.textContent = status.output_filename || 'presentation.pptx';
                showSection('result');
            } else if (status.status === 'error') {
                // Error
                stopStatusPolling();
                showError(status.message);
            }

        } catch (error) {
            stopStatusPolling();
            showError(error.message);
        }
    }, 1000);
}

function stopStatusPolling() {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
        statusCheckInterval = null;
    }
}

function updateProgress(percent, message) {
    progressFill.style.width = `${percent}%`;
    progressText.textContent = `${percent}%`;
    if (message) {
        processingMessage.textContent = message;
    }
}

function updateStep(stepId, state) {
    const step = document.getElementById(`step-${stepId}`);
    if (step) {
        step.classList.remove('active', 'completed');
        if (state) {
            step.classList.add(state);
        }
    }
}

// Download JSON (intermediate step)
document.getElementById('download-json-btn').addEventListener('click', () => {
    if (!currentJobId) return;

    window.location.href = `${API_BASE}/api/download-json/${currentJobId}`;

    document.getElementById('json-download-status').textContent = '✓ Download started';
});

// Continue to PPTX generation
document.getElementById('continue-btn').addEventListener('click', async () => {
    if (!currentJobId) return;

    showSection('processing');
    updateStep('generate', 'active');
    updateProgress(60, 'Generating PowerPoint...');

    try {
        const response = await fetch(`${API_BASE}/api/continue/${currentJobId}`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Continue failed');
        }

        // Resume status polling
        startStatusPolling();

    } catch (error) {
        showError(error.message);
    }
});

// Download Result
document.getElementById('download-btn').addEventListener('click', () => {
    if (!currentJobId) return;
    window.location.href = `${API_BASE}/api/download/${currentJobId}`;
});

// New Conversion
document.getElementById('new-convert-btn').addEventListener('click', resetApp);
document.getElementById('retry-btn').addEventListener('click', resetApp);

// Show specific section
function showSection(sectionName) {
    uploadSection.classList.add('hidden');
    processingSection.classList.add('hidden');
    jsonDownloadSection.classList.add('hidden');
    resultSection.classList.add('hidden');
    errorSection.classList.add('hidden');

    switch (sectionName) {
        case 'upload':
            uploadSection.classList.remove('hidden');
            break;
        case 'processing':
            processingSection.classList.remove('hidden');
            break;
        case 'json-download':
            jsonDownloadSection.classList.remove('hidden');
            break;
        case 'result':
            resultSection.classList.remove('hidden');
            break;
        case 'error':
            errorSection.classList.remove('hidden');
            break;
    }
}

function showError(message) {
    errorMessage.textContent = message;
    showSection('error');
}

function resetApp() {
    currentJobId = null;
    stopStatusPolling();

    // Reset file inputs
    pdfInput.value = '';
    jsonInput.value = '';
    pdfFileName.textContent = '';
    jsonFileName.textContent = '';

    // Reset UI states
    pdfFileInfo.classList.add('hidden');
    jsonFileInfo.classList.add('hidden');
    uploadZone.classList.remove('hidden');
    if (jsonUploadZone) jsonUploadZone.classList.remove('hidden');
    converterModeSelector.classList.add('hidden');
    convertBtn.classList.add('hidden');

    // Reset mode to normal
    document.querySelector('input[name="app-mode"][value="normal"]').checked = true;
    currentMode = 'normal';
    jsonUploadArea.classList.add('hidden');

    // Reset progress
    updateProgress(0, 'Initializing...');

    // Reset steps
    ['upload', 'analyze', 'generate', 'complete'].forEach(step => {
        updateStep(step, null);
    });

    // Reset JSON download status
    document.getElementById('json-download-status').textContent = '';

    showSection('upload');
}

// Initialize
showSection('upload');

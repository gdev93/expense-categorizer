document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const browseFiles = document.getElementById('browseFiles');
    const fileListPreview = document.getElementById('fileListPreview');
    const submitUpload = document.getElementById('submitUpload');
    const uploadForm = document.getElementById('uploadForm');
    const processingProgressBarContainer = document.getElementById('processingProgressBarContainer');
    const processingProgressBar = document.getElementById('processingProgressBar');
    let fileToUpload = null;
    const MAX_FILE_SIZE_MB = 10 * 1024 * 1024;
    const ALLOWED_TYPES = ['.csv', '.xlsx', '.xls'];
    let processingComplete = false;
    let uploadInProgress = false;
    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }
    async function checkUploadAvailability() {
        try {
            const response = await fetch(FILE_UPLOAD_CHECK, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN
                }
            });
            const data = await response.json();
            uploadInProgress = data.upload_in_progress;
            return {
                canUpload: !data.upload_in_progress,
                data: data
            };
        } catch (error) {
            console.error("Check availability error:", error);
            uploadInProgress = false;
            return {
                canUpload: false,
                data: null
            };
        }
    }

    async function performUpload() {
        if (!fileToUpload) return;
        const formData = new FormData();
        formData.append('csrfmiddlewaretoken', CSRF_TOKEN);
        formData.append(fileInput.name, fileToUpload, fileToUpload.name);
        submitUpload.disabled = true;
        submitUpload.classList.add('btn-disabled');
        processingComplete = false;
        try {
            const response = await fetch(uploadForm.action, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: formData
            });
            if (!response.ok) {
                const errorData = await response.json();
                showAlert(`${errorData.error || 'Si è verificato un errore sul server.'}`);
                submitUpload.disabled = false;
                submitUpload.classList.remove('btn-disabled');
            } else {
                uploadInProgress = true;
                if (window.location.href.includes(FILE_UPLOADS_PAGE)) {
                    window.location.reload();
                } else {
                    window.location.href = FILE_UPLOADS_PAGE;
                }
            }
        } catch (error) {
            showAlert('Errore di connessione. Controlla la tua rete.');
            submitUpload.disabled = false;
            submitUpload.classList.remove('btn-disabled');
        } finally {
            updateFileList();
        }
    }

    function updateFileList() {
        fileListPreview.innerHTML = '';
        if (fileToUpload) {
            fileListPreview.classList.remove('hidden');
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            fileItem.innerHTML = `
                    <span class="file-item-name">${fileToUpload.name}</span>
                    <span class="file-item-size text-muted">(${formatBytes(fileToUpload.size)})</span>
                    <span class="material-icons file-item-remove" title="Rimuovi">close</span>
                `;
            fileListPreview.appendChild(fileItem);
        } else {
            fileListPreview.classList.add('hidden');
        }
        if (uploadInProgress) {
            submitUpload.classList.add('btn-disabled');
            submitUpload.disabled = true;
        } else {
            submitUpload.classList.remove('btn-disabled');
            submitUpload.disabled = false;
        }
    }
    async function addFile(file) {
        const fileNameLower = file.name.toLowerCase();
        const isValidType = ALLOWED_TYPES.some(type => fileNameLower.endsWith(type));
        if (!isValidType) {
            showAlert(`Il file "${file.name}" non è un tipo supportato (${ALLOWED_TYPES.join(', ')}).`);
            return;
        }
        if (file.size > MAX_FILE_SIZE_MB) {
            showAlert(`Il file "${file.name}" supera la dimensione massima di 10MB.`);
            return;
        }
        const uploadCheck = await checkUploadAvailability();
        if (!uploadCheck.canUpload) {
            showAlert('⚠️ ATTENZIONE: C\'è un caricamento in corso!\n\n' +
                'Non è possibile caricare un nuovo file mentre è in corso l\'elaborazione di un altro upload.\n\n' +
                'È importante che tu:\n' +
                '• Completi l\'elaborazione in corso, oppure\n' +
                '• Elimini il caricamento in sospeso\n\n' +
                'Riprova dopo aver gestito il caricamento in corso.', 'warning');
            return;
        }
        fileToUpload = file;
        updateFileList();
    }
    function startSSE() {
        if (window.currentEventSource) {
            window.currentEventSource.close();
        }
        const eventSource = new EventSource(FILE_UPLOAD_PROGRESS);
        window.currentEventSource = eventSource;
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            let percentage = data.percentage ? data.percentage.replace('%', '') : '0';
            percentage = parseInt(percentage, 10);
            processingProgressBar.style.width = `${percentage}%`;
            processingProgressBar.textContent = `${percentage}% Elaborazione...`;
            processingProgressBar.setAttribute('aria-valuenow', percentage);
            uploadInProgress = true;
            submitUpload.disabled = true;
            submitUpload.classList.add('btn-disabled');
            processingProgressBarContainer.classList.remove('hidden');
            if (percentage === 100 || data.status === 'finished') {
                console.log("Processing complete!");
                eventSource.close();
                processingComplete = true;
                uploadInProgress = false;
                setTimeout(() => {
                    processingProgressBarContainer.classList.add('hidden');
                    submitUpload.disabled = false;
                    submitUpload.classList.remove('btn-disabled');
                    if (window.location.href.includes(FILE_UPLOADS_PAGE)) {
                        window.location.reload();
                    } else {
                        window.location.href = FILE_UPLOADS_PAGE;
                    }
                }, 1000);
            }
        };
        eventSource.onerror = (error) => {
            console.error("SSE error:", error);
            eventSource.close();
            processingComplete = true;
            uploadInProgress = false;
            submitUpload.disabled = false;
            submitUpload.classList.remove('btn-disabled');
            processingProgressBarContainer.classList.add('hidden');
        };
    }
    async function handlePageRefresh() {
        processingProgressBarContainer.classList.add('hidden');
        const uploadCheck = await checkUploadAvailability();
        if (!uploadCheck.canUpload && uploadCheck.data) {
            submitUpload.disabled = true;
            submitUpload.classList.add('btn-disabled');
            processingProgressBarContainer.classList.remove('hidden');
            uploadInProgress = true;
            startSSE();
        } else {
            uploadInProgress = false;
            submitUpload.disabled = false;
            submitUpload.classList.remove('btn-disabled');
        }
    }
    browseFiles.addEventListener('click', (e) => {
        e.preventDefault();
        fileInput.click();
    });
    fileInput.addEventListener('change', async (e) => {
        if (e.target.files.length > 0) {
            await addFile(e.target.files[0]);
        }
        e.target.value = '';
    });
    fileListPreview.addEventListener('click', (e) => {
        if (e.target.classList.contains('file-item-remove')) {
            fileToUpload = null;
            updateFileList();
        }
    });
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over'), false);
    });
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over'), false);
    });
    dropZone.addEventListener('drop', async (e) => {
        const dt = e.dataTransfer;
        if (dt.files.length > 0) {
            await addFile(dt.files[0]);
        }
    }, false);
    uploadForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        if (!fileToUpload) return;
        const uploadCheck = await checkUploadAvailability();
        if (!uploadCheck.canUpload) {
            showAlert('Non è possibile caricare un nuovo file mentre è in corso l\'elaborazione di un altro upload.', 'warning');
            updateFileList();
            return;
        }

        const data = uploadCheck.data;
        await performUpload();
    });
    updateFileList();
    handlePageRefresh();
    
    // Handle default category modal
    const defaultCategoryModal = document.getElementById('defaultCategoryModal');
    const showDefaultCategories = document.getElementById('showDefaultCategories');
    const defaultCategoryModalText = document.getElementById('defaultCategoryModalText');

    if (showDefaultCategories && defaultCategoryModal) {
        showDefaultCategories.addEventListener('click', (e) => {
            e.preventDefault();
            if (defaultCategoryModalText) {
                defaultCategoryModalText.style.display = 'none';
            }
            defaultCategoryModal.style.display = 'flex';
        });
    }
});

window.closeDefaultCategoryModal = function() {
    const modal = document.getElementById('defaultCategoryModal');
    if (modal) {
        modal.style.display = 'none';
    }
};

window.addEventListener('click', function(event) {
    const modal = document.getElementById('defaultCategoryModal');
    if (event.target === modal) {
        closeDefaultCategoryModal();
    }
});

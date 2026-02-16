
document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const browseFiles = document.getElementById('browseFiles');
    const fileListPreview = document.getElementById('fileListPreview');
    const submitUpload = document.getElementById('submitUpload');
    const uploadForm = document.getElementById('uploadForm');
    const processingProgressBarContainer = document.getElementById('processingProgressBarContainer');
    const processingProgressBar = document.getElementById('processingProgressBar');

    // Variabile per tenere traccia di UN SOLO file
    let fileToUpload = null;

    // Costanti
    const MAX_FILE_SIZE_MB = 10 * 1024 * 1024; // 10MB in bytes
    const ALLOWED_TYPES = ['.csv', '.xlsx', '.xls'];

    // --- Variabile di Stato per il Polling ---
    let processingComplete = false; // Flag per controllare lo stato di elaborazione
    let uploadInProgress = false; // Flag per indicare se c'è un upload in corso

    // --- Funzioni di Utilità ---

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    /**
     * Controlla se è possibile caricare un nuovo file.
     */
    async function checkUploadAvailability() {
        try {
            const response = await fetch(FILE_UPLOAD_CHECK, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN
                }
            });

            if (response.status === 200) {
                // C'è un upload in corso
                const data = await response.json();
                uploadInProgress = true;
                return {
                    canUpload: false,
                    data: data
                };
            } else if (response.status === 404) {
                // Nessun upload in corso, può caricare
                uploadInProgress = false;
                return {
                    canUpload: true,
                    data: null
                };
            } else {
                console.error("Errore durante il controllo della disponibilità:", response.status);
                uploadInProgress = false;
                return {
                    canUpload: false,
                    data: null
                };
            }
        } catch (error) {
            console.error('Errore di Rete durante il controllo della disponibilità:', error);
            uploadInProgress = false;
            return {
                canUpload: false,
                data: null
            };
        }
    }

    function updateFileList() {
        // Aggiorna la lista di anteprima e il bottone
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

        // Aggiorna il bottone: Disabilitato SOLO se c'è un upload in corso
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

        // Controlla se è possibile caricare prima di aggiungere il file
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

        // SOSTITUISCE il file esistente (unico file permesso)
        fileToUpload = file;
        updateFileList();
    }

    // --- Funzioni per Avvio e Controllo Processo ---

    /**
     * Controlla lo stato di avanzamento usando Server-Sent Events (SSE).
     */
    function startSSE() {
        console.log("SSE avviato.");

        // Chiudi eventuale connessione esistente
        if (window.currentEventSource) {
            window.currentEventSource.close();
        }

        const eventSource = new EventSource(FILE_UPLOAD_PROGRESS);
        window.currentEventSource = eventSource;

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.status === 'finished') {
                eventSource.close();
                processingComplete = true;
                uploadInProgress = false;

                processingProgressBarContainer.classList.add('hidden');
                submitUpload.disabled = false;
                submitUpload.classList.remove('btn-disabled');

                if (window.location.href !== FILE_UPLOADS_PAGE) {
                    window.location.href = FILE_UPLOADS_PAGE;
                }
                return;
            }

            let percentage = data.percentage ? data.percentage.replace('%', '') : '0';
            percentage = parseInt(percentage, 10);

            processingProgressBar.style.width = `${percentage}%`;
            processingProgressBar.textContent = `${percentage}% Elaborazione...`;
            processingProgressBar.setAttribute('aria-valuenow', percentage);

            uploadInProgress = true;
            submitUpload.disabled = true;
            submitUpload.classList.add('btn-disabled');
            processingProgressBarContainer.classList.remove('hidden');

            if (percentage === 100) {
                console.log("Processing complete!");
                eventSource.close();
                processingComplete = true;
                uploadInProgress = false;

                setTimeout(() => {
                    window.location.href = FILE_UPLOADS_PAGE;
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
            // C'è un upload in corso
            submitUpload.disabled = true;
            submitUpload.classList.add('btn-disabled');
            processingProgressBarContainer.classList.remove('hidden');
            uploadInProgress = true;
            startSSE();
        } else {
            // Nessun upload in corso - Abilita il bottone
            uploadInProgress = false;
            submitUpload.disabled = false;
            submitUpload.classList.remove('btn-disabled');
        }
    }


    browseFiles.addEventListener('click', (e) => {
        e.preventDefault();
        fileInput.click();
    });

    // 2. Selezione tramite input (il browser assicura che sia un solo file)
    fileInput.addEventListener('change', async (e) => {
        if (e.target.files.length > 0) {
            await addFile(e.target.files[0]);
        }
        e.target.value = ''; // Resetta il valore
    });

    // 3. Rimozione file dall'anteprima
    fileListPreview.addEventListener('click', (e) => {
        if (e.target.classList.contains('file-item-remove')) {
            fileToUpload = null; // Rimuove il file
            updateFileList();
        }
    });

    // 4. Gestione Drag & Drop
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
        // Prende solo il primo file trascinato
        if (dt.files.length > 0) {
            await addFile(dt.files[0]);
        }
    }, false);


    // --- 5. SUBMIT FORM con Long Polling ---
    uploadForm.addEventListener('submit', async function (e) {
        e.preventDefault();

        if (!fileToUpload) return;

        // Controlla se è possibile caricare prima di procedere
        const uploadCheck = await checkUploadAvailability();
        if (!uploadCheck.canUpload) {
            showAlert('Non è possibile caricare un nuovo file mentre è in corso l\'elaborazione di un altro upload.', 'warning');
            updateFileList();
            return;
        }

        const formData = new FormData();
        formData.append('csrfmiddlewaretoken', CSRF_TOKEN);
        formData.append(fileInput.name, fileToUpload, fileToUpload.name);

        submitUpload.disabled = true;
        submitUpload.classList.add('btn-disabled');

        processingComplete = false;

        try {
            // 1. UPLOAD DEL FILE
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
                console.log("Upload file riuscito.");
                uploadInProgress = true;

                // 2. AVVIA L'ELABORAZIONE SSE
                startSSE();
            }
        } catch (error) {
            console.error('Errore di Rete:', error);
            showAlert('Errore di connessione. Controlla la tua rete.');
            submitUpload.disabled = false;
            submitUpload.classList.remove('btn-disabled');
        } finally {
            updateFileList();
        }
    });

    // --- ESECUZIONE INIZIALE ---
    updateFileList();
    handlePageRefresh(); // Chiama la funzione per gestire il refresh
});
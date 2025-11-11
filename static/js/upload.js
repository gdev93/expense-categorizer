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
    const ALLOWED_TYPES = ['.csv'];

    // --- Variabile di Stato per il Polling ---
    let processingComplete = false; // Flag per controllare lo stato di elaborazione

    // --- Funzioni di Utilità ---

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    function updateFileList() {
        // Aggiorna la lista di anteprima e il bottone
        fileListPreview.innerHTML = '';

        if (fileToUpload) {
            fileListPreview.style.display = 'block';

            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';

            fileItem.innerHTML = `
                    <span class="file-item-name">${fileToUpload.name}</span>
                    <span class="file-item-size text-muted">(${formatBytes(fileToUpload.size)})</span>
                    <span class="file-item-remove" title="Rimuovi">&times;</span>
                `;
            fileListPreview.appendChild(fileItem);

            // Aggiorna il bottone: Abilitato se il file è presente
            submitUpload.textContent = fileToUpload ? 'Carica File Selezionato' : 'Carica CSV';
            submitUpload.classList.remove('btn-disabled');
            submitUpload.disabled = false;

        } else {
            fileListPreview.style.display = 'none';
            submitUpload.disabled = true
            submitUpload.classList.add('btn-disabled');
        }
    }


    function addFile(file) {
        const fileNameLower = file.name.toLowerCase();
        const isValidType = ALLOWED_TYPES.some(type => fileNameLower.endsWith(type));

        if (!isValidType) {
            alert(`Errore: Il file "${file.name}" non è un tipo supportato (${ALLOWED_TYPES.join(', ')}).`);
            return;
        }

        if (file.size > MAX_FILE_SIZE_MB) {
            alert(`Errore: Il file "${file.name}" supera la dimensione massima di 10MB.`);
            return;
        }

        // SOSTITUISCE il file esistente (unico file permesso)
        fileToUpload = file;
        updateFileList();
    }

    // --- Funzioni per Avvio e Controllo Processo ---

    /**
     * Invia la richiesta POST a CSV_UPLOAD_PROCESS per avviare l'elaborazione in background.
     */
    async function startCsvProcessing() {
        try {
            const response = await fetch(CSV_UPLOAD_PROCESS, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN
                }
            });

            // L'endpoint di processo ritorna 200/403/404, ma in caso di successo
            // dovrebbe tornare 200 con lo stato iniziale o un 201.
            if (!response.ok) {
                console.error("Errore nell'avvio del processo:", response.status);
                // Se l'avvio fallisce, il polling non deve partire
            }
        } catch (error) {
            console.error('Errore di Rete nell\'avvio del processo:', error);
        } finally {
            processingComplete = true;
            submitUpload.disabled = false;
            submitUpload.classList.remove('btn-disabled');
            window.location.href = CSV_UPLOADS_PAGE;
        }

    }


    /**
     * Controlla lo stato di avanzamento usando CSV_UPLOAD_PROGRESS (GET request).
     */
    async function checkProcessingProgress() {
        try {
            const response = await fetch(CSV_UPLOAD_PROGRESS, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN
                }
            });


            if (response.status === 200) {
                const data = await response.json();

                // NUOVO: Estrai la percentuale e puliscila se necessario
                let percentage = data.percentage ? data.percentage.replace('%', '') : '0';
                percentage = parseInt(percentage, 10);

                // Aggiorna l'elemento della Progress Bar
                processingProgressBar.style.width = `${percentage}%`;
                processingProgressBar.textContent = `${percentage}% Elaborazione...`;
                processingProgressBar.setAttribute('aria-valuenow', percentage);

                submitUpload.disabled = true;
                submitUpload.classList.add('btn-disabled');
                submitUpload.textContent = 'Elaborazione in corso...'; // Bottone mostra solo lo stato generale

                // Verifica la condizione di completamento
                if (percentage === 100 || (data.total > 0 && data.total === data.current_categorized)) {
                    console.log("Processing complete!");
                    processingComplete = true;
                    // Imposta la barra al 100% finale e la nasconde nel "finally" del submit.
                } else {
                    console.log(`Processing progress: ${percentage}%`);
                }
                return true; // Success: process is running/complete

            } else if (response.status === 404) {
                // Nessun caricamento in attesa trovato
                console.log("Nessun caricamento in attesa trovato (404).");
                processingComplete = true; // Ferma il loop

                // NUOVO: Nascondi la Progress Bar al termine o se non trovata
                processingProgressBarContainer.style.display = 'none';

                // Aggiorna l'UI alla modalità di attesa di upload
                submitUpload.disabled = !fileToUpload;
                submitUpload.textContent = fileToUpload ? 'Carica File Selezionato' : 'Carica CSV';
                return false;

            } else {
                console.error("Errore durante il controllo dello stato di elaborazione:", response.status);
                processingComplete = true;
                submitUpload.disabled = false;
                submitUpload.classList.remove('btn-disabled');
                submitUpload.textContent = 'Errore di Elaborazione';
                processingProgressBarContainer.style.display = 'none'; // Nascondi
                return false;
            }

        } catch (error) {
            console.error('Errore di Rete durante il polling:', error);
            processingComplete = true;
            submitUpload.disabled = false;
            submitUpload.classList.remove('btn-disabled');
            submitUpload.textContent = 'Errore di Rete';
            processingProgressBarContainer.style.display = 'none'; // Nascondi
            return false;
        }
    }

    async function startPolling() {
        console.log("Polling avviato.");

        // Loop di polling
        while (!processingComplete) {
            await checkProcessingProgress();

            // Micro-delay per non saturare la CPU del browser
            if (!processingComplete) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
        }

        // Una volta completato, reindirizza l'utente
        if (processingComplete && window.location.href !== CSV_UPLOADS_PAGE) {
            setTimeout(() => {
                window.location.href = CSV_UPLOADS_PAGE;
            }, 1000)
        }
    }

    async function handlePageRefresh() {
        // Disabilita il bottone e cambia il testo durante il controllo iniziale
        submitUpload.disabled = true;
        submitUpload.classList.add('btn-disabled');
        submitUpload.textContent = 'Controllo Stato Upload...'

        // NUOVO: Nascondi la barra durante il controllo iniziale
        processingProgressBarContainer.style.display = 'none';

        // Esegui la prima chiamata per vedere se c'è un processo in corso
        setTimeout(async () => {
            const processFound = await checkProcessingProgress();

            if (processFound && !processingComplete) {
                // Se un processo è attivo (200) ma non è finito, avvia il polling.
                // NUOVO: Mostra la barra prima di avviare il loop
                processingProgressBarContainer.style.display = 'block';
                await startPolling();
            }

            // Assicurati che il bottone sia ripristinato se non c'è polling attivo
            if (processingComplete) {
                updateFileList();
            }
        }, 1000);
    }


    browseFiles.addEventListener('click', (e) => {
        e.preventDefault();
        fileInput.click();
    });

    // 2. Selezione tramite input (il browser assicura che sia un solo file)
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            addFile(e.target.files[0]);
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

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        // Prende solo il primo file trascinato
        if (dt.files.length > 0) {
            addFile(dt.files[0]);
        }
    }, false);


    // --- 5. SUBMIT FORM con Long Polling ---
    uploadForm.addEventListener('submit', async function (e) {
        e.preventDefault();

        if (!fileToUpload) return;

        const formData = new FormData();
        formData.append('csrfmiddlewaretoken', CSRF_TOKEN);
        formData.append(fileInput.name, fileToUpload, fileToUpload.name);

        submitUpload.disabled = true;
        submitUpload.classList.add('btn-disabled');
        submitUpload.textContent = 'Caricamento file... ⏳';

        processingComplete = false;

        try {
            // 1. UPLOAD DEL FILE
            const response = await fetch(uploadForm.action, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                alert(`Errore di Caricamento: ${errorData.error || 'Si è verificato un errore sul server.'}`);
                submitUpload.disabled = false;
                submitUpload.classList.remove('btn-disabled');
                submitUpload.textContent = fileToUpload ? 'Carica File Selezionato' : 'Carica CSV';
            } else {
                console.log("Upload file riuscito.");
                submitUpload.textContent = 'Avvio elaborazione... ⚙️';

                // 2. AVVIA L'ELABORAZIONE IN BACKGROUND
                await startCsvProcessing();
            }
        } catch (error) {
            console.error('Errore di Rete:', error);
            alert('Errore di connessione. Controlla la tua rete.');
            submitUpload.disabled = false;
            submitUpload.classList.remove('btn-disabled');
            submitUpload.textContent = fileToUpload ? 'Carica File Selezionato' : 'Carica CSV';
        } finally {
            updateFileList();
        }
    });

    // --- ESECUZIONE INIZIALE ---
    updateFileList();
    handlePageRefresh(); // Chiama la funzione per gestire il refresh
});
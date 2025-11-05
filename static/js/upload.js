document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const browseFiles = document.getElementById('browseFiles');
    const fileListPreview = document.getElementById('fileListPreview');
    const submitUpload = document.getElementById('submitUpload');
    const uploadForm = document.getElementById('uploadForm');

    // Variabile per tenere traccia di UN SOLO file
    let fileToUpload = null;

    // Costanti
    const MAX_FILE_SIZE_MB = 10 * 1024 * 1024; // 10MB in bytes
    const ALLOWED_TYPES = ['.csv'];

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
            submitUpload.textContent = `Carica File Selezionato`;
            submitUpload.disabled = false;

        } else {
            fileListPreview.style.display = 'none';
            submitUpload.disabled = true;
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

    // --- Event Handlers ---

    // 1. Attivazione Clic sul testo
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


    uploadForm.addEventListener('submit', async function (e) {
        e.preventDefault();

        if (!fileToUpload) return; // Controlla la variabile singola

        const formData = new FormData();

        // AGGIUNGE IL TOKEN CSRF
        formData.append('csrfmiddlewaretoken', CSRF_TOKEN);

        // Aggiunge il singolo file
        // Utilizza il 'name' aggiornato (es. 'file')
        formData.append(fileInput.name, fileToUpload, fileToUpload.name);

        submitUpload.disabled = true;
        submitUpload.textContent = 'Caricamento in corso... ⏳';

        try {
            const response = await fetch(uploadForm.action, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                alert(`Errore di Caricamento: ${errorData.error || 'Si è verificato un errore sul server.'}`);
            }
        } catch (error) {
            console.error('Errore di Rete:', error);
            alert('Errore di connessione. Controlla la tua rete.');
        } finally {
            updateFileList();
        }
        try {
            const process_response = await fetch(CSV_UPLOAD_PROCESS, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN
                }
            })
            if (process_response.ok) {
                alert('Caricamento completato con successo! Il file è in fase di elaborazione.');
            }
        } catch (error) {
            console.log(error)
        } finally {
            window.location.href = CSV_UPLOADS_PAGE
        }
    });
    updateFileList();
});

/**
 * Common logic to download CSV from the export API.
 */
function downloadExport(payload, csrfToken, button) {
    const originalContent = button ? button.innerHTML : null;
    if (button) {
        button.disabled = true;
        button.innerHTML = '⏳...';
    }

    fetch(EXPORT_DOWNLOAD_ENDPOINT, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify(payload)
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Export failed with status ' + response.status);
        }
        
        let filename = null;
        const disposition = response.headers.get('Content-Disposition');
        if (disposition && disposition.indexOf('attachment') !== -1) {
            const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
            const matches = filenameRegex.exec(disposition);
            if (matches != null && matches[1]) {
                filename = matches[1].replace(/['"]/g, '');
            }
        }
        
        return response.blob().then(blob => ({ blob, filename }));
    })
    .then(({ blob, filename }) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        
        if (!filename) {
            const timestamp = new Date().toISOString().split('T')[0];
            filename = `esportazione_spese_${timestamp}.csv`;
        }
        
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        
        setTimeout(() => {
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        }, 100);
    })
    .catch(error => {
        console.error('Error exporting transactions:', error);
        alert('Si è verificato un errore durante l\'esportazione.');
    })
    .finally(() => {
        if (button) {
            button.disabled = false;
            button.innerHTML = originalContent;
        }
    });
}

/**
 * Handles the transaction export to CSV from the filters.
 */
function exportToCsv() {
    const form = document.getElementById('main-filter-form') || document.querySelector('form.filters');
    if (!form) return;

    const formData = new FormData(form);
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    const exportBtn = event.currentTarget;

    const payload = {};
    for (const [key, value] of formData.entries()) {
        if (key === 'months') {
            if (!payload.months) payload.months = [];
            payload.months.push(value);
        } else {
            payload[key] = value;
        }
    }

    downloadExport(payload, csrfToken, exportBtn);
}

/**
 * Exports a specific upload by ID.
 */
function exportUpload(uploadId, event) {
    // Try to find CSRF token from different possible places
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
                      (typeof CSRF_TOKEN !== 'undefined' ? CSRF_TOKEN : null);
    
    if (!csrfToken) {
        console.error('CSRF token not found');
        return;
    }

    const exportBtn = event ? event.currentTarget : null; // The button that was clicked
    downloadExport({ upload_ids: [uploadId] }, csrfToken, exportBtn);
    
    // Prevent the click from bubbling up to the data-list-item (which would navigate to details)
    if (event) {
        event.stopPropagation();
    }
}

function downloadExport(payload, csrfToken, button) {
    if (button) {
        button.disabled = true;
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
        showAlert('Si è verificato un errore durante l\'esportazione.');
    })
    .finally(() => {
        if (button) {
            button.disabled = false;
        }
    });
}
function exportToCsv() {
    const form = document.getElementById('main-filter-form') || document.querySelector('form.filters');
    if (!form) return;
    const formData = new FormData(form);
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    const exportBtn = event.currentTarget;
    const payload = {};
    for (const [key, value] of formData.entries()) {
        if (key === 'months' || key === 'categories') {
            if (!payload[key]) payload[key] = [];
            payload[key].push(value);
        } else {
            payload[key] = value;
        }
    }
    downloadExport(payload, csrfToken, exportBtn);
}
function exportUpload(uploadId, event) {
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
                      (typeof CSRF_TOKEN !== 'undefined' ? CSRF_TOKEN : null);
    if (!csrfToken) {
        console.error('CSRF token not found');
        return;
    }
    const exportBtn = event ? event.currentTarget : null;
    downloadExport({ upload_ids: [uploadId] }, csrfToken, exportBtn);
    if (event) {
        event.stopPropagation();
    }
}

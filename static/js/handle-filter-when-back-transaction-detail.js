
import SESSION_KEYS from './session-keys.js';

document.addEventListener('DOMContentLoaded', function () {
    const backButton = document.getElementById('back-button-list');
    const filters = sessionStorage.getItem(SESSION_KEYS.TRANSACTION_LIST_FILTERS);
    const baseUrl = sessionStorage.getItem(SESSION_KEYS.TRANSACTION_LIST_BASE_URL);

    let backUrl = BASE_BACK_URL; // Default URL without filters

    if (filters && baseUrl) {
        // If filters are found in session storage, construct the full URL
        // Filters already include the '?' or are empty, so we just append them.
        backUrl = baseUrl + filters;
    } else {
        // If no filters are found, check if a default base URL is saved,
        // otherwise fall back to the Django-generated default.
        if (baseUrl) {
            backUrl = baseUrl;
        }
    }

    backButton.href = backUrl;

    // Handle delete button with filter preservation
    const deleteButton = document.querySelector('button[name="delete"]');
    if (deleteButton) {
        deleteButton.addEventListener('click', function(event) {
            if (!confirm('Sei sicuro di voler eliminare questa transazione?')) {
                event.preventDefault();
                return false;
            }

            // Remove required attributes
            document.querySelectorAll('#id_merchant_raw_name, #id_amount, #id_transaction_date, #id_category')
                .forEach(field => field.removeAttribute('required'));

            // Get stored filters
            const storedFilters = sessionStorage.getItem(SESSION_KEYS.TRANSACTION_LIST_FILTERS) || '';
            const storedBaseUrl = sessionStorage.getItem(SESSION_KEYS.TRANSACTION_LIST_BASE_URL);

            // Add redirect URL with filters as hidden field
            if (storedBaseUrl) {
                const form = deleteButton.closest('form');
                const redirectInput = document.createElement('input');
                redirectInput.type = 'hidden';
                redirectInput.name = 'redirect_with_filters';
                redirectInput.value = storedBaseUrl + storedFilters;
                form.appendChild(redirectInput);
            }

            // Let the form submit naturally
            return true;
        });
    }
});
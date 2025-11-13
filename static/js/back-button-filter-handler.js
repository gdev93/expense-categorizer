import SESSION_KEYS from './session-keys.js';

document.addEventListener('DOMContentLoaded', function () {
    const backButton = document.getElementById('back-button-list');
    const filters = sessionStorage.getItem(SESSION_KEYS.TRANSACTION_LIST_FILTERS);
    const baseUrl = sessionStorage.getItem(SESSION_KEYS.TRANSACTION_LIST_BASE_URL);

    let backUrl=BASE_BACK_URL; // Default URL without filters

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
});
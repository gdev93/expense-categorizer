import SESSION_KEYS from './session-keys.js';

function saveFiltersAndRedirect(detailUrl) {
  sessionStorage.setItem(SESSION_KEYS.TRANSACTION_LIST_FILTERS, window.location.search);
  sessionStorage.setItem(SESSION_KEYS.TRANSACTION_LIST_BASE_URL, window.location.pathname);
  window.location.href = detailUrl;
}

window.saveFiltersAndRedirect = saveFiltersAndRedirect;
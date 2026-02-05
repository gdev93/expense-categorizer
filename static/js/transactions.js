/**
 * Handles category selection in merchant view (form submission)
 */
function selectCategory(item, categoryId) {
    const container = item.closest('.category-pill-container');
    if (!container) return;
    
    const input = container.querySelector('input[name="new_category_id"]');
    const form = container.closest('form');
    const span = container.querySelector('.transaction-category');
    const menu = container.querySelector('.category-dropdown-menu');

    if (input) input.value = categoryId;
    if (span) span.textContent = item.textContent.trim();

    // Close menu
    if (menu) {
        menu.classList.remove('show');
        menu.classList.remove('open-above');
    }
    container.classList.remove('is-open');

    // Submit form if it exists
    if (form) form.submit();
}

/**
 * Modal management for creating new transactions
 */
function openCreateModal() {
    const modal = document.getElementById('createTransactionModal');
    if (modal) {
        modal.style.display = "flex";
        document.body.classList.add('modal-open');
    }
}

function closeCreateModal() {
    const modal = document.getElementById('createTransactionModal');
    if (modal) {
        modal.style.display = "none";
        document.body.classList.remove('modal-open');
    }
}

/**
 * Merchant search selection
 */
function selectMerchant(name, id) {
    const input = document.getElementById('id_merchant_name');
    const idInput = document.getElementById('id_merchant_id');
    const container = document.getElementById('merchant-search-results');
    if (input) {
        input.value = name;
        // Trigger a change event so HTMX or other listeners know it changed
        input.dispatchEvent(new Event('change'));
    }
    if (idInput) {
        idInput.value = id || '';
    }
    if (container) {
        container.innerHTML = '';
    }
}

// Global click listener for closing the create modal when clicking outside
window.addEventListener('click', function(event) {
    const modal = document.getElementById('createTransactionModal');
    if (event.target === modal) {
        closeCreateModal();
    }
    
    // Also close merchant search results when clicking outside
    const searchContainer = document.getElementById('merchant-search-results');
    const searchInput = document.getElementById('id_merchant_name');
    if (searchContainer && !searchContainer.contains(event.target) && event.target !== searchInput) {
        searchContainer.innerHTML = '';
    }
});

// Initialize default date and merchant search listeners for transaction forms
document.addEventListener('DOMContentLoaded', function() {
    const dateInput = document.getElementById('id_transaction_date');
    // Only set if it's empty (e.g. on create form)
    if (dateInput && !dateInput.value) {
        dateInput.valueAsDate = new Date();
    }

    // Add listener to clear merchant_id when merchant_name is modified manually
    const merchantNameInput = document.getElementById('id_merchant_name');
    const merchantIdInput = document.getElementById('id_merchant_id');
    if (merchantNameInput && merchantIdInput) {
        merchantNameInput.addEventListener('input', function() {
            // When typing manually, clear the previously selected ID
            merchantIdInput.value = '';
        });
    }
});

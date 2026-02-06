/**
 * Handles category selection in merchant view (form submission)
 */
function selectQuickCategory(item, categoryId) {
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

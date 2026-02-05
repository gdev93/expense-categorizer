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

// Global click listener for closing the create modal when clicking outside
window.addEventListener('click', function(event) {
    const modal = document.getElementById('createTransactionModal');
    if (event.target === modal) {
        closeCreateModal();
    }
});

// Initialize default date for transaction forms
document.addEventListener('DOMContentLoaded', function() {
    const dateInput = document.getElementById('id_transaction_date');
    // Only set if it's empty (e.g. on create form)
    if (dateInput && !dateInput.value) {
        dateInput.valueAsDate = new Date();
    }
});

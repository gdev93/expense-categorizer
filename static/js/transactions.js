function selectQuickCategory(item, categoryId) {
    const container = item.closest('.category-pill-container');
    if (!container) return;
    const input = container.querySelector('input[name="new_category_id"]');
    const form = container.closest('form');
    const span = container.querySelector('.transaction-category');
    const menu = container.querySelector('.category-dropdown-menu');
    if (input) input.value = categoryId;
    if (span) span.textContent = item.textContent.trim();
    if (menu) {
        menu.classList.remove('show');
        menu.classList.remove('open-above');
    }
    container.classList.remove('is-open');
    if (form) form.submit();
}
document.addEventListener('DOMContentLoaded', function() {
    const dateInput = document.getElementById('id_transaction_date');
    if (dateInput && !dateInput.value) {
        dateInput.valueAsDate = new Date();
    }
    const merchantNameInput = document.getElementById('id_merchant_name');
    const merchantIdInput = document.getElementById('id_merchant_id');
    if (merchantNameInput && merchantIdInput) {
        merchantNameInput.addEventListener('input', function() {
            merchantIdInput.value = '';
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('transaction-form');
    const categorySelect = document.getElementById('id_category');
    const newCategoryInput = document.getElementById('id_new_category_name');
    const merchantInput = document.getElementById('id_merchant_name');

    if (!form || !categorySelect || !newCategoryInput) return;

    const originalCategoryId = categorySelect.value;
    const modal = document.getElementById('categoryModal');
    const btnOnlyThis = document.getElementById('btnOnlyThis');
    const btnApplyAll = document.getElementById('btnApplyAll');
    const applyToAllInput = document.getElementById('apply_to_all');

    let shouldShowModal = true;

    form.addEventListener('submit', function(e) {
        // Avoid showing modal when deleting
        if (e.submitter && e.submitter.name === 'delete') {
            return;
        }

        const currentCategoryId = categorySelect.value;
        const newCategoryName = newCategoryInput.value.trim();
        const currentMerchantName = merchantInput ? merchantInput.value.trim() : '';

        // If category has changed OR a new category name is provided
        const categoryChanged = currentCategoryId !== originalCategoryId || newCategoryName !== '';

        if (categoryChanged && shouldShowModal && modal) {
            // Update merchant name in modal text
            const modalMerchantName = document.getElementById('modal-merchant-name');
            if (modalMerchantName) {
                modalMerchantName.textContent = currentMerchantName;
            }

            e.preventDefault();
            // Use !important in style to ensure visibility against conflicting CSS
            modal.style.setProperty('display', 'flex', 'important');
        }
    });

    if (btnOnlyThis) {
        btnOnlyThis.onclick = function() {
            if (applyToAllInput) applyToAllInput.value = "false";
            shouldShowModal = false;
            if (modal) modal.style.display = "none";
            form.submit();
        }
    }

    if (btnApplyAll) {
        btnApplyAll.onclick = function() {
            if (applyToAllInput) applyToAllInput.value = "true";
            shouldShowModal = false;
            if (modal) modal.style.display = "none";
            form.submit();
        }
    }

    // Modal close when clicking outside
    window.addEventListener('click', function(event) {
        if (modal && event.target == modal) {
            modal.style.display = "none";
        }
    });
});

/**
 * Transforms the clicked <span> into a <select> dropdown using pre-loaded options.
 * This function relies on the global array: CATEGORY_OPTIONS.
 */
function makeSelectable(element) {
    // Exit if already a select element
    if (element.querySelector('select')) {
        return;
    }

    // Retrieve IDs from the HTML data attributes
    const currentCategoryId = element.getAttribute('data-current-category-id');
    const transactionId = element.getAttribute('data-transaction-id');

    // 1. Create the new select element
    const selectElement = document.createElement('select');
    selectElement.className = 'category-select-input form-control';
    selectElement.setAttribute('data-transaction-id', transactionId);

    // 2. Populate options using the global CATEGORY_OPTIONS
    CATEGORY_OPTIONS.forEach(category => {
        const option = document.createElement('option');
        // The value sent to the server is the Category ID
        option.value = category.id;
        option.textContent = category.name;

        // Pre-select the current category ID
        if (String(category.id) === currentCategoryId) {
            option.selected = true;
        }
        selectElement.appendChild(option);
    });

    // 3. Set the change event to trigger submission immediately upon selection
    selectElement.onchange = function () {
        submitEdit(this, element);
    };

    // 4. Replace the content and focus
    element.innerHTML = '';
    element.appendChild(selectElement);
    selectElement.focus();
}



async function submitEdit(selectElement, parentDiv) {
    const newCategoryId = selectElement.value;
    const transactionId = selectElement.getAttribute('data-transaction-id');

    parentDiv.innerHTML = selectElement.options[selectElement.selectedIndex].text;

    const formData = new FormData();
    // Send the necessary IDs to the server
    formData.append('category_id', newCategoryId);
    formData.append('transaction_id', transactionId);

    try {
        const response = await fetch(BASE_EDIT_TRANSACTION_URL, {
            method: 'POST',
            headers: {
                'X-CSRFToken': EDIT_TRANSACTION_CATEGORY_CSRF_TOKEN
            },
            body: formData,
        });

        if (!response.ok) {
            parentDiv.style.backgroundColor = '#f8d7da';
            throw new Error(`Update failed with status: ${response.status}`);
        }

        // Success: Execute redirect immediately if mandatory
        if (response.redirected) {
            window.location.href = response.url;
            return;
        }

        // Fallback for success without redirect (visual feedback)
        parentDiv.style.backgroundColor = '#d4edda';
        setTimeout(() => {
            parentDiv.style.backgroundColor = '';
        }, 800);

    } catch (error) {
        console.error("Error updating transaction category:", error);
        parentDiv.style.backgroundColor = '#f8d7da';
        alert("Failed to update transaction category. Check console for details.");
    }
}
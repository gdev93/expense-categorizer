/**
 * Transforms the clicked <div> into an <input> field for editing.
 * Called by: onclick="makeEditable(this)"
 */
function makeEditable(element) {
    // Check if the element is already an input
    if (element.querySelector('input')) {
        return;
    }

    const originalText = element.textContent.trim();
    const categoryId = element.getAttribute('data-category-id');

    // 1. Create the new input element
    const inputElement = document.createElement('input');
    inputElement.type = 'text';
    inputElement.value = originalText;
    // Using a class defined in your CSS for styling
    inputElement.className = 'category-temp-input form-control';

    inputElement.setAttribute('data-category-id', categoryId);

    // 2. Set the onblur event to trigger submission
    inputElement.onblur = function () {
        submitEdit(this, element);
    };

    // 3. Set the onkeypress event for Enter key submission
    inputElement.onkeypress = function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            this.blur(); // Triggers onblur
        }
    };

    // 4. Replace the content and focus
    element.innerHTML = '';
    element.appendChild(inputElement);
    inputElement.focus();
    inputElement.select();
}


async function submitEdit(inputElement, parentDiv) {
    const newValue = inputElement.value.trim();
    const categoryId = inputElement.getAttribute('data-category-id');

    parentDiv.innerHTML = newValue;

    const formData = new FormData();
    formData.append('name', newValue);
    formData.append('id', categoryId);

    try {
        const response = await fetch(BASE_CATEGORY_URL, {
            method: 'POST',
            headers: {
                'X-CSRFToken': CSRF_TOKEN
            },
            body: formData,
        });

        if (!response.ok) {
            parentDiv.style.backgroundColor = '#f8d7da';
            return
        }

        parentDiv.style.backgroundColor = '#d4edda';
        setTimeout(() => {
            if (response.redirected) {
                window.location.href = response.url;
            }
        }, 1000);

    } catch (error) {
        console.error("Error updating category:", error);
        showAlert("Failed to update category. Check console for details.");
    }
}
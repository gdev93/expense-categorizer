function makeEditable(element) {
    if (element.querySelector('input')) {
        return;
    }
    const originalText = element.textContent.trim();
    const categoryId = element.getAttribute('data-category-id');
    const inputElement = document.createElement('input');
    inputElement.type = 'text';
    inputElement.value = originalText;
    inputElement.className = 'category-temp-input form-control';
    inputElement.setAttribute('data-category-id', categoryId);
    inputElement.onblur = function () {
        submitEdit(this, element);
    };
    inputElement.onkeypress = function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            this.blur();
        }
    };
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

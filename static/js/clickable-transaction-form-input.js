function makeSelectable(element, event) {
    if (event) event.stopPropagation();
    if (element.classList.contains('category-pill-container')) {
        return;
    }
    const currentCategoryId = element.getAttribute('data-current-category-id');
    const transactionId = element.getAttribute('data-transaction-id');
    const currentHTML = element.innerHTML;
    const container = document.createElement('div');
    container.className = 'category-pill-container';
    const span = document.createElement('span');
    span.className = 'transaction-category';
    span.style.cursor = 'pointer';
    span.innerHTML = currentHTML;
    span.onclick = function(e) {
        e.stopPropagation();
        toggleCategoryMenu(this);
    };
    const menu = document.createElement('div');
    menu.className = 'category-dropdown-menu';
    CATEGORY_OPTIONS.forEach(category => {
        const item = document.createElement('div');
        item.className = 'category-dropdown-item';
        item.setAttribute('data-category-id', category.id);
        if (String(category.id) === currentCategoryId) {
            item.classList.add('active');
        }
        item.textContent = category.name;
        item.onclick = function(e) {
            e.stopPropagation();
            submitCategoryChange(category.id, category.name, transactionId, span, menu);
        };
        menu.appendChild(item);
    });
    container.appendChild(span);
    container.appendChild(menu);
    element.parentNode.replaceChild(container, element);
    toggleCategoryMenu(span);
}
async function submitCategoryChange(newCategoryId, newCategoryName, transactionId, span, menu) {
    span.textContent = newCategoryName;
    menu.classList.remove('show');
    menu.classList.remove('open-above');
    const container = span.closest('.category-pill-container');
    if (container) container.classList.remove('is-open');
    menu.querySelectorAll('.category-dropdown-item').forEach(item => {
        if (item.getAttribute('data-category-id') == newCategoryId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
    const formData = new FormData();
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
            span.style.backgroundColor = '#f8d7da';
            throw new Error(`Update failed with status: ${response.status}`);
        }
        if (response.redirected) {
            window.location.href = response.url;
            return;
        }
        const data = await response.json();
        span.style.backgroundColor = '#d4edda';
        showAlert(data.message || "Categoria aggiornata con successo.", "success");
        setTimeout(() => {
            span.style.backgroundColor = '';
        }, 800);
    } catch (error) {
        console.error("Error updating transaction category:", error);
        span.style.backgroundColor = '#f8d7da';
        showAlert("Errore durante l'aggiornamento della categoria. Controlla la console per i dettagli.");
    }
}

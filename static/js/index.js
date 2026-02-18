document.addEventListener('DOMContentLoaded', function() {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');
    function toggleMenu() {
        const isClosed = !sidebar.classList.contains('active');
        if (isClosed) {
            sidebar.classList.add('active');
            overlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        } else {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
    }
    if (menuToggle) {
        menuToggle.addEventListener('click', toggleMenu);
    }
    if (overlay) {
        overlay.addEventListener('click', toggleMenu);
    }
    document.addEventListener('keydown', function(event) {
        if (event.key === "Escape" && sidebar.classList.contains('active')) {
            toggleMenu();
        }
    });
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function() {
            const logoutForm = document.getElementById('logout-form');
            if (logoutForm) {
                logoutForm.submit();
            }
        });
    }
});
function setActiveNavItem() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.classList.remove('active');
        const linkPath = link.getAttribute('data-page') || link.getAttribute('href');
        if (currentPath === linkPath) {
            link.classList.add('active');
        }
    });
}
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', function (e) {
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        this.classList.add('active');
        if (window.innerWidth < 768) {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
        }
        const href = this.getAttribute('href');
        sessionStorage.setItem('activeNavItem', href);
    });
});
setActiveNavItem();
function toggleMultiselect(id, event) {
    if (event) event.stopPropagation();
    const el = document.getElementById(id);
    if (!el) return;
    const wasOpen = el.classList.contains('is-open');
    document.querySelectorAll('.custom-multiselect').forEach(m => {
        m.classList.remove('is-open');
    });
    if (!wasOpen) {
        el.classList.add('is-open');
    }
}
function updateMultiselect(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const checkboxes = el.querySelectorAll('input[type="checkbox"]');
    const triggerText = el.querySelector('.trigger-text');
    if (!triggerText) return;
    const selectedCheckboxes = Array.from(checkboxes).filter(cb => cb.checked);
    const selectedCount = selectedCheckboxes.length;
    const placeholder = el.getAttribute('data-placeholder') || 'Seleziona';
    const pluralText = el.getAttribute('data-plural-text') || 'selezionati';
    const firstCheckbox = checkboxes[0];
    if (firstCheckbox && firstCheckbox.name) {
        const name = firstCheckbox.name;
        let hiddenInput = el.querySelector(`input[type="hidden"][name="${name}"]`);
        if (selectedCount === 0) {
            if (!hiddenInput) {
                hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = name;
                hiddenInput.value = '';
                if (firstCheckbox.hasAttribute('form')) {
                    hiddenInput.setAttribute('form', firstCheckbox.getAttribute('form'));
                }
                el.appendChild(hiddenInput);
            }
        } else if (hiddenInput) {
            hiddenInput.remove();
        }
    }
    checkboxes.forEach(cb => {
        const item = cb.closest('.multiselect-item');
        if (item) {
            if (cb.checked) {
                item.classList.add('is-selected');
            } else {
                item.classList.remove('is-selected');
            }
        }
    });
    if (selectedCount === 0) {
        triggerText.textContent = placeholder;
    } else if (selectedCount === 1) {
        const item = selectedCheckboxes[0].closest('.multiselect-item');
        const labelText = item ? item.textContent.trim() : '';
        const cleanedText = labelText.replace(/^(label|event|calendar_today|calendar_month|rule|check_circle|sync)/, '').trim();
        triggerText.textContent = cleanedText;
    } else {
        triggerText.textContent = `${selectedCount} ${pluralText}`;
    }
    el.classList.remove('is-open');
}
function initAllMultiselects() {
    document.querySelectorAll('.custom-multiselect').forEach(el => {
        if (el.id) updateMultiselect(el.id);
    });
}
function toggleCategoryMenu(span) {
    const container = span.closest('.category-pill-container');
    const menu = span.nextElementSibling;
    if (!menu || !container) return;
    document.querySelectorAll('.category-dropdown-menu.show').forEach(m => {
        if (m !== menu) {
            m.classList.remove('show');
            m.classList.remove('open-above');
            const otherContainer = m.closest('.category-pill-container');
            if (otherContainer) otherContainer.classList.remove('is-open');
        }
    });
    const isOpening = !menu.classList.contains('show');
    if (isOpening) {
        menu.classList.remove('open-above');
        menu.classList.add('show');
        const rect = menu.getBoundingClientRect();
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
        if (rect.bottom > viewportHeight) {
            const spanRect = span.getBoundingClientRect();
            if (spanRect.top > viewportHeight - spanRect.bottom) {
                menu.classList.add('open-above');
            }
        }
    } else {
        menu.classList.remove('show');
        menu.classList.remove('open-above');
    }
    container.classList.toggle('is-open', isOpening);
}
function toggleFilters() {
    const collapsible = document.getElementById('filter-collapsible');
    if (collapsible) {
        collapsible.classList.toggle('show');
    }
}
function updateFilterButtonsState() {
    document.querySelectorAll('.filters').forEach(form => {
        const toggleBtn = form.querySelector('.filter-toggle-btn');
        if (!toggleBtn) return;
        let hasActiveFilters = false;
        form.querySelectorAll('input[type="text"], input[type="search"], input[type="number"]').forEach(input => {
            if (input.value.trim() !== '') {
                hasActiveFilters = true;
            }
        });
        form.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
            if (checkbox.checked) {
                hasActiveFilters = true;
            }
        });
        form.querySelectorAll('select').forEach(select => {
            if (select.name === 'year' || select.id === 'year' || select.name === 'view_type' || select.name === 'amount_operator' || select.name === 'paginate_by') return;
            if (select.multiple) {
                if (Array.from(select.selectedOptions).some(opt => opt.value !== '')) {
                    hasActiveFilters = true;
                }
            } else {
                if (select.value !== '') {
                    hasActiveFilters = true;
                }
            }
        });
        if (hasActiveFilters) {
            toggleBtn.classList.add('filters-active');
        } else {
            toggleBtn.classList.remove('filters-active');
        }
    });
}
function clearFilters(formId) {
    const form = document.getElementById(formId);
    if (!form) return;
    Array.from(form.elements).forEach(el => {
        if (el.name === 'view_type' || el.name === 'year' || el.id === 'year' || el.name === 'paginate_by' || el.type === 'hidden') {
            return;
        }
        if (el.tagName === 'INPUT') {
            if (['text', 'search', 'number', 'date'].includes(el.type)) {
                el.value = '';
            } else if (el.type === 'checkbox') {
                el.checked = false;
            }
        } else if (el.tagName === 'SELECT') {
            if (el.multiple) {
                Array.from(el.options).forEach(opt => opt.selected = false);
            } else {
                el.selectedIndex = 0;
            }
            if (el.name === 'amount_operator') {
                el.value = 'eq';
            }
        }
    });
    updateFilterButtonsState();
    initAllMultiselects();
}
document.addEventListener('DOMContentLoaded', () => {
    updateFilterButtonsState();
    initAllMultiselects();
    document.body.addEventListener('htmx:afterSwap', () => {
        updateFilterButtonsState();
        initAllMultiselects();
    });
});
function showAlert(message, type = 'danger') {
    let container = document.querySelector('.messages-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'messages-container';
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.prepend(container);
        } else {
            document.body.prepend(container);
        }
    }
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.setAttribute('role', 'alert');
    const formattedMessage = message.replace(/\n/g, '<br>');
    alertDiv.innerHTML = `
        ${formattedMessage}
        <button type="button" class="close-btn" onclick="this.parentElement.remove();" aria-label="Chiudi">
            <span class="material-icons">close</span>
        </button>
    `;
    container.appendChild(alertDiv);
}
window.addEventListener('click', function(event) {
    if (!event.target.closest('.custom-multiselect')) {
        document.querySelectorAll('.custom-multiselect').forEach(m => {
            m.classList.remove('is-open');
        });
    }
    if (!event.target.closest('.category-pill-container')) {
        document.querySelectorAll('.category-dropdown-menu.show').forEach(menu => {
            menu.classList.remove('show');
            menu.classList.remove('open-above');
            const container = menu.closest('.category-pill-container');
            if (container) container.classList.remove('is-open');
        });
    }
    const searchContainer = document.getElementById('merchant-search-results');
    const searchInput = document.getElementById('id_merchant_name');
    if (searchContainer && !searchContainer.contains(event.target) && event.target !== searchInput) {
        searchContainer.innerHTML = '';
    }
    const categoryContainer = document.getElementById('category-search-results');
    const categoryInput = document.getElementById('id_category_name');
    if (categoryContainer && !categoryContainer.contains(event.target) && event.target !== categoryInput) {
        categoryContainer.innerHTML = '';
    }
});
function selectMerchant(name, id) {
    const input = document.getElementById('id_merchant_name');
    const idInput = document.getElementById('id_merchant_id');
    const container = document.getElementById('merchant-search-results');
    if (input) {
        input.value = name;
        input.dispatchEvent(new Event('change'));
    }
    if (idInput) {
        idInput.value = id || '';
    }
    if (container) {
        container.innerHTML = '';
    }
    if (id) {
        fetch(`/categories/from-merchant/?merchant_id=${id}`)
            .then(response => {
                if (response.ok) return response.text();
                throw new Error('Network response was not ok');
            })
            .then(category => {
                const categoryInput = document.getElementById('id_category_name');
                if (categoryInput && category && !categoryInput.value) {
                    categoryInput.value = category;
                    categoryInput.dispatchEvent(new Event('change'));
                }
            })
            .catch(error => console.error('Error fetching category:', error));
    }
}
function selectCategory(name) {
    const input = document.getElementById('id_category_name');
    const container = document.getElementById('category-search-results');
    if (input) {
        input.value = name;
        input.dispatchEvent(new Event('change'));
    }
    if (container) {
        container.innerHTML = '';
    }
}

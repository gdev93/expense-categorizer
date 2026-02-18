function toggleExpander(headerId) {
    const header = document.getElementById(headerId);
    if (!header) return;
    const toggleBtn = header.querySelector('.expander-toggle-btn');
    const bodyId = toggleBtn.getAttribute('aria-controls');
    const body = document.getElementById(bodyId);
    if (!body) return;
    const isExpanded = toggleBtn.getAttribute('aria-expanded') === 'true';
    if (isExpanded) {
        body.style.maxHeight = '0';
        body.classList.add('collapsed');
        toggleBtn.setAttribute('aria-expanded', 'false');
    } else {
        body.style.maxHeight = body.scrollHeight + 'px';
        body.classList.remove('collapsed');
        toggleBtn.setAttribute('aria-expanded', 'true');
    }
}

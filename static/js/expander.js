/**
 * Toggles the expanded/collapsed state of a content block.
 * @param {string} headerId - The ID of the header element that was clicked.
 */
function toggleExpander(headerId) {
    const header = document.getElementById(headerId);
    if (!header) return;

    // 1. Get the button and the content body
    const toggleBtn = header.querySelector('.expander-toggle-btn');
    const bodyId = toggleBtn.getAttribute('aria-controls');
    const body = document.getElementById(bodyId);

    if (!body) return;

    // 2. Check the current state
    const isExpanded = toggleBtn.getAttribute('aria-expanded') === 'true';

    // 3. Toggle the state
    if (isExpanded) {
        // COLLAPSE: Set max-height to 0 and add the 'collapsed' class
        body.style.maxHeight = '0';
        body.classList.add('collapsed');
        toggleBtn.setAttribute('aria-expanded', 'false');
    } else {
        // EXPAND: Set max-height to the content's scroll height, then remove 'collapsed'
        // Setting it to scrollHeight allows for the smooth CSS transition
        body.style.maxHeight = body.scrollHeight + 'px';
        body.classList.remove('collapsed');
        toggleBtn.setAttribute('aria-expanded', 'true');
    }
}
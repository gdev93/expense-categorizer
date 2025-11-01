function toggleExpander(headerId) {
    const header = document.getElementById(headerId);
    const toggleBtn = header.querySelector('.expander-toggle-btn');
    const body = document.getElementById(toggleBtn.getAttribute('aria-controls'));

    const isExpanded = toggleBtn.getAttribute('aria-expanded') === 'true';

    // Toggle aria state
    toggleBtn.setAttribute('aria-expanded', !isExpanded);

    // Toggle CSS class for styling and animation
    body.classList.toggle('collapsed', isExpanded);

    // Optional: If you use max-height transition, you might need to set it dynamically
    // if (!isExpanded) {
    //     body.style.maxHeight = body.scrollHeight + "px";
    // } else {
    //     body.style.maxHeight = "0";
    // }
}

// Add event listener to the header for better click target
document.getElementById('ruleExpanderHeader').addEventListener('click', function() {
    toggleExpander('ruleExpanderHeader');
});
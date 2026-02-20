# Junie Development Guidelines

1. **Language:** All code and comments must be written in English.
2. **Minimalist Comments:** Comments should be minimal and only explain complex or non-obvious logic.
3. **No Inline CSS:** Do not use inline styles (`style` attributes or `<style>` blocks) in HTML templates, except for email templates. Use dedicated CSS files instead.
4. **Class-Based Views (CBVs):** Every new endpoint must be implemented as a Class-Based View.
   1. Context should be passed using a dataclass
5. **Testing with Testcontainers:** Every Class-Based View must have a minimal unit test using Testcontainers.

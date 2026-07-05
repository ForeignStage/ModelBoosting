# SKILL: Frontend (Claude Code) — Actionable Patterns

## Responsive layout
```css
/* Mobile-first */
.container { width: 100%; padding: 0 1rem; }
@media (min-width: 768px) { .container { max-width: 1200px; margin: 0 auto; } }

/* Flex row → column on mobile */
.row { display: flex; gap: 1rem; flex-wrap: wrap; }
.col { flex: 1; min-width: 280px; }
```

## Accessibility checklist
- `<img>` must have `alt` (empty `alt=""` for decorative)
- Interactive elements need `aria-label` if no visible text
- Focus visible: `outline: 2px solid #0066cc`
- Color contrast ≥ 4.5:1 for normal text, ≥ 3:1 for large
- Form inputs paired with `<label for="id">`
- `role="alert"` for dynamic error messages

## Fetch + error handling
```javascript
async function apiFetch(url, opts = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...opts
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}
```

## DOM update pattern (no framework)
```javascript
function render(container, html) {
  container.innerHTML = '';               // clear
  container.insertAdjacentHTML('beforeend', html); // safe insert
}
```

## Loading/error state
```javascript
function setLoading(el, loading) {
  el.disabled = loading;
  el.textContent = loading ? '加载中...' : el.dataset.label;
}
```

## CSS custom properties (theme)
```css
:root { --color-primary: #1a73e8; --radius: 8px; --shadow: 0 2px 8px rgba(0,0,0,.15); }
```

## Console errors to hunt
- Uncaught TypeError / reference errors
- Failed to fetch / CORS errors
- 404 for assets (fonts, icons)
- "Cannot read properties of undefined"

## RULES
- No inline styles for anything reusable — use CSS classes
- Test at 375px (iPhone SE) and 1440px
- Avoid `innerHTML` with user data — use `textContent` or sanitize
- Check tab navigation works for all interactive elements

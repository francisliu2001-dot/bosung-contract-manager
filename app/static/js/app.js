const trigger = document.querySelector('.menu-button');
const sidebar = document.querySelector('.sidebar');
if (trigger && sidebar) {
  trigger.addEventListener('click', () => {
    const open = sidebar.classList.toggle('is-open');
    trigger.setAttribute('aria-expanded', String(open));
  });
}

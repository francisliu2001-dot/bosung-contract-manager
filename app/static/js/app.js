const trigger = document.querySelector('.menu-button');
const sidebar = document.querySelector('.sidebar');
if (trigger && sidebar) {
  trigger.addEventListener('click', () => {
    const open = sidebar.classList.toggle('is-open');
    trigger.setAttribute('aria-expanded', String(open));
  });
}

document.querySelectorAll('[data-copy]').forEach((button) => {
  button.addEventListener('click', async () => {
    await navigator.clipboard.writeText(button.dataset.copy);
    const original = button.textContent;
    button.textContent = '已复制';
    window.setTimeout(() => { button.textContent = original; }, 1600);
  });
});

document.querySelectorAll('[data-open-dialog]').forEach((button) => {
  button.addEventListener('click', () => {
    const dialog = document.getElementById(button.dataset.openDialog);
    if (!dialog) return;
    const category = button.dataset.category;
    if (category) dialog.querySelector('[name="category"]').value = category;
    dialog.showModal();
  });
});
document.querySelectorAll('[data-close-dialog]').forEach((button) => {
  button.addEventListener('click', () => button.closest('dialog')?.close());
});
document.querySelectorAll('form[data-confirm]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

const createForm = document.getElementById('contract-create-form');
if (createForm) {
  const business = document.getElementById('business-type');
  const fileType = document.getElementById('file-type');
  const owner = document.getElementById('primary-owner');
  const lockedOwner = document.querySelector('[data-owner-code]');
  const month = document.getElementById('signing-month');
  const region = document.getElementById('region');
  const customRegionWrap = document.getElementById('custom-region-wrap');
  const customRegion = document.getElementById('custom-region');
  const preview = document.getElementById('number-preview');
  const confirmPreview = document.getElementById('confirm-number-preview');
  const dialog = document.getElementById('number-confirm-dialog');
  const confirmed = document.getElementById('confirmed');

  const selectedCode = (select) => select?.selectedOptions[0]?.dataset.code || '';
  const customRegionCode = () => (customRegion?.value.trim().split(/\s+/).at(-1) || 'QT').toUpperCase();
  const updatePreview = () => {
    const monthCode = month.value ? month.value.slice(2, 4) + month.value.slice(5, 7) : '____';
    const ownerCode = owner ? selectedCode(owner) : lockedOwner?.dataset.ownerCode || '__';
    const regionCode = selectedCode(region) === 'QT' ? customRegionCode() : selectedCode(region);
    preview.textContent = `BS-${selectedCode(business)}${selectedCode(fileType)}${ownerCode}${monthCode}____-${regionCode || '__'}`;
    confirmPreview.textContent = preview.textContent;
    const isCustom = selectedCode(region) === 'QT';
    customRegionWrap.hidden = !isCustom;
    customRegion.required = isCustom;
  };
  [business, fileType, owner, month, region, customRegion].filter(Boolean).forEach((field) => field.addEventListener('input', updatePreview));
  updatePreview();
  createForm.addEventListener('submit', (event) => {
    if (confirmed.value === 'yes') return;
    event.preventDefault();
    if (!createForm.reportValidity()) return;
    updatePreview();
    dialog.showModal();
  });
  document.getElementById('confirm-generate').addEventListener('click', (event) => {
    event.preventDefault();
    confirmed.value = 'yes';
    dialog.close();
    createForm.requestSubmit();
  });
}

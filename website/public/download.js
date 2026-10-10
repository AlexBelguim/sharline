// Keep a missing installer from becoming a broken download link.
const button = document.querySelector('#installer-download');
const status = document.querySelector('#download-status');
const installer = 'downloads/SHARDLINE-Setup.exe';

async function checkInstaller() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(installer, { method: 'HEAD', cache: 'no-store', signal: controller.signal });
    const size = Number(response.headers.get('content-length'));
    if (!response.ok || size <= 0 || /text\/html/i.test(response.headers.get('content-type') || '')) {
      throw new Error('Installer unavailable');
    }
    button.href = installer;
    button.removeAttribute('aria-disabled');
    button.removeAttribute('tabindex');
    button.innerHTML = 'Download for Windows <span aria-hidden="true">↓</span>';
    status.textContent = `Ready to download · ${(size / 1024 / 1024).toFixed(1)} MB`;
  } catch {
    button.removeAttribute('href');
    button.setAttribute('aria-disabled', 'true');
    button.setAttribute('tabindex', '-1');
    button.textContent = 'Installer coming soon';
    status.textContent = 'No installer is available right now. Please check back soon.';
  } finally {
    clearTimeout(timeout);
  }
}

checkInstaller();
// Also pick up a newly published build without making visitors reload.
setInterval(checkInstaller, 60000);

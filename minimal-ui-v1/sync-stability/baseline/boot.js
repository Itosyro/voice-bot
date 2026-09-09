(() => {
  'use strict';
  const start = async () => {
    try {
      await window.DVIZH_SYNC_READY;
    } catch (error) {
      console.warn('DVIZH sync bootstrap:', error);
    }
    const script = document.createElement('script');
    script.src = './app.js';
    script.addEventListener('load', () => window.DVIZH_SYNC?.markAppLoaded());
    script.addEventListener('error', () => {
      const toast = document.getElementById('toast');
      if (toast) {
        toast.textContent = 'Не удалось загрузить приложение. Обнови страницу.';
        toast.classList.add('is-visible');
      }
    });
    document.body.appendChild(script);
  };
  start();
})();

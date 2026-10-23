// Sidebar: collapsible (desktop, jadi rel ikon) & overlay (mobile)
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const toggleBtn = document.getElementById('sidebar-toggle');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (!sidebar || !toggleBtn) return;

  const MOBILE_BREAKPOINT = 780;
  const isMobile = () => window.innerWidth <= MOBILE_BREAKPOINT;

  // Terapkan preferensi tersimpan (hanya relevan di layar desktop)
  const savedCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
  if (!isMobile() && savedCollapsed) {
    sidebar.classList.add('collapsed');
    toggleBtn.setAttribute('aria-expanded', 'false');
  }

  function closeMobileSidebar() {
    sidebar.classList.remove('mobile-open');
    if (backdrop) backdrop.classList.remove('show');
    toggleBtn.setAttribute('aria-expanded', 'false');
  }

  toggleBtn.addEventListener('click', () => {
    if (isMobile()) {
      const open = sidebar.classList.toggle('mobile-open');
      if (backdrop) backdrop.classList.toggle('show', open);
      toggleBtn.setAttribute('aria-expanded', String(open));
    } else {
      const collapsed = sidebar.classList.toggle('collapsed');
      toggleBtn.setAttribute('aria-expanded', String(!collapsed));
      localStorage.setItem('sidebarCollapsed', collapsed);
    }
  });

  if (backdrop) backdrop.addEventListener('click', closeMobileSidebar);

  // Di mobile, tutup sidebar otomatis setelah memilih menu
  sidebar.querySelectorAll('.side-link').forEach(link => {
    link.addEventListener('click', () => {
      if (isMobile()) closeMobileSidebar();
    });
  });

  // Reset state overlay saat resize melewati breakpoint
  window.addEventListener('resize', () => {
    if (!isMobile()) closeMobileSidebar();
  });
});

// Dropdown menu user (Profil Saya / Keluar)
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('user-menu-toggle');
  const dropdown = document.getElementById('user-dropdown');
  if (toggle && dropdown) {
    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });
    document.addEventListener('click', () => dropdown.classList.remove('open'));
  }

  // Dropdown aksi (Edit/Batalkan/Hapus) - bisa lebih dari satu di halaman
  document.querySelectorAll('.action-dropdown-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const menu = btn.nextElementSibling;
      document.querySelectorAll('.action-dropdown-menu.open').forEach(m => {
        if (m !== menu) m.classList.remove('open');
      });
      menu.classList.toggle('open');
    });
  });
  document.addEventListener('click', () => {
    document.querySelectorAll('.action-dropdown-menu.open').forEach(m => m.classList.remove('open'));
  });
});

// Live preview rasio DTI di form prediksi (opsional, murni UX, perhitungan asli tetap di backend)
document.addEventListener('DOMContentLoaded', () => {
  const income = document.getElementById('person_income');
  const amount = document.getElementById('loan_amnt');
  if (!income || !amount) return;

  function updateHint() {
    const inc = parseFloat(income.value) || 0;
    const amt = parseFloat(amount.value) || 0;
    if (inc > 0) {
      const ratio = ((amt / inc) * 100).toFixed(1);
      let hint = document.getElementById('dti-hint');
      if (!hint) {
        hint = document.createElement('p');
        hint.id = 'dti-hint';
        hint.style.cssText = 'font-size:12px;color:#5b6577;margin-top:-8px;margin-bottom:16px;';
        amount.closest('.field-row').insertAdjacentElement('afterend', hint);
      }
      hint.textContent = `Estimasi rasio pinjaman terhadap pendapatan: ${ratio}%`;
    }
  }
  income.addEventListener('input', updateHint);
  amount.addEventListener('input', updateHint);
  updateHint();
});

// Quantity controls with min/max and optional autoSubmit
document.querySelectorAll('[data-qty]').forEach(box => {
  const input = box.querySelector('input');
  const minusBtn = box.querySelector('[data-minus]');
  const plusBtn = box.querySelector('[data-plus]');
  const form = box.closest('form');
  const max = parseInt(box.dataset.max, 10) || parseInt(input.getAttribute('max'), 10) || 999;
  const min = parseInt(input.getAttribute('min'), 10) || 1;

  if (minusBtn) {
    minusBtn.onclick = () => {
      const current = parseInt(input.value, 10) || min;
      const nextVal = Math.max(min, current - 1);
      if (current !== nextVal) {
        input.value = nextVal;
        if (box.dataset.autoSubmit === 'true' && form) {
          form.submit();
        }
      }
    };
  }

  if (plusBtn) {
    plusBtn.onclick = () => {
      const current = parseInt(input.value, 10) || min;
      const nextVal = Math.min(max, current + 1);
      if (current !== nextVal) {
        input.value = nextVal;
        if (box.dataset.autoSubmit === 'true' && form) {
          form.submit();
        }
      }
    };
  }
});

// Confirmation handling (Bootstrap modal with window.confirm fallback)
function showConfirmation(message, onConfirm) {
  const modalElem = document.getElementById('deleteConfirmModal');
  const msgElem = document.getElementById('deleteConfirmModalMessage');
  const confirmBtn = document.getElementById('deleteConfirmModalConfirmBtn');

  if (modalElem && msgElem && confirmBtn && window.bootstrap && window.bootstrap.Modal) {
    msgElem.textContent = message;
    const modalInstance = bootstrap.Modal.getOrCreateInstance(modalElem);

    const newConfirmBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

    newConfirmBtn.addEventListener('click', () => {
      modalInstance.hide();
      onConfirm();
    });

    modalInstance.show();
  } else {
    if (window.confirm(message)) {
      onConfirm();
    }
  }
}

// Attach confirmation to forms or buttons with data-confirm
document.addEventListener('submit', function(e) {
  const form = e.target;
  if (!form || !form.matches) return;

  if (form._isConfirmed) return;

  const btn = e.submitter;
  const msg = (btn && btn.getAttribute('data-confirm')) || form.getAttribute('data-confirm');

  if (msg) {
    e.preventDefault();
    showConfirmation(msg, () => {
      form._isConfirmed = true;
      form.submit();
    });
  }
});

// Bulk Delete & Select All checkboxes in Books Dashboard
const selectAllBooks = document.getElementById('selectAllBooks');
const bulkDeleteBtn = document.getElementById('bulkDeleteBtn');
const bulkDeleteForm = document.getElementById('bulkDeleteForm');
const selectedCount = document.getElementById('selectedCount');

function updateBulkDeleteState() {
  const checkboxes = document.querySelectorAll('.book-select-cb');
  const checked = document.querySelectorAll('.book-select-cb:checked');
  const count = checked.length;

  if (selectedCount) {
    selectedCount.textContent = count;
  }
  if (bulkDeleteBtn) {
    bulkDeleteBtn.disabled = (count === 0);
  }
  if (selectAllBooks) {
    selectAllBooks.checked = (checkboxes.length > 0 && count === checkboxes.length);
    selectAllBooks.indeterminate = (count > 0 && count < checkboxes.length);
  }
}

if (selectAllBooks) {
  selectAllBooks.addEventListener('change', function() {
    const checkboxes = document.querySelectorAll('.book-select-cb');
    checkboxes.forEach(cb => {
      cb.checked = selectAllBooks.checked;
    });
    updateBulkDeleteState();
  });
}

document.querySelectorAll('.book-select-cb').forEach(cb => {
  cb.addEventListener('change', updateBulkDeleteState);
});

if (bulkDeleteBtn && bulkDeleteForm) {
  bulkDeleteBtn.addEventListener('click', function(e) {
    e.preventDefault();
    const checked = document.querySelectorAll('.book-select-cb:checked');
    if (checked.length === 0) return;

    const msg = `Delete ${checked.length} selected book(s)? This cannot be undone.`;
    showConfirmation(msg, () => {
      bulkDeleteForm.querySelectorAll('input[name="selected_books"]').forEach(el => el.remove());
      checked.forEach(cb => {
        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'selected_books';
        hidden.value = cb.value;
        bulkDeleteForm.appendChild(hidden);
      });
      bulkDeleteForm.submit();
    });
  });
}



document.querySelectorAll('[data-wish]').forEach(b => b.onclick = () => {
  const on = b.classList.toggle('text-danger');
  b.querySelector('i').className = on ? 'bi bi-heart-fill' : 'bi bi-heart';
});

// AI summary (TEAM 4: replace the demo block with fetch(btn.dataset.url) -> Gemini view)
const aiBtn = document.getElementById('aiBtn');
if (aiBtn) aiBtn.onclick = () => {
  const out = document.getElementById('aiOut');
  out.textContent = 'Generating summary...';
  aiBtn.disabled = true;
  setTimeout(() => {
    out.textContent = aiBtn.dataset.demo;
    aiBtn.disabled = false;
    aiBtn.textContent = 'Regenerate summary';
  }, 900);
};

const filterForm = document.getElementById('filterForm');
if (filterForm) {
  document.querySelectorAll('.filters input, .toolbar select').forEach(i => {
    i.addEventListener('change', () => {
      filterForm.submit();
    });
  });
}

// Left Sidebar - Collapsible desktop & overlay mobile
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
const bsSidebar = document.getElementById('bsSidebar');
const bsLayout = document.getElementById('bsLayout');
const sidebarBackdrop = document.getElementById('sidebarBackdrop');

function isDesktop() {
  return window.innerWidth >= 992;
}

function openMobileSidebar() {
  if (bsSidebar) bsSidebar.classList.add('show');
  if (sidebarBackdrop) sidebarBackdrop.classList.add('show');
  document.body.style.overflow = 'hidden';
}

function closeMobileSidebar() {
  if (bsSidebar) bsSidebar.classList.remove('show');
  if (sidebarBackdrop) sidebarBackdrop.classList.remove('show');
  document.body.style.overflow = '';
}

function toggleSidebar() {
  if (isDesktop()) {
    if (bsLayout) {
      bsLayout.classList.toggle('sidebar-collapsed');
      const isCollapsed = bsLayout.classList.contains('sidebar-collapsed');
      try {
        localStorage.setItem('bookstore_sidebar_collapsed', isCollapsed ? 'true' : 'false');
      } catch (e) {}
    }
  } else {
    if (bsSidebar && bsSidebar.classList.contains('show')) {
      closeMobileSidebar();
    } else {
      openMobileSidebar();
    }
  }
}

// Restore saved desktop sidebar preference
try {
  if (isDesktop() && localStorage.getItem('bookstore_sidebar_collapsed') === 'true') {
    if (bsLayout) bsLayout.classList.add('sidebar-collapsed');
  }
} catch (e) {}

if (sidebarToggle) {
  sidebarToggle.addEventListener('click', (e) => {
    e.preventDefault();
    toggleSidebar();
  });
}

if (sidebarCloseBtn) {
  sidebarCloseBtn.addEventListener('click', (e) => {
    e.preventDefault();
    if (isDesktop()) {
      if (bsLayout) {
        bsLayout.classList.add('sidebar-collapsed');
        try {
          localStorage.setItem('bookstore_sidebar_collapsed', 'true');
        } catch (e) {}
      }
    } else {
      closeMobileSidebar();
    }
  });
}

if (sidebarBackdrop) {
  sidebarBackdrop.addEventListener('click', closeMobileSidebar);
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !isDesktop() && bsSidebar && bsSidebar.classList.contains('show')) {
    closeMobileSidebar();
  }
});

window.addEventListener('resize', () => {
  if (isDesktop() && bsSidebar && bsSidebar.classList.contains('show')) {
    closeMobileSidebar();
  }
});

// --- Navigation Links, Smooth Scrolling & Active State Synchronization ---
const allNavLinks = document.querySelectorAll('.bs-nav .links a, .bs-sidebar-nav .bs-sidebar-link');

function setActiveNav(navKey) {
  if (!navKey) return;
  document.querySelectorAll('.bs-nav .links a').forEach(el => {
    if (el.getAttribute('data-nav') === navKey) {
      el.classList.add('active');
    } else {
      el.classList.remove('active');
    }
  });

  document.querySelectorAll('.bs-sidebar-nav .bs-sidebar-link').forEach(el => {
    if (el.getAttribute('data-nav') === navKey) {
      el.classList.add('active');
    } else {
      el.classList.remove('active');
    }
  });
}

function isHomePage() {
  const p = window.location.pathname;
  return p === '/' || p === '' || p.endsWith('/home') || p.endsWith('/home/');
}

let isProgrammaticScroll = false;
let scrollTimer = null;

function scrollToTarget(targetElem, navKey) {
  if (!targetElem) return;
  isProgrammaticScroll = true;
  clearTimeout(scrollTimer);

  setActiveNav(navKey);

  const navOffset = 70;
  const elementPosition = targetElem.getBoundingClientRect().top;
  const offsetPosition = elementPosition + window.pageYOffset - navOffset;

  window.scrollTo({
    top: Math.max(0, offsetPosition),
    behavior: 'smooth'
  });

  scrollTimer = setTimeout(() => {
    isProgrammaticScroll = false;
  }, 900);
}

// Click handling for navbar and sidebar items
allNavLinks.forEach(link => {
  link.addEventListener('click', function(e) {
    const navKey = this.getAttribute('data-nav');
    const href = this.getAttribute('href') || '';

    if (!isDesktop()) {
      closeMobileSidebar();
    }

    if (isHomePage()) {
      if (navKey === 'home') {
        e.preventDefault();
        window.history.pushState(null, '', window.location.pathname);
        isProgrammaticScroll = true;
        clearTimeout(scrollTimer);
        setActiveNav('home');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        scrollTimer = setTimeout(() => { isProgrammaticScroll = false; }, 900);
        return;
      }

      if (href.includes('#')) {
        const hash = href.substring(href.indexOf('#'));
        const target = document.querySelector(hash);
        if (target) {
          e.preventDefault();
          window.history.pushState(null, '', hash);
          scrollToTarget(target, navKey);
          return;
        }
      }
    }
  });
});

// ScrollSpy on Homepage to dynamically highlight sections as the user scrolls
function initScrollSpy() {
  if (!isHomePage()) return;

  const sections = [
    { key: 'about', elem: document.getElementById('about') },
    { key: 'new-arrivals', elem: document.getElementById('new-arrivals') },
    { key: 'best-sellers', elem: document.getElementById('best-sellers') },
    { key: 'categories', elem: document.getElementById('categories') }
  ];

  window.addEventListener('scroll', () => {
    if (isProgrammaticScroll) return;

    const scrollY = window.scrollY || window.pageYOffset;
    if (scrollY < 180) {
      setActiveNav('home');
      return;
    }

    const checkPoint = scrollY + (window.innerHeight * 0.35);

    for (const sec of sections) {
      if (sec.elem) {
        const top = sec.elem.offsetTop - 85;
        const bottom = top + sec.elem.offsetHeight;
        if (checkPoint >= top && checkPoint <= bottom) {
          setActiveNav(sec.key);
          return;
        }
      }
    }
  }, { passive: true });
}

// Sync active state on page load and hash change
function syncNavState() {
  const path = window.location.pathname;
  const hash = window.location.hash;

  if (isHomePage()) {
    if (hash) {
      const navKey = hash.replace('#', '');
      const target = document.querySelector(hash);
      if (target) {
        setActiveNav(navKey);
        setTimeout(() => {
          scrollToTarget(target, navKey);
        }, 100);
        return;
      }
    }
    setActiveNav('home');
  } else if (path.includes('/books/')) {
    setActiveNav('books');
  } else if (path.includes('/newsletter/')) {
    setActiveNav('about');
  }
}

window.addEventListener('hashchange', () => {
  if (isHomePage() && window.location.hash) {
    const navKey = window.location.hash.replace('#', '');
    const target = document.querySelector(window.location.hash);
    if (target) {
      scrollToTarget(target, navKey);
    }
  }
});

syncNavState();
initScrollSpy();

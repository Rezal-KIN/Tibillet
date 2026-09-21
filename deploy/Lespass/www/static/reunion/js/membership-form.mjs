const attachMembershipForm = (root = document) => {
  const form = root.querySelector('#membership-form');
  if (!form) return;
  if (form.dataset.membershipValidators === '1') return;
  form.dataset.membershipValidators = '1';

  const emailInput = form.querySelector('#membership-email');
  const confirmInput = form.querySelector('#confirm-email');
  const errorDiv = form.querySelector('#email-error');

  const validateEmails = () => {
    if (!emailInput || !confirmInput || !errorDiv) return true;
    const email = emailInput.value || '';
    const confirmEmail = confirmInput.value || '';
    if (email !== confirmEmail) {
      confirmInput.setCustomValidity('Les adresses e-mail ne correspondent pas.');
      errorDiv.textContent = 'Les adresses e-mail ne correspondent pas.';
      return false;
    }
    confirmInput.setCustomValidity('');
    errorDiv.textContent = '';
    return true;
  };

  const validateMsRequired = () => {
    let ok = true;
    const groups = form.querySelectorAll('[data-ms-required="true"]');
    groups.forEach(group => {
      const inputName = group.getAttribute('data-input-name');
      const boxes = group.querySelectorAll(`input[type="checkbox"][name="${inputName}"]`);
      const anyChecked = Array.from(boxes).some(cb => cb.checked);
      const error = group.querySelector('[data-ms-error]');
      if (!anyChecked) {
        ok = false;
        if (error) {
          error.textContent = group.getAttribute('data-error-message') || 'Veuillez cocher au moins une option.';
          error.style.display = 'block';
        }
        boxes.forEach(cb => cb.setAttribute('aria-invalid', 'true'));
      } else {
        if (error) {
          error.textContent = '';
          error.style.display = 'none';
        }
        boxes.forEach(cb => cb.removeAttribute('aria-invalid'));
      }
    });
    return ok;
  };

  const validateBlRequired = () => {
    let ok = true;
    const groups = form.querySelectorAll('[data-bl-required="true"]');
    groups.forEach(group => {
      const input = group.querySelector('input[type="checkbox"]');
      const error = group.querySelector('[data-bl-error]');
      if (!input) return;
      if (!input.checked) {
        ok = false;
        if (error) {
          error.textContent = group.getAttribute('data-error-message') || 'Veuillez cocher cette case.';
          error.style.display = 'block';
        }
        input.setAttribute('aria-invalid', 'true');
      } else {
        if (error) {
          error.textContent = '';
          error.style.display = 'none';
        }
        input.removeAttribute('aria-invalid');
      }
    });
    return ok;
  };

  const validateAll = () => {
    const okEmails = validateEmails();
    const okMs = validateMsRequired();
    const okBl = validateBlRequired();
    return okEmails && okMs && okBl;
  };

  form.addEventListener('submit', (event) => {
    if (!validateAll()) {
      event.preventDefault();
    }
  });

  form.addEventListener('htmx:configRequest', (event) => {
    if (!validateAll()) {
      event.preventDefault();
    }
  });

  if (emailInput && confirmInput) {
    emailInput.addEventListener('input', validateEmails);
    confirmInput.addEventListener('input', validateEmails);
  }

  form.addEventListener('change', (event) => {
    const target = event.target;
    if (target && target.closest('[data-ms-required="true"]')) {
      validateMsRequired();
    }
    if (target && target.closest('[data-bl-required="true"]')) {
      validateBlRequired();
    }
  });
};

const removeMembershipLinks = (root = document) => {
  const candidates = root.querySelectorAll(
    'a[href="/memberships/"], a[href^="/memberships/"], a[href="/my_account/"], a[href^="/my_account/"], button, a'
  );
  candidates.forEach((link) => {
    const txt = (link.textContent || '').toLowerCase();
    const hasMembershipLabel = txt.includes('adhésion') || txt.includes('adhesion') || txt.includes('subscription');
    const hasMembershipIcon = !!link.querySelector('.bi-postcard');
    if (!hasMembershipLabel && !hasMembershipIcon) {
      return;
    }
    const col = link.closest('.col-md');
    if (col) {
      col.remove();
      return;
    }
    const navItem = link.closest('.nav-item');
    if (navItem) {
      navItem.remove();
      return;
    }
    const listItem = link.closest('li');
    if (listItem) {
      listItem.remove();
      return;
    }
    link.remove();
  });
};

const removeAgendaLinks = (root = document) => {
  const links = root.querySelectorAll('a[href="/event/"], a[href^="/event/"]');
  links.forEach((link) => {
    const col = link.closest('.col-md');
    if (col) {
      col.remove();
      return;
    }
    const navItem = link.closest('.nav-item');
    if (navItem) {
      navItem.remove();
      return;
    }
    const listItem = link.closest('li');
    if (listItem) {
      listItem.remove();
      return;
    }
    link.remove();
  });
};

const addGalaSiteLinks = (root = document) => {
  const url = 'https://galas-am-aix.com';
  const galaLabel = '<i class="bi bi-globe2 me-1"></i> Site du Gala';

  // Navbar link
  const navList = root.querySelector('.navbar .navbar-nav.me-auto');
  if (navList && !navList.querySelector('[data-gala-site-link="1"]')) {
    const li = document.createElement('li');
    li.className = 'nav-item';
    const a = document.createElement('a');
    a.className = 'nav-link';
    a.href = url;
    a.setAttribute('data-gala-site-link', '1');
    a.innerHTML = galaLabel;
    li.appendChild(a);
    navList.appendChild(li);
  }

  // Home buttons row
  const homeRow = root.querySelector('.home-bg .row');
  if (homeRow && !homeRow.querySelector('[data-gala-site-btn="1"]')) {
    const col = document.createElement('div');
    col.className = 'col-md mb-3';
    const a = document.createElement('a');
    a.className = 'btn btn-lg btn-primary d-block my-3';
    a.href = url;
    a.setAttribute('data-gala-site-btn', '1');
    a.innerHTML = galaLabel;
    col.appendChild(a);
    homeRow.appendChild(col);
  }

  // Footer link
  const footerList = root.querySelector('footer .nav.flex-column');
  if (footerList && !footerList.querySelector('[data-gala-site-footer="1"]')) {
    const li = document.createElement('li');
    li.className = 'nav-item';
    const a = document.createElement('a');
    a.className = 'nav-link';
    a.href = url;
    a.setAttribute('data-gala-site-footer', '1');
    a.innerHTML = galaLabel;
    li.appendChild(a);
    footerList.appendChild(li);
  }
};

const addCardManagementLinks = (root = document) => {
  // Le panneau login peut exister même quand l'utilisateur est connecté.
  // On se base donc sur la présence du lien "Mon compte" dans la navbar.
  const isAuthenticated = !!root.querySelector('.navbar a[href="/my_account/"]');
  const requiresLogin = !isAuthenticated;
  const cardManagementLabel = 'Recharger / Gestion carte';

  const buildLink = () => {
    const a = document.createElement('a');
    a.className = 'nav-link';
    a.innerHTML = '<i class="bi bi-credit-card-2-front me-1"></i> ' + cardManagementLabel;
    a.setAttribute('data-card-management-link', '1');
    if (requiresLogin) {
      a.href = '#';
      a.setAttribute('data-bs-toggle', 'offcanvas');
      a.setAttribute('data-bs-target', '#loginPanel');
      a.setAttribute('aria-controls', 'loginPanel');
    } else {
      a.href = '/my_account/';
      a.setAttribute('hx-get', '/my_account/');
      a.setAttribute('hx-target', 'body');
      a.setAttribute('hx-push-url', 'true');
    }
    return a;
  };

  // Navbar link
  const navList = root.querySelector('.navbar .navbar-nav.me-auto');
  if (navList && !navList.querySelector('[data-card-management-link="1"]')) {
    const li = document.createElement('li');
    li.className = 'nav-item';
    li.appendChild(buildLink());
    navList.appendChild(li);
  }

  // Home buttons row
  const homeRow = root.querySelector('.home-bg .row');
  if (homeRow && !homeRow.querySelector('[data-card-management-btn="1"]')) {
    const col = document.createElement('div');
    col.className = 'col-md mb-3';
    const a = document.createElement('a');
    a.className = 'btn btn-lg btn-primary d-block my-3';
    a.innerHTML = '<i class="bi bi-credit-card-2-front me-1"></i> ' + cardManagementLabel;
    a.setAttribute('data-card-management-btn', '1');
    if (requiresLogin) {
      a.href = '#';
      a.setAttribute('data-bs-toggle', 'offcanvas');
      a.setAttribute('data-bs-target', '#loginPanel');
      a.setAttribute('aria-controls', 'loginPanel');
    } else {
      a.href = '/my_account/';
      a.setAttribute('hx-get', '/my_account/');
      a.setAttribute('hx-target', 'body');
      a.setAttribute('hx-push-url', 'true');
    }
    col.appendChild(a);
    homeRow.appendChild(col);
  }

  // Footer link
  const footerList = root.querySelector('footer .nav.flex-column');
  if (footerList && !footerList.querySelector('[data-card-management-footer="1"]')) {
    const li = document.createElement('li');
    li.className = 'nav-item';
    const a = buildLink();
    a.className = 'nav-link';
    a.setAttribute('data-card-management-footer', '1');
    li.appendChild(a);
    footerList.appendChild(li);
  }
};

const updateHomeManagementTitle = (root = document) => {
  const title = root.querySelector('.home-bg h1.display-1');
  if (!title) return;
  title.innerHTML = '<i class="bi bi-credit-card-2-front me-2"></i> Espace de gestion carte';

  const subtitle = root.querySelector('.home-bg p.lead.fs-4');
  if (subtitle) {
    subtitle.textContent = 'Rechargez votre carte et accedez a votre espace personnel en quelques clics.';
  }

  const secondaryLead = root.querySelector('.home-bg p.lead:not(.fs-4)');
  if (secondaryLead) {
    secondaryLead.textContent = '';
    secondaryLead.style.display = 'none';
  }
};

const removeLanguageAndThemeOptions = (root = document) => {
  const languageBtn = root.querySelector('#languageDropdown');
  if (languageBtn) {
    const item = languageBtn.closest('.nav-item');
    if (item) {
      item.remove();
    } else {
      languageBtn.remove();
    }
  }

  const themeBtn = root.querySelector('#themeToggle');
  if (themeBtn) {
    const item = themeBtn.closest('.nav-item');
    if (item) {
      item.remove();
    } else {
      themeBtn.remove();
    }
  }
};

const replaceNavbarBrandWithLogo = (root = document) => {
  const brand = root.querySelector('.navbar .navbar-brand');
  if (!brand) return;
  if (brand.querySelector('img[data-brand-logo="1"]')) return;
  brand.textContent = '';
  const img = document.createElement('img');
  img.src = '/static/reunion/img/logo.webp';
  img.alt = 'Logo';
  img.setAttribute('data-brand-logo', '1');
  img.className = 'navbar-brand-logo';
  brand.appendChild(img);
};

const setCustomFavicon = () => {
  const faviconHref = '/static/reunion/img/logo.webp';
  const head = document.head;
  if (!head) return;
  let icon = head.querySelector('link[rel="icon"][data-custom-favicon="1"]');
  if (!icon) {
    icon = document.createElement('link');
    icon.setAttribute('rel', 'icon');
    icon.setAttribute('data-custom-favicon', '1');
    head.appendChild(icon);
  }
  icon.setAttribute('type', 'image/webp');
  icon.setAttribute('href', faviconHref);
};

const renameEntityLabel = (root = document) => {
  const fromNames = new Set(['KIN', 'Kin']);
  const target = 'Gala-am-Aix';
  const selectors = [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'span', 'a', 'strong', 'small', 'label'
  ];
  root.querySelectorAll(selectors.join(',')).forEach((el) => {
    const text = (el.textContent || '').trim();
    if (fromNames.has(text)) {
      el.textContent = target;
    }
  });
};

export const init = () => {
  attachMembershipForm(document);
  removeMembershipLinks(document);
  removeAgendaLinks(document);
  addGalaSiteLinks(document);
  addCardManagementLinks(document);
  updateHomeManagementTitle(document);
  removeLanguageAndThemeOptions(document);
  replaceNavbarBrandWithLogo(document);
  setCustomFavicon();
  renameEntityLabel(document);
  document.body.addEventListener('htmx:afterSwap', (event) => {
    attachMembershipForm(event.target || document);
    removeMembershipLinks(event.target || document);
    removeAgendaLinks(event.target || document);
    addGalaSiteLinks(event.target || document);
    addCardManagementLinks(event.target || document);
    updateHomeManagementTitle(event.target || document);
    removeLanguageAndThemeOptions(event.target || document);
    replaceNavbarBrandWithLogo(event.target || document);
    setCustomFavicon();
    renameEntityLabel(event.target || document);
  });
};

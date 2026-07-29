/**
 * BiteRig — Frontend Application Logic
 *
 * Manages:
 *  - View switching (Home ↔ Loading ↔ Recipe)
 *  - Image selection (file upload + getUserMedia camera)
 *  - Filter & nationality state
 *  - API call to /api/cook
 *  - Recipe rendering
 *  - Toast notifications
 */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let selectedFile    = null;
let selectedFilters = new Set();
let selectedNationality = null;
let cameraStream    = null;
let cameraFacing    = 'environment'; // 'environment' = back, 'user' = front
let loadingTimer    = null;
let recipeSource    = 'home'; // tracks where to go back from recipe view

// ---------------------------------------------------------------------------
// View Management
// ---------------------------------------------------------------------------
const VIEWS = ['view-home', 'view-loading', 'view-recipe', 'view-recipes'];

function showView(name) {
  const fullId = name.startsWith('view-') ? name : `view-${name}`;
  VIEWS.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.classList.remove('active');
      if (id === 'view-loading') el.style.position = '';
    }
  });

  const target = document.getElementById(fullId);
  if (!target) return;

  // Loading view needs special full-screen treatment
  if (fullId === 'view-loading') {
    target.style.position = 'fixed';
    target.style.inset = '0';
    target.style.zIndex = '100';
  } else {
    target.style.position = '';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  target.classList.add('active');

  // Update the name variable so openSavedRecipe knows which view is "back"
  if (fullId === 'view-recipes') recipeSource = 'recipes';
  if (fullId === 'view-home')    recipeSource = 'home';
}

// ---------------------------------------------------------------------------
// Toast Notifications
// ---------------------------------------------------------------------------
let toastTimeout = null;

function showToast(message, type = 'error') {
  const toast   = document.getElementById('toast');
  const msgEl   = document.getElementById('toast-msg');
  const iconEl  = document.getElementById('toast-icon');

  msgEl.textContent = message;
  iconEl.textContent = type === 'error' ? 'error' : 'check_circle';

  if (type === 'success') {
    toast.style.background = '#31312d'; // inverse-surface
  } else {
    toast.style.background = '#ba1a1a'; // error color
  }

  toast.classList.add('show');

  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.classList.remove('show');
  }, 3500);
}

// ---------------------------------------------------------------------------
// Image Selection — File Upload
// ---------------------------------------------------------------------------
function handleFileSelect(input) {
  const file = input.files[0];
  if (!file) return;

  // Validate type
  if (!file.type.startsWith('image/')) {
    showToast('Please select an image file (JPEG, PNG, WebP)');
    return;
  }

  // Validate size (10 MB)
  if (file.size > 10 * 1024 * 1024) {
    showToast('Image is too large. Please use a photo under 10 MB.');
    return;
  }

  selectedFile = file;
  showImagePreview(URL.createObjectURL(file));
  input.value = ''; // reset so same file can be re-selected
}

function showImagePreview(objectUrl) {
  const placeholder = document.getElementById('viewfinder-placeholder');
  const preview     = document.getElementById('viewfinder-preview');
  const img         = document.getElementById('preview-img');
  const viewfinder  = document.getElementById('viewfinder');

  img.src = objectUrl;
  placeholder.classList.add('hidden');
  preview.classList.remove('hidden');

  // Update viewfinder border to solid
  viewfinder.classList.remove('border-dashed', 'border-outline-variant');
  viewfinder.classList.add('border-primary-container');

  showToast('Photo ready! Hit COOK 🔥', 'success');
}

// ---------------------------------------------------------------------------
// Camera — getUserMedia
// ---------------------------------------------------------------------------
async function openCamera() {
  // Try getUserMedia first
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    try {
      await startCameraStream();
      document.getElementById('camera-modal').classList.remove('hidden');
    } catch (err) {
      console.warn('getUserMedia failed, falling back to input capture:', err);
      document.getElementById('camera-input-fallback').click();
    }
  } else {
    // Older mobile browsers
    document.getElementById('camera-input-fallback').click();
  }
}

async function startCameraStream() {
  // Stop any existing stream
  if (cameraStream) {
    cameraStream.getTracks().forEach(t => t.stop());
  }

  const constraints = {
    video: {
      facingMode: { ideal: cameraFacing },
      width: { ideal: 1280 },
      height: { ideal: 1280 },
    }
  };

  cameraStream = await navigator.mediaDevices.getUserMedia(constraints);
  const video = document.getElementById('camera-feed');
  video.srcObject = cameraStream;

  // Mirror front camera; don't mirror back camera
  video.style.transform = cameraFacing === 'user' ? 'scaleX(-1)' : 'scaleX(1)';
}

function switchCamera() {
  cameraFacing = cameraFacing === 'environment' ? 'user' : 'environment';
  startCameraStream().catch(err => {
    showToast('Could not switch camera');
    console.error(err);
  });
}

function closeCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach(t => t.stop());
    cameraStream = null;
  }
  document.getElementById('camera-modal').classList.add('hidden');
  document.getElementById('camera-feed').srcObject = null;
}

function capturePhoto() {
  const video  = document.getElementById('camera-feed');
  const canvas = document.createElement('canvas');
  canvas.width  = video.videoWidth;
  canvas.height = video.videoHeight;

  const ctx = canvas.getContext('2d');

  // Un-mirror front camera capture
  if (cameraFacing === 'user') {
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
  }

  ctx.drawImage(video, 0, 0);

  canvas.toBlob(blob => {
    if (!blob) { showToast('Capture failed. Try again.'); return; }

    selectedFile = new File([blob], 'capture.jpg', { type: 'image/jpeg' });
    showImagePreview(URL.createObjectURL(blob));
    closeCamera();
  }, 'image/jpeg', 0.92);
}

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------
function toggleFilter(btn) {
  const filter = btn.dataset.filter;
  const isActive = selectedFilters.has(filter);

  if (isActive) {
    selectedFilters.delete(filter);
    btn.classList.remove('bg-secondary-container', 'text-on-secondary-container', 'border-secondary-container');
    btn.classList.add('bg-surface-container-high', 'border-outline-variant', 'text-on-surface-variant');
  } else {
    selectedFilters.add(filter);
    btn.classList.remove('bg-surface-container-high', 'border-outline-variant', 'text-on-surface-variant');
    btn.classList.add('bg-secondary-container', 'text-on-secondary-container', 'border-secondary-container');
  }
}

// ---------------------------------------------------------------------------
// Nationality
// ---------------------------------------------------------------------------
function toggleNationality(el) {
  const nat = el.dataset.nationality;

  // Deselect all first
  document.querySelectorAll('.nationality-circle').forEach(item => {
    const circle = item.querySelector('.nat-circle');
    const label  = item.querySelector('.nat-label');
    circle.classList.remove('bg-primary-container', 'text-on-primary-container', 'border-primary-container', 'scale-110');
    circle.classList.add('bg-surface-container-highest', 'text-on-surface-variant', 'border-transparent');
    label.classList.remove('text-primary', 'font-bold');
    label.classList.add('text-on-surface-variant');
  });

  if (selectedNationality === nat) {
    // Already selected — deselect (toggle off)
    selectedNationality = null;
    return;
  }

  // Select new
  selectedNationality = nat;
  const circle = el.querySelector('.nat-circle');
  const label  = el.querySelector('.nat-label');
  circle.classList.remove('bg-surface-container-highest', 'text-on-surface-variant', 'border-transparent');
  circle.classList.add('bg-primary-container', 'text-on-primary-container', 'border-primary-container', 'scale-110');
  label.classList.remove('text-on-surface-variant');
  label.classList.add('text-primary', 'font-bold');
}

// ---------------------------------------------------------------------------
// Cook Flow
// ---------------------------------------------------------------------------
const LOADING_TIPS = [
  'Analysing your ingredients…',
  'Crafting the perfect recipe…',
  'Seasoning with AI magic ✨',
  'Consulting the chef…',
  'Almost ready to plate up!',
];

function startLoadingAnimation() {
  const bar     = document.getElementById('progress-bar');
  const tipEl   = document.getElementById('loading-tip');
  let progress  = 10;
  let tipIndex  = 0;

  // Progress simulation
  const progressInterval = setInterval(() => {
    progress = Math.min(progress + Math.random() * 8, 88);
    bar.style.width = `${progress}%`;
  }, 600);

  // Tip rotation
  const tipInterval = setInterval(() => {
    tipIndex = (tipIndex + 1) % LOADING_TIPS.length;
    tipEl.style.opacity = '0';
    setTimeout(() => {
      tipEl.textContent = LOADING_TIPS[tipIndex];
      tipEl.style.opacity = '1';
    }, 300);
  }, 2500);

  // Store intervals for cleanup
  loadingTimer = { progressInterval, tipInterval, bar };
}

function stopLoadingAnimation() {
  if (loadingTimer) {
    clearInterval(loadingTimer.progressInterval);
    clearInterval(loadingTimer.tipInterval);
    if (loadingTimer.bar) loadingTimer.bar.style.width = '100%';
    loadingTimer = null;
  }
}

async function startCook() {
  if (!selectedFile) {
    showToast('Please add a photo of your ingredients first! 📸');
    // Shake the viewfinder for visual feedback
    const vf = document.getElementById('viewfinder');
    vf.classList.add('border-error');
    setTimeout(() => vf.classList.remove('border-error'), 1500);
    return;
  }

  showView('loading');
  startLoadingAnimation();
  document.getElementById('loading-tip').textContent = LOADING_TIPS[0];

  try {
    const formData = new FormData();
    formData.append('image', selectedFile);
    formData.append('filters', JSON.stringify([...selectedFilters]));
    if (selectedNationality) {
      formData.append('nationality', selectedNationality);
    }

    const response = await fetch(`${API_BASE_URL}/api/cook`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      let errMsg = `Server error (${response.status})`;
      try {
        const err = await response.json();
        errMsg = err.detail || errMsg;
      } catch (_) { /* ignore */ }
      throw new Error(errMsg);
    }

    const recipe = await response.json();
    stopLoadingAnimation();
    renderRecipe(recipe);
    showView('recipe');

  } catch (err) {
    stopLoadingAnimation();
    console.error('Cook error:', err);
    showView('home');

    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      showToast('Cannot reach the server. Is the backend running? 🔌');
    } else {
      showToast(err.message || 'Something went wrong. Please try again.');
    }
  }
}

// ---------------------------------------------------------------------------
// Recipe Rendering
// ---------------------------------------------------------------------------
function renderRecipe(recipe) {
  // Name
  const nameEl = document.getElementById('recipe-name');
  nameEl.textContent = recipe.recipe_name || 'Mystery Dish';

  // Hero image — switch between real photo and brand gradient
  const heroImg      = document.getElementById('recipe-hero-img');
  const heroGradient = document.getElementById('recipe-hero-gradient');
  const heroCircles  = document.getElementById('recipe-hero-circles');

  if (recipe.image_url) {
    heroImg.style.backgroundImage = `url('${recipe.image_url}')`;
    heroImg.style.display  = 'block';
    // Fade it in smoothly
    requestAnimationFrame(() => { heroImg.style.opacity = '1'; });
    // Dark bottom overlay for text readability over photo
    heroGradient.style.background =
      'linear-gradient(to top, rgba(0,0,0,0.90) 0%, rgba(0,0,0,0.55) 40%, rgba(0,0,0,0.10) 100%)';
    heroCircles.style.display = 'none';
    // Fallback: if image fails to load, revert to brand gradient
    const probe = new Image();
    probe.onerror = () => {
      heroImg.style.display = 'none';
      heroGradient.style.background = 'linear-gradient(135deg, #ff9f1c 0%, #895100 60%, #7f4c7f 100%)';
      heroCircles.style.display = 'block';
    };
    probe.src = recipe.image_url;
  } else {
    heroImg.style.display  = 'none';
    heroImg.style.opacity  = '0';
    heroGradient.style.background = 'linear-gradient(135deg, #ff9f1c 0%, #895100 60%, #7f4c7f 100%)';
    heroCircles.style.display = 'block';
  }

  // Description
  const descEl = document.getElementById('recipe-description');
  descEl.textContent = recipe.description || '';

  // Tags
  const tagsContainer = document.getElementById('recipe-tags');
  tagsContainer.innerHTML = '';
  const tags = recipe.tags || [];
  tags.forEach(tag => {
    const span = document.createElement('span');
    span.className = 'bg-white/25 backdrop-blur-sm text-white font-label-sm text-label-sm px-3 py-1 rounded-full uppercase tracking-wider border border-white/20';
    span.textContent = tag;
    tagsContainer.appendChild(span);
  });

  // Meta
  document.getElementById('recipe-prep').textContent      = recipe.prep_time   || '—';
  document.getElementById('recipe-cook').textContent      = recipe.cook_time   || '—';
  document.getElementById('recipe-difficulty').textContent = recipe.difficulty  || '—';
  document.getElementById('recipe-servings').textContent  = recipe.servings    || '—';

  // Detected ingredients
  const detectedEl = document.getElementById('detected-ingredients');
  detectedEl.innerHTML = '';
  (recipe.detected_ingredients || []).forEach(ing => {
    detectedEl.appendChild(createIngredientPill(ing, 'primary'));
  });

  // Additional ingredients
  const additionalEl = document.getElementById('additional-ingredients');
  const additionalSection = document.getElementById('additional-section');
  additionalEl.innerHTML = '';
  const additional = recipe.additional_ingredients || [];
  if (additional.length > 0) {
    additional.forEach(ing => {
      additionalEl.appendChild(createIngredientPill(ing, 'secondary'));
    });
    additionalSection.classList.remove('hidden');
  } else {
    additionalSection.classList.add('hidden');
  }

  // Steps
  const stepsEl = document.getElementById('recipe-steps');
  stepsEl.innerHTML = '';
  const steps = recipe.steps || [];
  steps.forEach((step, index) => {
    const isLast = index === steps.length - 1;
    const stepEl = document.createElement('div');
    stepEl.className = `step-card flex items-start gap-md p-md rounded-lg ${
      !isLast ? 'border-b-2 border-outline-variant/20' : ''
    }`;
    stepEl.innerHTML = `
      <div class="font-display-lg text-display-lg text-primary flex-shrink-0 leading-none select-none">
        ${step.step}
      </div>
      <div class="flex flex-col gap-1 pt-1">
        ${step.title ? `<h4 class="font-label-lg text-label-lg text-on-surface-variant uppercase tracking-wider">${escHtml(step.title)}</h4>` : ''}
        <p class="font-body-lg text-body-lg text-on-surface">${escHtml(step.instruction)}</p>
      </div>
    `;
    stepsEl.appendChild(stepEl);
  });

  // Pro tip
  const tipSection = document.getElementById('tip-section');
  const tipEl = document.getElementById('recipe-tip');
  if (recipe.tips) {
    tipEl.textContent = recipe.tips;
    tipSection.classList.remove('hidden');
  } else {
    tipSection.classList.add('hidden');
  }
}

// ---------------------------------------------------------------------------
// Recipes History
// ---------------------------------------------------------------------------

/** Format ISO timestamp to a human-friendly "X hours ago" string. */
function timeAgo(isoString) {
  const then  = new Date(isoString);
  const diff  = (Date.now() - then.getTime()) / 1000; // seconds
  if (diff < 60)             return 'Just now';
  if (diff < 3600)           return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400)          return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7)      return `${Math.floor(diff / 86400)}d ago`;
  return then.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Gradient palette for recipe cards (cycles by index). */
const CARD_GRADIENTS = [
  'from-[#ff9f1c] to-[#895100]',
  'from-[#7f4c7f] to-[#330638]',
  'from-[#496800] to-[#141f00]',
  'from-[#895100] to-[#7f4c7f]',
  'from-[#ff9f1c] to-[#7f4c7f]',
];

/** Fetch saved recipes from backend and render the list. */
async function loadRecipesView() {
  const listEl    = document.getElementById('recipes-list');
  const emptyEl   = document.getElementById('recipes-empty');
  const loadingEl = document.getElementById('recipes-loading');
  const errorEl   = document.getElementById('recipes-error');

  // Reset states
  [emptyEl, errorEl, listEl].forEach(el => {
    el.classList.add('hidden');
    el.style.display = '';
  });
  loadingEl.classList.remove('hidden');
  loadingEl.style.display = 'flex';
  listEl.innerHTML = '';

  try {
    const resp = await fetch(`${API_BASE_URL}/api/recipes`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const entries = await resp.json();

    loadingEl.classList.add('hidden');
    loadingEl.style.display = '';

    if (!entries.length) {
      emptyEl.classList.remove('hidden');
      emptyEl.style.display = 'flex';
      return;
    }

    entries.forEach((entry, idx) => {
      listEl.appendChild(buildRecipeCard(entry, idx));
    });

  } catch (err) {
    console.error('loadRecipesView error:', err);
    loadingEl.classList.add('hidden');
    loadingEl.style.display = '';
    errorEl.classList.remove('hidden');
    errorEl.style.display = 'flex';
  }
}

/** Build a single recipe history card DOM element. */
function buildRecipeCard(entry, idx) {
  const recipe     = entry.recipe || {};
  const name       = recipe.recipe_name || 'Unnamed Recipe';
  const created    = entry.created_at   || '';
  const filters    = (entry.filters     || []).join(', ');
  const nat        = entry.nationality  ? `${entry.nationality} · ` : '';
  const difficulty = recipe.difficulty  || '';
  const cookTime   = recipe.cook_time   || '';
  const gradient   = CARD_GRADIENTS[idx % CARD_GRADIENTS.length];
  const id         = entry.id;
  const imgUrl     = recipe.image_url   || null;

  // Thumbnail: real dish photo if available, else coloured gradient icon
  const thumbHtml = imgUrl
    ? `<div class="w-14 h-14 flex-shrink-0 relative">
         <img src="${escHtml(imgUrl)}"
              class="w-14 h-14 rounded-full object-cover shadow-md"
              alt="${escHtml(name)}"
              onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"/>
         <div class="w-14 h-14 rounded-full bg-gradient-to-br ${gradient}
                     items-center justify-center shadow-md hidden absolute inset-0">
           <span class="material-symbols-outlined text-white text-[26px]" style="font-variation-settings:'FILL' 1;">restaurant</span>
         </div>
       </div>`
    : `<div class="w-14 h-14 flex-shrink-0 rounded-full bg-gradient-to-br ${gradient}
                 flex items-center justify-center shadow-md">
         <span class="material-symbols-outlined text-white text-[26px]" style="font-variation-settings:'FILL' 1;">restaurant</span>
       </div>`;

  const card = document.createElement('div');
  card.className = 'bg-surface-container-lowest rounded-xl shadow-chef overflow-hidden transition-all hover:shadow-[0_16px_50px_rgba(100,53,102,0.20)] hover:-translate-y-0.5';
  card.innerHTML = `
    <div class="flex items-center gap-md p-md cursor-pointer" onclick="openSavedRecipe('${escHtml(id)}')">
      ${thumbHtml}
      <div class="flex flex-col gap-[2px] flex-1 min-w-0">
        <h3 class="font-headline-md text-headline-md text-on-surface truncate">${escHtml(name)}</h3>
        <p class="font-label-sm text-label-sm text-on-surface-variant truncate">
          ${escHtml(nat)}${escHtml(difficulty)}${cookTime ? ` · ${escHtml(cookTime)}` : ''}
        </p>
        <p class="font-label-sm text-label-sm text-on-surface-variant/70">
          ${filters ? escHtml(filters) + ' · ' : ''}${timeAgo(created)}
        </p>
      </div>
      <span class="material-symbols-outlined text-on-surface-variant flex-shrink-0">chevron_right</span>
    </div>
    <div class="border-t border-outline-variant/20 px-md py-xs flex justify-end">
      <button onclick="event.stopPropagation(); deleteRecipeEntry('${escHtml(id)}', this)"
              class="flex items-center gap-1 text-error font-label-sm text-label-sm hover:bg-error-container/40 px-3 py-1 rounded-full transition-colors">
        <span class="material-symbols-outlined text-[14px]">delete</span> Delete
      </button>
    </div>
  `;
  return card;
}

/** Open a saved recipe entry in the recipe view. */
async function openSavedRecipe(recipeId) {
  try {
    const resp = await fetch(`${API_BASE_URL}/api/recipes/${encodeURIComponent(recipeId)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const entry  = await resp.json();
    const recipe = entry.recipe;
    if (!recipe) throw new Error('Invalid recipe data');

    recipeSource = 'recipes'; // back button goes to recipes list
    renderRecipe(recipe);
    showView('recipe');

  } catch (err) {
    showToast('Could not load recipe. Try again.');
    console.error('openSavedRecipe error:', err);
  }
}

/** Delete a recipe and remove its card from the DOM. */
async function deleteRecipeEntry(recipeId, btnEl) {
  try {
    const resp = await fetch(`${API_BASE_URL}/api/recipes/${encodeURIComponent(recipeId)}`, {
      method: 'DELETE',
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    // Remove the card from the DOM
    const card = btnEl.closest('.bg-surface-container-lowest');
    card.style.opacity = '0';
    card.style.transform = 'translateX(30px)';
    card.style.transition = 'opacity 0.25s, transform 0.25s';
    setTimeout(() => {
      card.remove();
      // Show empty state if no cards remain
      const listEl = document.getElementById('recipes-list');
      if (!listEl.children.length) {
        const emptyEl = document.getElementById('recipes-empty');
        emptyEl.classList.remove('hidden');
        emptyEl.style.display = 'flex';
      }
    }, 280);
    showToast('Recipe deleted', 'success');
  } catch (err) {
    showToast('Could not delete recipe.');
    console.error(err);
  }
}

function createIngredientPill(text, type) {
  const span = document.createElement('span');
  if (type === 'primary') {
    span.className = 'bg-primary-fixed text-on-primary-fixed font-label-lg text-label-lg px-3 py-1 rounded-full capitalize';
  } else {
    span.className = 'bg-surface-container text-on-surface-variant font-label-lg text-label-lg px-3 py-1 rounded-full capitalize border border-outline-variant';
  }
  span.textContent = text;
  return span;
}

function escHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  // Close camera modal on backdrop click
  document.getElementById('camera-modal').addEventListener('click', e => {
    if (e.target === document.getElementById('camera-modal')) closeCamera();
  });

  // Drag & drop on viewfinder
  const viewfinder = document.getElementById('viewfinder');
  viewfinder.addEventListener('dragover', e => {
    e.preventDefault();
    viewfinder.classList.add('border-primary', 'bg-primary-fixed/10');
  });
  viewfinder.addEventListener('dragleave', () => {
    viewfinder.classList.remove('border-primary', 'bg-primary-fixed/10');
  });
  viewfinder.addEventListener('drop', e => {
    e.preventDefault();
    viewfinder.classList.remove('border-primary', 'bg-primary-fixed/10');
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
      selectedFile = file;
      showImagePreview(URL.createObjectURL(file));
    } else {
      showToast('Please drop an image file');
    }
  });

  // Initial view
  showView('home');
});

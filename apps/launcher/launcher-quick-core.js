(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.LauncherQuickCore = factory();
}(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  function copyItem(item) {
    var copy = {};
    Object.keys(item || {}).forEach(function (key) { copy[key] = item[key]; });
    return copy;
  }

  function isInputId(id) {
    return id === 'com.webos.app.livetv' || /^com\.webos\.app\.hdmi[1-4]$/.test(String(id || ''));
  }

  var CATEGORY_ICONS = {
    favorites: 'favorite',
    apps: 'apps',
    links: 'web',
    cameras: 'camera',
    utilities: 'settings'
  };

  function quickItem(row, source) {
    var item = copyItem(source);
    // The full launcher configuration remains the single source of truth. The
    // quick view changes only camera activation to the existing popup PiP app.
    if (row.id === 'cameras' && item.type === 'preset') {
      item.type = 'overlayPreset';
      item.previewPresetId = item.targetId;
    }
    return item;
  }

  function buildCategories(data) {
    var rows = data && data.config && data.config.rows || [];
    return rows.filter(function (row) {
      return row && row.visible !== false;
    }).map(function (row) {
      return {
        id: row.id,
        label: row.title || row.id,
        iconKey: CATEGORY_ICONS[row.id] || 'apps',
        items: (row.items || []).filter(function (item) {
          return item && item.visible !== false;
        }).map(function (item) { return quickItem(row, item); })
      };
    });
  }

  function createState() {
    return { layer: 'categories', categoryIndex: 0, itemIndices: {} };
  }

  function normalizedState(state, categories) {
    state = state || createState();
    categories = categories || [];
    var result = {
      layer: state.layer === 'items' ? 'items' : 'categories',
      categoryIndex: Math.max(0, Math.min(categories.length - 1, Number(state.categoryIndex) || 0)),
      itemIndices: {}
    };
    Object.keys(state.itemIndices || {}).forEach(function (key) { result.itemIndices[key] = Number(state.itemIndices[key]) || 0; });
    if (!categories.length) { result.categoryIndex = 0; result.layer = 'categories'; return result; }
    var category = categories[result.categoryIndex];
    var itemIndex = Math.max(0, Math.min(category.items.length - 1, result.itemIndices[category.id] || 0));
    result.itemIndices[category.id] = itemIndex;
    if (!category.items.length) result.layer = 'categories';
    return result;
  }

  function move(state, intent, categories) {
    var next = normalizedState(state, categories);
    if (!categories || !categories.length) return next;
    var category = categories[next.categoryIndex];
    if (next.layer === 'categories') {
      if (intent === 'left' || intent === 'right') {
        var delta = intent === 'left' ? -1 : 1;
        next.categoryIndex = (next.categoryIndex + delta + categories.length) % categories.length;
      } else if (intent === 'down' && category.items.length) next.layer = 'items';
      return normalizedState(next, categories);
    }
    if (intent === 'up') next.layer = 'categories';
    else if (intent === 'left' || intent === 'right') {
      var index = next.itemIndices[category.id] || 0;
      index += intent === 'left' ? -1 : 1;
      next.itemIndices[category.id] = Math.max(0, Math.min(category.items.length - 1, index));
    }
    return normalizedState(next, categories);
  }

  function currentItem(state, categories) {
    var current = normalizedState(state, categories);
    if (current.layer !== 'items' || !categories.length) return null;
    var category = categories[current.categoryIndex];
    return category.items[current.itemIndices[category.id] || 0] || null;
  }

  return {
    categoryIcons: copyItem(CATEGORY_ICONS),
    buildCategories: buildCategories,
    createState: createState,
    normalizeState: normalizedState,
    move: move,
    currentItem: currentItem,
    isInputId: isInputId
  };
}));

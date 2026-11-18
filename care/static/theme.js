/* 暖茶 / 浅绿双配色切换：在样式表之前设置 data-theme，避免首屏闪色。 */
(function () {
  var KEY = 'anlin-theme';
  var root = document.documentElement;
  var themes = ['warm', 'green'];

  function read() {
    try {
      var saved = localStorage.getItem(KEY);
      return themes.indexOf(saved) >= 0 ? saved : 'warm';
    } catch (error) {
      return 'warm';
    }
  }

  function apply(theme, persist) {
    if (themes.indexOf(theme) < 0) theme = 'warm';
    root.dataset.theme = theme;
    var green = theme === 'green';
    var name = green ? '浅绿' : '暖茶';
    var buttons = document.querySelectorAll('[data-theme-toggle]');
    for (var i = 0; i < buttons.length; i += 1) {
      var button = buttons[i];
      button.setAttribute('aria-pressed', String(green));
      button.setAttribute('aria-label', '切换界面配色，当前' + name);
      button.title = '切换暖茶 / 浅绿配色（当前' + name + '）';
      var label = button.querySelector('.theme-toggle-label');
      if (label) label.textContent = name;
    }
    if (persist) {
      try { localStorage.setItem(KEY, theme); } catch (error) { /* 隐私模式不持久化 */ }
    }
    try {
      root.dispatchEvent(new CustomEvent('themechange', { detail: { theme: theme } }));
    } catch (error) { /* 老浏览器忽略事件失败 */ }
  }

  apply(read(), false);

  document.addEventListener('DOMContentLoaded', function () {
    var buttons = document.querySelectorAll('[data-theme-toggle]');
    for (var i = 0; i < buttons.length; i += 1) {
      buttons[i].addEventListener('click', function () {
        apply(root.dataset.theme === 'green' ? 'warm' : 'green', true);
      });
    }
    apply(read(), false);
  });

  window.addEventListener('storage', function (event) {
    if (event.key === KEY) apply(read(), false);
  });

  window.AnlinTheme = {
    apply: function (theme) { apply(theme, true); },
    current: function () { return root.dataset.theme || 'warm'; }
  };
})();

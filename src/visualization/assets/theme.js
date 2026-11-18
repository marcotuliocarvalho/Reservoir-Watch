window.dash_clientside = Object.assign({}, window.dash_clientside, {
  hidrico: {
    toggleTheme: function (nClicks, current) {
      var theme = current;
      if (!nClicks) {
        if (!theme) {
          var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
          theme = prefersDark ? "dark" : "light";
        }
      } else {
        theme = current === "dark" ? "light" : "dark";
      }
      document.documentElement.setAttribute("data-theme", theme);
      return theme;
    },
  },
});

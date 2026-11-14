/* Site behaviour. No framework, no tracking, no network calls.
   Every feature degrades to working HTML when this file does not load. */
(function () {
  "use strict";

  // --- mobile navigation ---------------------------------------------------
  var toggle = document.querySelector("[data-nav-toggle]");
  var nav = document.querySelector("[data-nav]");

  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.classList.contains("is-open")) {
        nav.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });

    document.addEventListener("click", function (event) {
      if (!nav.contains(event.target) && !toggle.contains(event.target)) {
        nav.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  // --- sticky header hairline ---------------------------------------------
  var header = document.querySelector(".site-header");

  if (header) {
    var onScroll = function () {
      header.classList.toggle("is-stuck", window.scrollY > 8);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // --- copy buttons --------------------------------------------------------
  // The clipboard API is refused in some embedded views. On refusal, select
  // the text so the reader can copy it with the keyboard.
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var target = document.getElementById(button.getAttribute("data-copy"));
      if (!target) return;

      var text = target.innerText;
      var done = function (label) {
        var previous = button.textContent;
        button.textContent = label;
        button.classList.add("is-done");
        window.setTimeout(function () {
          button.textContent = previous;
          button.classList.remove("is-done");
        }, 1600);
      };

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () {
            done("copied");
          },
          function () {
            selectText(target);
            done("selected");
          }
        );
      } else {
        selectText(target);
        done("selected");
      }
    });
  });

  function selectText(node) {
    var range = document.createRange();
    range.selectNodeContents(node);
    var selection = window.getSelection();
    if (!selection) return;
    selection.removeAllRanges();
    selection.addRange(range);
  }

  // --- wide table affordance ----------------------------------------------
  // A table wider than its column scrolls, but nothing on screen says so.
  // Add a short hint under the table while it overflows, and remove it once
  // the reader has scrolled to the end.
  var wrappers = Array.prototype.slice.call(
    document.querySelectorAll(".table-wrap")
  );

  function markOverflow(wrapper) {
    var overflow = wrapper.scrollWidth - wrapper.clientWidth;
    var atEnd = overflow > 2 && wrapper.scrollLeft >= overflow - 2;
    var hint = wrapper.nextElementSibling;

    if (overflow <= 2 || atEnd) {
      if (hint && hint.classList.contains("table-hint")) hint.remove();
      return;
    }

    if (!hint || !hint.classList.contains("table-hint")) {
      hint = document.createElement("p");
      hint.className = "table-hint";
      hint.textContent = "Scroll the table for the rest";
      wrapper.insertAdjacentElement("afterend", hint);
    }
  }

  if (wrappers.length) {
    wrappers.forEach(function (wrapper) {
      markOverflow(wrapper);
      wrapper.addEventListener(
        "scroll",
        function () {
          markOverflow(wrapper);
        },
        { passive: true }
      );
    });

    var remeasure = function () {
      wrappers.forEach(markOverflow);
    };
    window.addEventListener("resize", remeasure, { passive: true });
    window.addEventListener("load", remeasure);
  }

  // --- table of contents highlight ----------------------------------------
  var tocLinks = Array.prototype.slice.call(
    document.querySelectorAll(".toc a[href^='#']")
  );

  if (tocLinks.length && "IntersectionObserver" in window) {
    var byId = {};
    var sections = [];

    tocLinks.forEach(function (link) {
      var id = link.getAttribute("href").slice(1);
      var section = document.getElementById(id);
      if (section) {
        byId[id] = link;
        sections.push(section);
      }
    });

    var visible = {};
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) visible[entry.target.id] = true;
          else delete visible[entry.target.id];
        });

        var current = null;
        for (var i = 0; i < sections.length; i += 1) {
          if (visible[sections[i].id]) {
            current = sections[i];
            break;
          }
        }

        tocLinks.forEach(function (link) {
          link.classList.toggle(
            "is-active",
            Boolean(current) && link === byId[current.id]
          );
        });
      },
      { rootMargin: "-88px 0px -60% 0px", threshold: 0 }
    );

    sections.forEach(function (section) {
      observer.observe(section);
    });
  }

  // --- theme toggle --------------------------------------------------------
  // System theme is the default. A click stores an explicit choice for this
  // browser only; storage can throw in private windows, so every access is
  // guarded and failure just leaves the system theme in place.
  var themeButton = document.querySelector("[data-theme-toggle]");
  var root = document.documentElement;

  function storedTheme() {
    try {
      return window.localStorage.getItem("zyrompts-theme");
    } catch (error) {
      return null;
    }
  }

  function systemTheme() {
    return window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  // The label has to describe what the button will do, which depends on the
  // theme actually in effect, not on whether a choice was stored. With no
  // stored choice under a dark system preference, this used to say "Switch to
  // dark theme": the label named the current theme instead of the next one.
  function applyTheme(theme) {
    if (theme === "dark" || theme === "light") {
      root.setAttribute("data-theme", theme);
    } else {
      root.removeAttribute("data-theme");
    }
    if (themeButton) {
      var effective = theme === "dark" || theme === "light" ? theme : systemTheme();
      themeButton.setAttribute(
        "aria-label",
        effective === "dark" ? "Switch to light theme" : "Switch to dark theme"
      );
    }
  }

  if (themeButton) {
    applyTheme(storedTheme());
    themeButton.addEventListener("click", function () {
      var current =
        root.getAttribute("data-theme") || systemTheme();
      var next = current === "dark" ? "light" : "dark";
      applyTheme(next);
      try {
        window.localStorage.setItem("zyrompts-theme", next);
      } catch (error) {
        /* storage is optional; the choice still applies for this page view */
      }
    });
  }
})();

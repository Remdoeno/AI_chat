(() => {
  const EYE_ICON = `
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M2.1 12s3.6-6.5 9.9-6.5S21.9 12 21.9 12s-3.6 6.5-9.9 6.5S2.1 12 2.1 12Z"></path>
      <circle cx="12" cy="12" r="3"></circle>
    </svg>
  `;
  const EYE_OFF_ICON = `
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M3 3l18 18"></path>
      <path d="M10.6 10.6A2 2 0 0 0 12 14a2 2 0 0 0 1.4-.6"></path>
      <path d="M9.9 5.8A9.8 9.8 0 0 1 12 5.5c6.3 0 9.9 6.5 9.9 6.5a17 17 0 0 1-3 3.8"></path>
      <path d="M6.1 7.6A17 17 0 0 0 2.1 12s3.6 6.5 9.9 6.5a9.7 9.7 0 0 0 4-.8"></path>
    </svg>
  `;

  function bindPasswordInput(input) {
    if (!(input instanceof HTMLInputElement) || input.dataset.passwordVisibilityBound === "true") {
      return;
    }
    input.dataset.passwordVisibilityBound = "true";

    const wrapper = document.createElement("span");
    wrapper.className = "password-input-wrap";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "password-visibility-toggle";
    button.setAttribute("aria-label", "显示密码");
    button.setAttribute("aria-pressed", "false");
    button.title = "显示密码";
    button.innerHTML = EYE_ICON;
    wrapper.appendChild(button);

    button.addEventListener("click", () => {
      const revealing = input.type === "password";
      input.type = revealing ? "text" : "password";
      button.setAttribute("aria-label", revealing ? "隐藏密码" : "显示密码");
      button.setAttribute("aria-pressed", revealing ? "true" : "false");
      button.title = revealing ? "隐藏密码" : "显示密码";
      button.innerHTML = revealing ? EYE_OFF_ICON : EYE_ICON;
      input.focus({ preventScroll: true });
    });
  }

  function initPasswordVisibility() {
    document.querySelectorAll('input[type="password"]').forEach(bindPasswordInput);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPasswordVisibility, { once: true });
  } else {
    initPasswordVisibility();
  }
})();

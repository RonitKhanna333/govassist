(function () {
  const toggle = document.querySelector(".nav-toggle");
  const navigation = document.querySelector(".site-nav");
  if (!toggle || !navigation) return;

  toggle.addEventListener("click", () => {
    const open = navigation.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", String(open));
    toggle.textContent = open ? "Close" : "Menu";
  });

  navigation.addEventListener("click", (event) => {
    if (!event.target.closest("a")) return;
    navigation.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
    toggle.textContent = "Menu";
  });
})();

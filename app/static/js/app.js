(function () {
  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebarToggle");
  const languageSelect = document.getElementById("languageSelect");
  const fontSelect = document.getElementById("fontSelect");
  const fontSizeSelect = document.getElementById("fontSizeSelect");

  function readPrefsFromControls() {
    return {
      language: languageSelect.value,
      font: fontSelect.value,
      font_size: Number(fontSizeSelect.value),
    };
  }

  async function savePrefsAndReload() {
    const body = readPrefsFromControls();
    const response = await fetch("/api/prefs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail);
    }
    window.location.reload();
  }

  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
  }

  languageSelect.addEventListener("change", savePrefsAndReload);
  fontSelect.addEventListener("change", savePrefsAndReload);
  fontSizeSelect.addEventListener("change", savePrefsAndReload);
})();

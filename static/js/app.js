(function () {
  "use strict";

  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const toggle = document.getElementById("sidebarToggle");

  function closeSidebar() {
    if (sidebar) sidebar.classList.remove("open");
    if (overlay) overlay.classList.remove("show");
  }

  if (toggle && sidebar && overlay) {
    toggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
      overlay.classList.toggle("show");
    });
    overlay.addEventListener("click", closeSidebar);
    sidebar.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", closeSidebar);
    });
  }

  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("excelFile");
  const fileLabel = document.getElementById("selectedFileName");
  const fileNameWrap = document.querySelector(".file-name");
  const uploadForm = document.getElementById("uploadForm");

  if (dropzone && fileInput) {
    function showFile(name) {
      if (fileLabel) fileLabel.textContent = name;
      if (fileNameWrap) fileNameWrap.classList.remove("d-none");
    }

    dropzone.addEventListener("click", function (e) {
      if (e.target.closest("button, input, label, a, select, textarea, .form-control")) {
        return;
      }
      fileInput.click();
    });

    dropzone.addEventListener("dragover", function (e) {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", function () {
      dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", function (e) {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      const files = e.dataTransfer?.files;
      if (files && files.length) {
        fileInput.files = files;
        showFile(files[0].name);
      }
    });

    fileInput.addEventListener("change", function () {
      if (fileInput.files && fileInput.files[0]) {
        showFile(fileInput.files[0].name);
      }
    });

    if (uploadForm) {
      uploadForm.addEventListener("submit", function (e) {
        const hasFile = fileInput.files && fileInput.files.length > 0;
        const hasLast = uploadForm.dataset.hasLast === "1";
        if (!hasFile && !hasLast) {
          e.preventDefault();
          alert("Zgjidhni një skedar Excel për ngarkim.");
          return;
        }
        const btn = uploadForm.querySelector('button[type="submit"]');
        if (btn && !btn.disabled) {
          btn.disabled = true;
          btn.innerHTML =
            '<span class="spinner-border spinner-border-sm me-2"></span>Duke përpunuar...';
        }
      });
    }
  }
})();

// DepthWizard Client Interaction Scripts
document.addEventListener("DOMContentLoaded", () => {
  setupDropzone();
});

function setupDropzone() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const pill = document.getElementById("selected-file-pill");
  const fileNameSpan = document.getElementById("selected-file-name");
  const submitBtn = document.getElementById("submit-btn");

  if (!dropzone || !fileInput) return;

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length > 0) {
      fileInput.files = e.dataTransfer.files;
      updateFileDisplay(e.dataTransfer.files[0].name);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      updateFileDisplay(e.target.files[0].name);
    }
  });

  function updateFileDisplay(name) {
    if (fileNameSpan && pill) {
      fileNameSpan.textContent = name;
      pill.style.display = "inline-flex";
    }
    if (submitBtn) {
      submitBtn.disabled = false;
    }
  }
}

// Function to trigger pre-packaged sample execution via API
async function runSample(sampleName) {
  const statusContainer = document.getElementById("job-status-panel");
  if (!statusContainer) return;

  try {
    statusContainer.innerHTML = `
      <div class="instrument-card">
        <div class="card-header">
          <div class="card-title-group">
            <div class="card-title">Initiating Benchmark Scene</div>
            <div class="card-subtitle">Loading ${sampleName} into processing pipeline</div>
          </div>
          <span class="card-badge status-active">DISPATCHING</span>
        </div>
        <div class="step-indicator"><div class="pulse-dot"></div> Submitting job to pipeline...</div>
      </div>
    `;

    const res = await fetch(`/api/jobs/sample?sample_name=${encodeURIComponent(sampleName)}`, {
      method: "POST"
    });
    const data = await res.json();
    if (data.id) {
      // Trigger htmx get to load polling partial
      htmx.ajax("GET", `/jobs/${data.id}/status`, { target: "#job-status-panel", swap: "innerHTML" });
    } else {
      statusContainer.innerHTML = `
        <div class="instrument-card">
          <p style="color: var(--color-accent-red); font-family: var(--font-mono); font-size: 0.85rem;">Error launching sample scene.</p>
        </div>
      `;
    }
  } catch (err) {
    console.error("Failed to run sample:", err);
  }
}
